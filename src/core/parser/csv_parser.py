"""XBRL-CSV (OIM) parser — Rule 16 compliant (no float for numerics)."""

from __future__ import annotations

import csv
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from src.core.exceptions import CSVParseError
from src.core.types import InputFormat


@dataclass(frozen=True)
class CSVColumn:
    """Metadata for a single CSV column."""
    name: str
    dimensions: dict[str, str] = field(default_factory=dict)
    propertiesFrom: str | None = None
    decimals: str | None = None


@dataclass(frozen=True)
class CSVTable:
    """A single table definition from xBRL-CSV metadata."""
    table_id: str
    url: str
    columns: dict[str, CSVColumn] = field(default_factory=dict)
    parameters: dict[str, str] = field(default_factory=dict)


@dataclass
class CSVFact:
    """A fact extracted from a CSV row."""
    fact_id: str
    concept: str
    value: str | None
    entity: str | None = None
    period: dict[str, str] | None = None
    unit: str | None = None
    decimals: str | None = None
    dimensions: dict[str, str] = field(default_factory=dict)
    is_nil: bool = False


@dataclass
class XBRLCSVDocument:
    """Parsed xBRL-CSV document."""
    source_file: str
    source_size: int
    document_type: str = ""
    namespaces: dict[str, str] = field(default_factory=dict)
    taxonomy: list[str] = field(default_factory=list)
    tables: list[CSVTable] = field(default_factory=list)
    facts: list[CSVFact] = field(default_factory=list)
    format: InputFormat = InputFormat.XBRL_CSV


class XBRLCSVParser:
    """Parser for xBRL-CSV (OIM) report packages.

    Rule 16 compliance: all numeric column values are read as strings.
    """

    def parse(self, metadata_path: str) -> XBRLCSVDocument:
        """Parse an xBRL-CSV report from its metadata JSON file.

        Args:
            metadata_path: Path to the xBRL-CSV metadata JSON file.

        Returns:
            Parsed XBRLCSVDocument with all facts.

        Raises:
            CSVParseError: On any structural or I/O error.
        """
        if not os.path.isfile(metadata_path):
            raise CSVParseError(
                code="CSV-0001",
                message=f"Metadata file not found: {metadata_path}",
                file_path=metadata_path,
            )

        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except json.JSONDecodeError as exc:
            raise CSVParseError(
                code="CSV-0002",
                message=f"Invalid JSON in metadata file: {exc}",
                file_path=metadata_path,
                line=exc.lineno,
                column=exc.colno,
            ) from exc

        meta_size = os.path.getsize(metadata_path)
        base_dir = str(Path(metadata_path).parent)

        doc_info = raw.get("documentInfo", {})
        document_type = doc_info.get("documentType", "")
        namespaces = doc_info.get("namespaces", {})
        taxonomy = doc_info.get("taxonomy", [])

        tables_raw = raw.get("tables", {})
        tables: list[CSVTable] = []
        all_facts: list[CSVFact] = []
        fact_counter = 0

        for table_id, table_def in tables_raw.items():
            url = table_def.get("url", "")
            columns_raw = table_def.get("columns", {})
            parameters = table_def.get("parameters", {})

            columns: dict[str, CSVColumn] = {}
            for col_name, col_def in columns_raw.items():
                if isinstance(col_def, dict):
                    columns[col_name] = CSVColumn(
                        name=col_name,
                        dimensions=col_def.get("dimensions", {}),
                        propertiesFrom=col_def.get("propertiesFrom"),
                        decimals=col_def.get("decimals"),
                    )
                else:
                    columns[col_name] = CSVColumn(name=col_name)

            table = CSVTable(
                table_id=table_id,
                url=url,
                columns=columns,
                parameters=parameters,
            )
            tables.append(table)

            # Read the CSV data file
            csv_path = os.path.join(base_dir, url) if url else ""
            if csv_path and os.path.isfile(csv_path):
                try:
                    facts, count = self._read_csv_table(
                        csv_path, table, namespaces, fact_counter,
                    )
                    all_facts.extend(facts)
                    fact_counter = count
                except Exception as exc:
                    raise CSVParseError(
                        code="CSV-0003",
                        message=f"Error reading CSV table '{table_id}': {exc}",
                        file_path=csv_path,
                    ) from exc

        return XBRLCSVDocument(
            source_file=metadata_path,
            source_size=meta_size,
            document_type=document_type,
            namespaces=namespaces,
            taxonomy=taxonomy,
            tables=tables,
            facts=all_facts,
        )

    def _read_csv_table(
        self,
        csv_path: str,
        table: CSVTable,
        namespaces: dict[str, str],
        start_counter: int,
    ) -> tuple[list[CSVFact], int]:
        """Read facts from a single CSV data file.

        All cell values are read as strings (Rule 16 compliance).
        """
        facts: list[CSVFact] = []
        counter = start_counter

        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                for col_name, cell_value in row.items():
                    if col_name is None or cell_value is None:
                        continue

                    col_def = table.columns.get(col_name)
                    if col_def is None:
                        continue

                    dims = dict(col_def.dimensions)
                    concept = dims.pop("concept", col_name)
                    concept = self._resolve_prefixed(concept, namespaces)

                    entity = dims.pop("entity", None)
                    period_str = dims.pop("period", None)
                    period = self._parse_period_string(period_str) if period_str else None
                    unit = dims.pop("unit", None)
                    decimals = col_def.decimals

                    # Resolve remaining dimension values
                    resolved_dims: dict[str, str] = {}
                    for dk, dv in dims.items():
                        resolved_dims[self._resolve_prefixed(dk, namespaces)] = (
                            self._resolve_prefixed(str(dv), namespaces)
                        )

                    # Apply propertiesFrom
                    if col_def.propertiesFrom and col_def.propertiesFrom in row:
                        pass  # propertiesFrom references another column for metadata

                    is_nil = cell_value.strip() == "" and concept != ""
                    value = cell_value if not is_nil else None

                    fact_id = f"f-{table.table_id}-{counter}"
                    counter += 1

                    facts.append(CSVFact(
                        fact_id=fact_id,
                        concept=concept,
                        value=value,
                        entity=entity,
                        period=period,
                        unit=unit,
                        decimals=decimals,
                        dimensions=resolved_dims,
                        is_nil=is_nil,
                    ))

        return facts, counter

    @staticmethod
    def _resolve_prefixed(name: str, namespaces: dict[str, str]) -> str:
        """Resolve prefix:local to {uri}local using namespace map."""
        if ":" not in name or name.startswith("{"):
            return name
        prefix, _, local = name.partition(":")
        uri = namespaces.get(prefix, "")
        if uri:
            return f"{{{uri}}}{local}"
        return name

    @staticmethod
    def _parse_period_string(period_str: str) -> dict[str, str]:
        """Parse a period string into a period dict."""
        period_str = period_str.strip()
        if "/" in period_str:
            parts = period_str.split("/", 1)
            return {"startDate": parts[0], "endDate": parts[1]}
        return {"instant": period_str}
