"""Streaming parser for xBRL-CSV using polars lazy frames.

Parses xBRL-CSV documents that exceed the DOM threshold by reading
the CSV data in batches using ``polars.scan_csv`` and lazy evaluation.
Facts are streamed batch-by-batch and stored in the ``FactStore``.

Spec references:
- xBRL-CSV 1.0 §2–4
- polars documentation (scan_csv, lazy frames)
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import polars as pl

from src.core.parser.streaming.fact_index import FactReference
from src.core.parser.streaming.fact_store import FactStore
from src.core.parser.streaming.memory_budget import MemoryBudget
from src.core.parser.streaming.sax_handler import StreamingParseResult
from src.core.parser.xml_parser import RawContext, RawUnit, SchemaRef

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50_000  # rows per batch


class XBRLCSVStreamer:
    """Streaming parser for xBRL-CSV using polars lazy frames.

    Reads the JSON metadata file to discover table definitions and
    column mappings, then uses ``polars.scan_csv`` with batch
    collection to process CSV data without loading everything
    into memory at once.

    Parameters
    ----------
    metadata_path:
        Path to the xBRL-CSV metadata JSON file.
    fact_store:
        ``FactStore`` to hold parsed fact references.
    budget:
        ``MemoryBudget`` for memory tracking.
    """

    def __init__(
        self,
        metadata_path: str,
        fact_store: FactStore,
        budget: MemoryBudget,
    ) -> None:
        self._metadata_path = metadata_path
        self._fact_store = fact_store
        self._budget = budget
        self._fact_index = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self) -> StreamingParseResult:
        """Stream-parse xBRL-CSV data using polars scan_csv.

        Steps:
        1. Read metadata JSON for table definitions.
        2. For each table, use ``polars.scan_csv`` to create a lazy frame.
        3. Collect in batches of ``_BATCH_SIZE`` rows.
        4. Convert each batch into ``FactReference`` entries.

        Returns
        -------
        StreamingParseResult
        """
        result = StreamingParseResult(fact_store=self._fact_store)
        start_time = time.monotonic()

        # Read metadata
        try:
            with open(self._metadata_path, "r", encoding="utf-8") as fh:
                metadata = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            result.parse_errors.append(
                f"Cannot read metadata file: {exc}"
            )
            result.elapsed_seconds = time.monotonic() - start_time
            return result

        if not isinstance(metadata, dict):
            result.parse_errors.append("Metadata is not a JSON object")
            result.elapsed_seconds = time.monotonic() - start_time
            return result

        # Extract document info
        self._extract_document_info(metadata, result)

        # Process tables
        base_dir = str(Path(self._metadata_path).parent)
        tables = metadata.get("tables", metadata.get(
            "tableGroup", {}
        ).get("tables", []))

        if isinstance(tables, dict):
            tables = list(tables.values()) if all(
                isinstance(v, dict) for v in tables.values()
            ) else [tables]
        elif not isinstance(tables, list):
            tables = []

        context_counter = 0
        unit_counter = 0
        context_cache: dict[str, str] = {}
        unit_cache: dict[str, str] = {}
        total_bytes = 0

        for table_idx, table_def in enumerate(tables):
            if not isinstance(table_def, dict):
                result.parse_errors.append(
                    f"Table {table_idx} is not an object"
                )
                continue

            try:
                ctx_c, unit_c, bytes_scanned = self._stream_table(
                    table_def,
                    base_dir,
                    result,
                    context_counter,
                    unit_counter,
                    context_cache,
                    unit_cache,
                )
                context_counter = ctx_c
                unit_counter = unit_c
                total_bytes += bytes_scanned
            except Exception as exc:  # noqa: BLE001
                result.parse_errors.append(
                    f"Error streaming table {table_idx}: {exc}"
                )

        result.total_bytes_scanned = total_bytes
        result.total_facts = self._fact_store.count
        result.elapsed_seconds = time.monotonic() - start_time
        result.spill_occurred = (
            self._fact_store.storage_mode.value != "in_memory"
        )

        logger.info(
            "CSV streaming parse complete: %s facts in %.2fs",
            result.total_facts,
            result.elapsed_seconds,
        )

        return result

    # ------------------------------------------------------------------
    # Document info
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_document_info(
        metadata: dict[str, Any], result: StreamingParseResult
    ) -> None:
        """Extract namespaces and taxonomy references from metadata."""
        doc_info = metadata.get("documentInfo", {})
        if isinstance(doc_info, dict):
            ns = doc_info.get("namespaces", {})
            if isinstance(ns, dict):
                result.namespaces = {str(k): str(v) for k, v in ns.items()}

            taxonomy = doc_info.get("taxonomy", [])
            if isinstance(taxonomy, list):
                for href in taxonomy:
                    if isinstance(href, str):
                        result.schema_refs.append(SchemaRef(href=href))

    # ------------------------------------------------------------------
    # Table streaming
    # ------------------------------------------------------------------

    def _stream_table(
        self,
        table_def: dict[str, Any],
        base_dir: str,
        result: StreamingParseResult,
        context_counter: int,
        unit_counter: int,
        context_cache: dict[str, str],
        unit_cache: dict[str, str],
    ) -> tuple[int, int, int]:
        """Stream a single CSV table using polars.

        Returns
        -------
        tuple[int, int, int]
            Updated (context_counter, unit_counter, bytes_scanned).
        """
        csv_url = table_def.get("url", "")
        if not csv_url:
            result.parse_errors.append("Table missing 'url'")
            return context_counter, unit_counter, 0

        csv_path = os.path.join(base_dir, csv_url)
        if not os.path.exists(csv_path):
            result.parse_errors.append(f"CSV not found: {csv_path}")
            return context_counter, unit_counter, 0

        file_size = os.path.getsize(csv_path)

        # Column definitions
        columns = table_def.get("columns", {})
        if not isinstance(columns, dict):
            columns = {}

        # Table-level dimensions
        table_dims = table_def.get("dimensions", {})
        if not isinstance(table_dims, dict):
            table_dims = {}

        # Use polars scan_csv for lazy evaluation
        try:
            lazy_frame = pl.scan_csv(
                csv_path,
                encoding="utf8",
                infer_schema_length=0,
            )
        except Exception as exc:  # noqa: BLE001
            result.parse_errors.append(f"Error scanning CSV {csv_path}: {exc}")
            return context_counter, unit_counter, file_size

        # Get total row count for batching
        try:
            total_rows = lazy_frame.select(pl.len()).collect().item()
        except Exception:  # noqa: BLE001
            total_rows = 0

        # Process in batches using slice
        for batch_start in range(0, max(total_rows, 1), _BATCH_SIZE):
            try:
                batch_df = lazy_frame.slice(
                    batch_start, _BATCH_SIZE
                ).collect()
            except Exception as exc:  # noqa: BLE001
                result.parse_errors.append(
                    f"Error collecting batch at row {batch_start}: {exc}"
                )
                continue

            col_names = batch_df.columns
            for row_idx in range(len(batch_df)):
                row_data: dict[str, str] = {}
                for col in col_names:
                    val = batch_df[col][row_idx]
                    row_data[col] = str(val) if val is not None else ""

                try:
                    context_counter, unit_counter = self._process_row(
                        row_data,
                        columns,
                        table_dims,
                        result,
                        context_counter,
                        unit_counter,
                        context_cache,
                        unit_cache,
                        batch_start + row_idx + 1,
                    )
                except Exception as exc:  # noqa: BLE001
                    result.parse_errors.append(
                        f"Error at row {batch_start + row_idx + 1}: {exc}"
                    )

        return context_counter, unit_counter, file_size

    # ------------------------------------------------------------------
    # Row processing
    # ------------------------------------------------------------------

    def _process_row(
        self,
        row_data: dict[str, str],
        columns: dict[str, Any],
        table_dims: dict[str, Any],
        result: StreamingParseResult,
        context_counter: int,
        unit_counter: int,
        context_cache: dict[str, str],
        unit_cache: dict[str, str],
        row_num: int,
    ) -> tuple[int, int]:
        """Process a single CSV row into FactReference entries."""
        # Build dimensions
        dims: dict[str, str] = {}
        dims.update({str(k): str(v) for k, v in table_dims.items()})

        for col_name, col_def in columns.items():
            if isinstance(col_def, dict):
                dim_prop = col_def.get("dimensions", {})
                if isinstance(dim_prop, dict):
                    for dk, dv in dim_prop.items():
                        if isinstance(dv, str) and dv.startswith("$"):
                            ref_col = dv.lstrip("$")
                            if ref_col in row_data:
                                dims[dk] = row_data[ref_col]
                        else:
                            dims[dk] = str(dv)

        # Context
        entity = dims.get("xbrl:entity", "")
        period = dims.get("xbrl:period", "")
        ctx_key = f"entity={entity}|period={period}"

        if ctx_key in context_cache:
            context_ref = context_cache[ctx_key]
        else:
            context_counter += 1
            context_ref = f"_csv_stream_ctx_{context_counter}"
            ctx = self._synthesize_context(context_ref, entity, period)
            result.contexts[context_ref] = ctx
            context_cache[ctx_key] = context_ref

        # Process value columns
        for col_name, col_def in columns.items():
            if not isinstance(col_def, dict):
                continue

            col_dims = col_def.get("dimensions", {})
            concept = ""
            if isinstance(col_dims, dict):
                concept = str(col_dims.get("xbrl:concept", ""))
            if not concept:
                continue

            value = row_data.get(col_name, "")
            if not value:
                continue

            concept_resolved = self._resolve_qname(
                concept, result.namespaces
            )

            # Unit
            unit_qname = dims.get("xbrl:unit", "")
            if isinstance(col_dims, dict):
                unit_qname = str(col_dims.get("xbrl:unit", unit_qname))

            unit_ref: Optional[str] = None
            is_numeric = bool(unit_qname)
            if unit_qname:
                if unit_qname in unit_cache:
                    unit_ref = unit_cache[unit_qname]
                else:
                    unit_counter += 1
                    unit_ref = f"_csv_stream_unit_{unit_counter}"
                    unit = RawUnit(id=unit_ref, measures=[unit_qname])
                    result.units[unit_ref] = unit
                    unit_cache[unit_qname] = unit_ref

            decimals_raw = col_def.get("decimals")
            decimals: Optional[str] = str(decimals_raw) if decimals_raw is not None else None

            value_bytes = value.encode("utf-8")

            ref = FactReference(
                index=self._fact_index,
                concept=concept_resolved,
                context_ref=context_ref,
                unit_ref=unit_ref,
                byte_offset=0,
                value_length=len(value_bytes),
                is_numeric=is_numeric,
                is_nil=False,
                decimals=decimals,
                source_line=row_num,
            )

            self._fact_store.add(ref)
            self._fact_index += 1

        return context_counter, unit_counter

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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

    @staticmethod
    def _synthesize_context(
        ctx_id: str, entity: str, period: str
    ) -> RawContext:
        """Create a RawContext from CSV dimension values."""
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
