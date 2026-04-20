"""XBRL-CSV parser (OIM format).

Parses xBRL-CSV document sets per the OIM specification into the
canonical XBRLInstance model. Handles metadata.json + CSV table files.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import structlog

from src.core.exceptions import CSVParseError
from src.core.model.builder_oim import OIMFact, OIMModelBuilder
from src.core.model.xbrl_model import TaxonomyModel, XBRLInstance
from src.core.types import InputFormat

logger = structlog.get_logger(__name__)


class CSVParser:
    """Parse xBRL-CSV document sets into XBRLInstance."""

    def __init__(self) -> None:
        self._log = logger.bind(component="csv_parser")
        self._builder = OIMModelBuilder()

    def parse(
        self,
        file_path: str | Path,
        taxonomy: TaxonomyModel | None = None,
    ) -> XBRLInstance:
        """Parse an xBRL-CSV document set.

        If file_path points to a JSON metadata file, it reads table
        definitions and locates associated CSV files. If it points
        directly to a CSV file, it parses it with default column mappings.

        Args:
            file_path: Path to the metadata JSON or CSV file.
            taxonomy: Optional resolved taxonomy.

        Returns:
            XBRLInstance with the parsed data.

        Raises:
            CSVParseError: If the document set is malformed.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        self._log.info("csv_parse_start", path=str(path))

        if path.suffix.lower() == ".json":
            return self._parse_metadata(path, taxonomy)
        return self._parse_csv_direct(path, taxonomy)

    def _parse_metadata(
        self, meta_path: Path, taxonomy: TaxonomyModel | None
    ) -> XBRLInstance:
        """Parse from xBRL-CSV metadata.json entry point."""
        try:
            import orjson
            meta_data = orjson.loads(meta_path.read_bytes())
        except Exception as exc:
            raise CSVParseError(
                message=f"Failed to parse CSV metadata: {exc}",
                code="PARSE-0070",
                file_path=str(meta_path),
            ) from exc

        if not isinstance(meta_data, dict):
            raise CSVParseError(
                message="CSV metadata root must be an object",
                code="PARSE-0071",
                file_path=str(meta_path),
            )

        doc_info = meta_data.get("documentInfo", {})
        prefixes = doc_info.get("namespaces", {}) if isinstance(doc_info, dict) else {}

        tables = meta_data.get("tables", {})
        if not isinstance(tables, dict):
            tables = {}

        all_facts: list[OIMFact] = []
        base_dir = meta_path.parent

        for table_id, table_def in tables.items():
            if not isinstance(table_def, dict):
                continue
            csv_url = table_def.get("url", "")
            if not csv_url:
                continue
            csv_path = base_dir / csv_url
            if not csv_path.exists():
                self._log.warning("csv_table_missing", table=table_id, path=str(csv_path))
                continue

            columns = table_def.get("columns", {})
            template_dims = table_def.get("dimensions", {})
            facts = self._parse_csv_table(
                csv_path, table_id, columns, template_dims
            )
            all_facts.extend(facts)

        instance = self._builder.build_from_facts(
            all_facts,
            source_file=str(meta_path),
            format_type=InputFormat.XBRL_CSV,
            taxonomy=taxonomy,
            prefixes=dict(prefixes) if isinstance(prefixes, dict) else {},
        )

        self._log.info("csv_parse_complete", facts=len(instance.facts))
        return instance

    def _parse_csv_direct(
        self, csv_path: Path, taxonomy: TaxonomyModel | None
    ) -> XBRLInstance:
        """Parse a standalone CSV file with default column mappings."""
        facts = self._parse_csv_table(csv_path, "default", {}, {})
        instance = self._builder.build_from_facts(
            facts,
            source_file=str(csv_path),
            format_type=InputFormat.XBRL_CSV,
            taxonomy=taxonomy,
        )
        self._log.info("csv_direct_parse_complete", facts=len(instance.facts))
        return instance

    def _parse_csv_table(
        self,
        csv_path: Path,
        table_id: str,
        columns: dict[str, Any],
        template_dims: dict[str, str],
    ) -> list[OIMFact]:
        """Parse a single CSV table file into OIM facts."""
        facts: list[OIMFact] = []

        try:
            text = csv_path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            raise CSVParseError(
                message=f"Failed to read CSV file: {exc}",
                code="PARSE-0072",
                file_path=str(csv_path),
            ) from exc

        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            return facts

        # Map column definitions
        col_map = self._build_column_map(reader.fieldnames, columns)

        for row_idx, row in enumerate(reader):
            fact = self._row_to_fact(row, col_map, template_dims, row_idx, str(csv_path))
            if fact is not None:
                facts.append(fact)

        return facts

    def _build_column_map(
        self,
        fieldnames: list[str],
        columns: dict[str, Any],
    ) -> dict[str, str]:
        """Build a mapping from CSV column names to OIM aspect names."""
        col_map: dict[str, str] = {}
        standard_mappings = {
            "concept": "concept",
            "entity": "entity",
            "period": "period",
            "unit": "unit",
            "value": "value",
            "decimals": "decimals",
            "language": "language",
        }

        for fn in fieldnames:
            fn_lower = fn.lower()
            if fn_lower in standard_mappings:
                col_map[fn] = standard_mappings[fn_lower]
            elif fn in columns:
                col_def = columns[fn]
                if isinstance(col_def, dict):
                    dim = col_def.get("dimensions", {})
                    if isinstance(dim, dict) and "concept" in dim:
                        col_map[fn] = "concept"
                    else:
                        col_map[fn] = fn
                else:
                    col_map[fn] = fn
            else:
                col_map[fn] = fn

        return col_map

    def _row_to_fact(
        self,
        row: dict[str, str],
        col_map: dict[str, str],
        template_dims: dict[str, str],
        row_idx: int,
        source_file: str,
    ) -> OIMFact | None:
        """Convert a CSV row to an OIMFact."""
        concept = ""
        entity = ""
        period = ""
        unit = ""
        value: Any = None
        decimals: int | str | None = None
        language: str | None = None
        extra_dims: dict[str, str] = dict(template_dims)

        for col_name, mapped in col_map.items():
            cell = row.get(col_name, "").strip()
            if not cell:
                continue
            if mapped == "concept":
                concept = cell
            elif mapped == "entity":
                entity = cell
            elif mapped == "period":
                period = cell
            elif mapped == "unit":
                unit = cell
            elif mapped == "value":
                value = cell
            elif mapped == "decimals":
                if cell.upper() == "INF":
                    decimals = "INF"
                else:
                    try:
                        decimals = int(cell)
                    except ValueError:
                        pass
            elif mapped == "language":
                language = cell
            else:
                extra_dims[col_name] = cell

        if not concept and value is None:
            return None

        period_instant = ""
        period_start = ""
        period_end = ""
        if "/" in period:
            parts = period.split("/", 1)
            period_start = parts[0]
            period_end = parts[1]
        elif period:
            period_instant = period

        return OIMFact(
            id=f"r{row_idx}",
            concept=concept,
            entity=entity,
            period_instant=period_instant,
            period_start=period_start,
            period_end=period_end,
            unit=unit,
            value=value,
            decimals=decimals,
            dimensions=extra_dims,
            language=language,
            is_nil=value is None or value == "",
        )
