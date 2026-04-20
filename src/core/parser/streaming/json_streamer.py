"""Streaming parser for xBRL-JSON using ijson.

Parses xBRL-JSON documents that exceed the DOM threshold using
``ijson`` for incremental JSON parsing. Facts are streamed one at
a time and stored in the provided ``FactStore``.

Spec references:
- xBRL-JSON 1.0 §2–4
- ijson documentation
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import ijson

from src.core.parser.streaming.fact_index import FactReference
from src.core.parser.streaming.fact_store import FactStore
from src.core.parser.streaming.memory_budget import MemoryBudget
from src.core.parser.streaming.sax_handler import StreamingParseResult
from src.core.parser.xml_parser import RawContext, RawUnit, SchemaRef

logger = logging.getLogger(__name__)


# OIM dimension keys
_CONCEPT_DIM = "xbrl:concept"
_ENTITY_DIM = "xbrl:entity"
_PERIOD_DIM = "xbrl:period"
_UNIT_DIM = "xbrl:unit"


class XBRLJSONStreamer:
    """Streaming parser for xBRL-JSON documents using ijson.

    Parses the JSON file incrementally without loading the entire
    document into memory. Facts are extracted from the ``facts``
    section and stored in the ``FactStore``.

    Parameters
    ----------
    file_path:
        Path to the xBRL-JSON file.
    fact_store:
        ``FactStore`` to hold parsed fact references.
    budget:
        ``MemoryBudget`` for memory tracking.
    """

    def __init__(
        self,
        file_path: str,
        fact_store: FactStore,
        budget: MemoryBudget,
    ) -> None:
        self._file_path = file_path
        self._fact_store = fact_store
        self._budget = budget
        self._fact_index = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self) -> StreamingParseResult:
        """Stream-parse an xBRL-JSON file using ijson.

        Two-pass approach:
        1. First pass: extract documentInfo (namespaces, taxonomy).
        2. Second pass: stream facts from the ``facts`` section.

        Returns
        -------
        StreamingParseResult
        """
        result = StreamingParseResult(fact_store=self._fact_store)
        start_time = time.monotonic()

        file_size = os.path.getsize(self._file_path)
        result.total_bytes_scanned = file_size

        # Pass 1: documentInfo
        try:
            self._extract_document_info(result)
        except Exception as exc:  # noqa: BLE001
            result.parse_errors.append(f"Error reading documentInfo: {exc}")

        # Pass 2: facts
        context_counter = 0
        unit_counter = 0
        context_cache: dict[str, str] = {}
        unit_cache: dict[str, str] = {}

        try:
            with open(self._file_path, "rb") as fh:
                # Stream facts using ijson prefix
                parser = ijson.items(fh, "facts")
                for facts_dict in parser:
                    if not isinstance(facts_dict, dict):
                        continue
                    for fact_id, fact_data in facts_dict.items():
                        try:
                            ctx_c, unit_c = self._process_fact(
                                fact_id,
                                fact_data,
                                result,
                                context_counter,
                                unit_counter,
                                context_cache,
                                unit_cache,
                            )
                            context_counter = ctx_c
                            unit_counter = unit_c
                        except Exception as exc:  # noqa: BLE001
                            result.parse_errors.append(
                                f"Error processing fact '{fact_id}': {exc}"
                            )
        except Exception as exc:  # noqa: BLE001
            # If prefix-based streaming fails, try key-value streaming
            try:
                self._stream_facts_kv(
                    result,
                    context_counter,
                    unit_counter,
                    context_cache,
                    unit_cache,
                )
            except Exception as exc2:  # noqa: BLE001
                result.parse_errors.append(
                    f"Error streaming facts: {exc}; fallback also failed: {exc2}"
                )

        result.total_facts = self._fact_store.count
        result.elapsed_seconds = time.monotonic() - start_time
        result.spill_occurred = (
            self._fact_store.storage_mode.value != "in_memory"
        )

        logger.info(
            "JSON streaming parse complete: %s facts in %.2fs",
            result.total_facts,
            result.elapsed_seconds,
        )

        return result

    # ------------------------------------------------------------------
    # Pass 1: documentInfo
    # ------------------------------------------------------------------

    def _extract_document_info(self, result: StreamingParseResult) -> None:
        """Extract namespaces and taxonomy from documentInfo."""
        with open(self._file_path, "rb") as fh:
            # Extract namespaces
            try:
                for prefix, event, value in ijson.parse(fh):
                    if prefix.startswith("documentInfo.namespaces.") and event == "string":
                        # prefix is like "documentInfo.namespaces.us-gaap"
                        ns_prefix = prefix.split(".")[-1]
                        result.namespaces[ns_prefix] = value
                    elif prefix.startswith("documentInfo.taxonomy.item") and event == "string":
                        result.schema_refs.append(SchemaRef(href=value))
                    elif prefix == "facts" and event == "start_map":
                        # Stop once we reach facts section
                        break
            except ijson.IncompleteJSONError:
                result.parse_errors.append(
                    "Incomplete JSON while reading documentInfo"
                )

    # ------------------------------------------------------------------
    # Pass 2: facts streaming
    # ------------------------------------------------------------------

    def _stream_facts_kv(
        self,
        result: StreamingParseResult,
        context_counter: int,
        unit_counter: int,
        context_cache: dict[str, str],
        unit_cache: dict[str, str],
    ) -> None:
        """Alternative fact streaming using key-value iteration."""
        with open(self._file_path, "rb") as fh:
            # Use kvitems to iterate over facts
            for fact_id, fact_data in ijson.kvitems(fh, "facts"):
                try:
                    ctx_c, unit_c = self._process_fact(
                        fact_id,
                        fact_data,
                        result,
                        context_counter,
                        unit_counter,
                        context_cache,
                        unit_cache,
                    )
                    context_counter = ctx_c
                    unit_counter = unit_c
                except Exception as exc:  # noqa: BLE001
                    result.parse_errors.append(
                        f"Error processing fact '{fact_id}': {exc}"
                    )

    def _process_fact(
        self,
        fact_id: str,
        fact_data: Any,
        result: StreamingParseResult,
        context_counter: int,
        unit_counter: int,
        context_cache: dict[str, str],
        unit_cache: dict[str, str],
    ) -> tuple[int, int]:
        """Process a single fact from the JSON stream."""
        if not isinstance(fact_data, dict):
            return context_counter, unit_counter

        dimensions = fact_data.get("dimensions", {})
        if not isinstance(dimensions, dict):
            return context_counter, unit_counter

        # Concept
        concept_qname = dimensions.get(_CONCEPT_DIM, "")
        concept = self._resolve_qname(concept_qname, result.namespaces)

        # Context
        entity = str(dimensions.get(_ENTITY_DIM, ""))
        period = str(dimensions.get(_PERIOD_DIM, ""))
        ctx_key = f"entity={entity}|period={period}"

        if ctx_key in context_cache:
            context_ref = context_cache[ctx_key]
        else:
            context_counter += 1
            context_ref = f"_stream_ctx_{context_counter}"
            ctx = self._synthesize_context(context_ref, entity, period)
            result.contexts[context_ref] = ctx
            context_cache[ctx_key] = context_ref

        # Unit
        unit_qname = dimensions.get(_UNIT_DIM, "")
        unit_ref: Optional[str] = None
        if unit_qname:
            if unit_qname in unit_cache:
                unit_ref = unit_cache[unit_qname]
            else:
                unit_counter += 1
                unit_ref = f"_stream_unit_{unit_counter}"
                unit = RawUnit(id=unit_ref, measures=[str(unit_qname)])
                result.units[unit_ref] = unit
                unit_cache[unit_qname] = unit_ref

        # Value
        value = fact_data.get("value", "")
        if value is None:
            value = ""
        else:
            value = str(value)

        is_nil = value == "" and fact_data.get("value") is None
        is_numeric = unit_ref is not None

        decimals_raw = fact_data.get("decimals")
        decimals: Optional[str] = str(decimals_raw) if decimals_raw is not None else None

        value_bytes = value.encode("utf-8")

        ref = FactReference(
            index=self._fact_index,
            concept=concept,
            context_ref=context_ref,
            unit_ref=unit_ref,
            byte_offset=0,
            value_length=len(value_bytes),
            is_numeric=is_numeric,
            is_nil=is_nil,
            decimals=decimals,
            id=str(fact_id),
            source_line=0,
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
        """Create a RawContext from OIM dimension values."""
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
