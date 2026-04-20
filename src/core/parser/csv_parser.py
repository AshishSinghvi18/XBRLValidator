"""Parser for xBRL-CSV format documents.

Parses xBRL-CSV documents consisting of a JSON metadata file and one
or more CSV data files into a ``RawXBRLDocument``.

The metadata file (typically ``metadata.json``) defines:
- documentInfo (namespaces, taxonomy references)
- table definitions (columns, dimensions, propertiesFrom)
- links to CSV data files

Spec references:
- xBRL-CSV 1.0 §2 (document structure)
- xBRL-CSV 1.0 §3 (metadata file)
- xBRL-CSV 1.0 §4 (CSV data)
- W3C CSV on the Web (CSVW) metadata vocabulary
"""

from __future__ import annotations

import json
import logging
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

import polars as pl

from src.core.exceptions import ParseError
from src.core.parser.xml_parser import (
    RawContext,
    RawFact,
    RawUnit,
    RawXBRLDocument,
    SchemaRef,
)

logger = logging.getLogger(__name__)

# Default CSV read options
_CSV_ENCODING = "utf-8"


class CSVParser:
    """Parser for xBRL-CSV format documents.

    Uses ``polars`` for fast, memory-efficient CSV reading and ``json``
    for metadata parsing.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, metadata_path: str) -> RawXBRLDocument:
        """Parse an xBRL-CSV document from its metadata file.

        Reads the JSON metadata file to discover table definitions,
        then parses each referenced CSV data file.

        Parameters
        ----------
        metadata_path:
            Path to the metadata JSON file (e.g. ``metadata.json``).

        Returns
        -------
        RawXBRLDocument

        Raises
        ------
        ParseError
            On metadata parsing errors or missing CSV files.
        """
        doc = RawXBRLDocument(file_path=metadata_path)

        # Read metadata
        try:
            with open(metadata_path, "r", encoding=_CSV_ENCODING) as fh:
                metadata = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ParseError(
                f"Invalid JSON in metadata file: {exc}",
                file_path=metadata_path,
                line=0,
                column=0,
            ) from exc
        except OSError as exc:
            raise ParseError(
                f"Cannot read metadata file: {exc}",
                file_path=metadata_path,
                line=0,
                column=0,
            ) from exc

        if not isinstance(metadata, dict):
            raise ParseError(
                "xBRL-CSV metadata must be a JSON object",
                file_path=metadata_path,
                line=0,
                column=0,
            )

        # Extract document info
        self._extract_document_info(metadata, doc)

        # Process tables
        base_dir = str(Path(metadata_path).parent)
        tables = metadata.get("tables", metadata.get("tableGroup", {}).get("tables", []))
        if isinstance(tables, dict):
            # Single table object → convert to list
            tables = list(tables.values()) if all(
                isinstance(v, dict) for v in tables.values()
            ) else [tables]
        elif not isinstance(tables, list):
            tables = []

        context_counter = 0
        unit_counter = 0
        context_cache: dict[str, str] = {}
        unit_cache: dict[str, str] = {}

        for table_idx, table_def in enumerate(tables):
            if not isinstance(table_def, dict):
                doc.parse_errors.append(
                    f"Table definition {table_idx} is not an object"
                )
                continue

            try:
                ctx_count, unit_count = self._process_table(
                    table_def,
                    base_dir,
                    doc,
                    context_counter,
                    unit_counter,
                    context_cache,
                    unit_cache,
                )
                context_counter = ctx_count
                unit_counter = unit_count
            except Exception as exc:  # noqa: BLE001
                doc.parse_errors.append(
                    f"Error processing table {table_idx}: {exc}"
                )

        return doc

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_document_info(
        metadata: dict[str, Any], doc: RawXBRLDocument
    ) -> None:
        """Extract document-level metadata."""
        doc_info = metadata.get("documentInfo", {})
        if isinstance(doc_info, dict):
            # Namespaces
            ns = doc_info.get("namespaces", {})
            if isinstance(ns, dict):
                doc.namespaces = {str(k): str(v) for k, v in ns.items()}

            # Taxonomy
            taxonomy = doc_info.get("taxonomy", [])
            if isinstance(taxonomy, list):
                for href in taxonomy:
                    if isinstance(href, str):
                        doc.schema_refs.append(SchemaRef(href=href))

    def _process_table(
        self,
        table_def: dict[str, Any],
        base_dir: str,
        doc: RawXBRLDocument,
        context_counter: int,
        unit_counter: int,
        context_cache: dict[str, str],
        unit_cache: dict[str, str],
    ) -> tuple[int, int]:
        """Process a single table definition.

        Parameters
        ----------
        table_def:
            Table definition from metadata.
        base_dir:
            Base directory for resolving relative CSV paths.
        doc:
            Document being built.
        context_counter, unit_counter:
            Running counters for synthesised context/unit IDs.
        context_cache, unit_cache:
            Caches to avoid duplicate context/unit creation.

        Returns
        -------
        tuple[int, int]
            Updated (context_counter, unit_counter).
        """
        # Resolve CSV file path
        csv_url = table_def.get("url", "")
        if not csv_url:
            doc.parse_errors.append("Table definition missing 'url'")
            return context_counter, unit_counter

        csv_path = os.path.join(base_dir, csv_url)
        if not os.path.exists(csv_path):
            doc.parse_errors.append(f"CSV file not found: {csv_path}")
            return context_counter, unit_counter

        # Extract column definitions
        columns = table_def.get("columns", {})
        if not isinstance(columns, dict):
            columns = {}

        # Table-level dimensions (propertiesFrom or dimensions)
        table_dims = table_def.get("dimensions", {})
        if not isinstance(table_dims, dict):
            table_dims = {}

        # Read CSV
        try:
            df = pl.read_csv(csv_path, encoding=_CSV_ENCODING, infer_schema_length=0)
        except Exception as exc:  # noqa: BLE001
            doc.parse_errors.append(f"Error reading CSV {csv_path}: {exc}")
            return context_counter, unit_counter

        # Process rows
        col_names = df.columns
        for row_idx in range(len(df)):
            row_data: dict[str, str] = {}
            for col in col_names:
                val = df[col][row_idx]
                row_data[col] = str(val) if val is not None else ""

            try:
                context_counter, unit_counter = self._process_row(
                    row_data,
                    columns,
                    table_dims,
                    doc,
                    context_counter,
                    unit_counter,
                    context_cache,
                    unit_cache,
                    row_idx + 1,
                )
            except Exception as exc:  # noqa: BLE001
                doc.parse_errors.append(
                    f"Error processing row {row_idx + 1} in {csv_path}: {exc}"
                )

        return context_counter, unit_counter

    def _process_row(
        self,
        row_data: dict[str, str],
        columns: dict[str, Any],
        table_dims: dict[str, Any],
        doc: RawXBRLDocument,
        context_counter: int,
        unit_counter: int,
        context_cache: dict[str, str],
        unit_cache: dict[str, str],
        row_num: int,
    ) -> tuple[int, int]:
        """Process a single CSV row into facts.

        Each value column in the row becomes a separate XBRL fact.
        Dimension columns provide context/unit information.
        """
        # Build dimensions from table-level defaults + row data
        dims: dict[str, str] = {}
        dims.update({str(k): str(v) for k, v in table_dims.items()})

        # Override with row-level dimension columns
        for col_name, col_def in columns.items():
            if isinstance(col_def, dict):
                dim_prop = col_def.get("dimensions", {})
                if isinstance(dim_prop, dict):
                    for dk, dv in dim_prop.items():
                        if isinstance(dv, str) and dv.startswith("$"):
                            # Column reference
                            ref_col = dv.lstrip("$")
                            if ref_col in row_data:
                                dims[dk] = row_data[ref_col]
                        else:
                            dims[dk] = str(dv)

            # Check if column itself is a dimension source
            if col_name in row_data and isinstance(col_def, dict):
                prop_from = col_def.get("propertyGroupFrom", "")
                if prop_from:
                    dims[prop_from] = row_data[col_name]

        # Synthesise context
        entity = dims.get("xbrl:entity", "")
        period = dims.get("xbrl:period", "")
        ctx_key = f"entity={entity}|period={period}"

        # Add extra dimensions to context key
        extra_dims = {
            k: v for k, v in sorted(dims.items())
            if k not in ("xbrl:concept", "xbrl:entity", "xbrl:period",
                         "xbrl:unit", "xbrl:language", "xbrl:noteId")
        }
        if extra_dims:
            ctx_key += "|" + "|".join(f"{k}={v}" for k, v in extra_dims.items())

        if ctx_key in context_cache:
            context_ref = context_cache[ctx_key]
        else:
            context_counter += 1
            context_ref = f"_csv_ctx_{context_counter}"
            ctx = self._synthesize_context(context_ref, entity, period)
            doc.contexts[context_ref] = ctx
            context_cache[ctx_key] = context_ref

        # Process value columns
        for col_name, col_def in columns.items():
            if not isinstance(col_def, dict):
                continue

            # Determine if this is a fact column
            col_dims = col_def.get("dimensions", {})
            concept = ""
            if isinstance(col_dims, dict):
                concept = str(col_dims.get("xbrl:concept", ""))
            if not concept:
                # Try propertyGroupFrom or skip
                continue

            value = row_data.get(col_name, "")
            if not value:
                continue

            # Resolve concept
            concept_resolved = self._resolve_qname(concept, doc.namespaces)

            # Unit
            unit_qname = dims.get("xbrl:unit", "")
            if isinstance(col_dims, dict):
                unit_qname = str(col_dims.get("xbrl:unit", unit_qname))

            unit_ref: Optional[str] = None
            if unit_qname:
                if unit_qname in unit_cache:
                    unit_ref = unit_cache[unit_qname]
                else:
                    unit_counter += 1
                    unit_ref = f"_csv_unit_{unit_counter}"
                    unit = RawUnit(id=unit_ref, measures=[unit_qname])
                    doc.units[unit_ref] = unit
                    unit_cache[unit_qname] = unit_ref

            # Decimals
            decimals = col_def.get("decimals")
            if decimals is not None:
                decimals = str(decimals)

            fact = RawFact(
                concept=concept_resolved,
                context_ref=context_ref,
                unit_ref=unit_ref,
                value=value,
                decimals=decimals,
                source_line=row_num,
            )
            doc.facts.append(fact)

        return context_counter, unit_counter

    @staticmethod
    def _synthesize_context(
        ctx_id: str, entity: str, period: str
    ) -> RawContext:
        """Create a ``RawContext`` from CSV dimension values."""
        ctx = RawContext(id=ctx_id)

        if entity:
            if " " in entity:
                parts = entity.split(" ", maxsplit=1)
                ctx.entity_scheme = parts[0]
                ctx.entity_id = parts[1]
            elif ":" in entity:
                scheme, eid = entity.split(":", maxsplit=1)
                ctx.entity_scheme = scheme
                ctx.entity_id = eid
            else:
                ctx.entity_id = entity

        if period:
            if "/" in period:
                parts = period.split("/", maxsplit=1)
                ctx.period_type = "duration"
                ctx.start_date = parts[0]
                ctx.end_date = parts[1]
            elif period.lower() == "forever":
                ctx.period_type = "forever"
            else:
                ctx.period_type = "instant"
                ctx.instant = period

        return ctx

    @staticmethod
    def _resolve_qname(
        qname: str, namespaces: dict[str, str]
    ) -> str:
        """Resolve a prefixed QName to Clark notation."""
        if not qname or ":" not in qname:
            return qname
        prefix, local = qname.split(":", maxsplit=1)
        ns_uri = namespaces.get(prefix, "")
        if ns_uri:
            return f"{{{ns_uri}}}{local}"
        return qname
