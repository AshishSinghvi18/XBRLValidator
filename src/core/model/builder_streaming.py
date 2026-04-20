"""Streaming model builder — SAX-based builder for large XBRL documents.

Implements Rule 2: Streaming First — files > 100 MB use streaming parsing
to maintain constant memory usage regardless of document size.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import IO

import structlog
from lxml import etree

from src.core.constants import NS_XBRLI, NS_LINK
from src.core.model.xbrl_model import (
    Context, EntityIdentifier, Fact, Footnote, Period,
    SchemaRef, TaxonomyModel, Unit, UnitMeasure, XBRLInstance,
)
from src.core.qname import format_qname
from src.core.types import InputFormat, PeriodType
from src.utils.datetime_utils import parse_iso_date
from src.utils.decimal_utils import XBRL_DECIMAL_CONTEXT

logger = structlog.get_logger(__name__)


@dataclass
class StreamingBuildState:
    """Mutable state accumulated during streaming parse."""
    contexts: dict[str, Context] = field(default_factory=dict)
    units: dict[str, Unit] = field(default_factory=dict)
    facts: list[Fact] = field(default_factory=list)
    footnotes: list[Footnote] = field(default_factory=list)
    schema_refs: list[SchemaRef] = field(default_factory=list)
    fact_counter: int = 0
    current_depth: int = 0
    errors: list[str] = field(default_factory=list)


class StreamingModelBuilder:
    """SAX-based model builder for large XBRL instance documents.

    Uses lxml iterparse for memory-efficient processing of large files.
    Maintains constant memory by processing elements individually and
    clearing them after extraction.
    """

    def __init__(self, chunk_size: int = 8 * 1024 * 1024) -> None:
        self._chunk_size = chunk_size
        self._log = logger.bind(component="streaming_model_builder")

    def build(
        self,
        source: str | IO[bytes],
        taxonomy: TaxonomyModel | None = None,
        source_file: str = "",
    ) -> XBRLInstance:
        """Build an XBRLInstance by streaming the source document."""
        self._log.info("streaming_build_start", source=source_file)
        state = StreamingBuildState()

        events = ("end",)
        context_tag = f"{{{NS_XBRLI}}}context"
        unit_tag = f"{{{NS_XBRLI}}}unit"
        schema_ref_tag = f"{{{NS_LINK}}}schemaRef"

        try:
            ctx_iter = etree.iterparse(
                source, events=events, huge_tree=True,
                no_network=True, resolve_entities=False,
            )
            root_nsmap: dict[str, str] = {}

            for event, elem in ctx_iter:
                tag = elem.tag
                if not isinstance(tag, str):
                    elem.clear()
                    continue

                # Capture root namespace map on first element
                if not root_nsmap and elem.nsmap:
                    for prefix, uri in elem.nsmap.items():
                        root_nsmap[prefix if prefix is not None else ""] = uri

                if tag == context_tag:
                    ctx = self._parse_context(elem)
                    if ctx is not None:
                        state.contexts[ctx.id] = ctx
                    elem.clear()
                elif tag == unit_tag:
                    unit = self._parse_unit(elem)
                    if unit is not None:
                        state.units[unit.id] = unit
                    elem.clear()
                elif tag == schema_ref_tag:
                    href = elem.get(f"{{http://www.w3.org/1999/xlink}}href", "")
                    if href:
                        state.schema_refs.append(SchemaRef(href=href))
                    elem.clear()
                else:
                    # Check if it's a fact element (not in XBRLI/LINK ns)
                    if (not tag.startswith(f"{{{NS_XBRLI}}}")
                            and not tag.startswith(f"{{{NS_LINK}}}")):
                        fact = self._parse_fact(elem, state.fact_counter, source_file, taxonomy)
                        if fact is not None:
                            state.facts.append(fact)
                            state.fact_counter += 1
                    elem.clear()

        except etree.XMLSyntaxError as exc:
            self._log.error("streaming_parse_error", error=str(exc))
            state.errors.append(str(exc))

        instance = XBRLInstance(
            file_path=source_file,
            format_type=InputFormat.XBRL_XML,
            contexts=state.contexts,
            units=state.units,
            facts=state.facts,
            footnotes=state.footnotes,
            taxonomy=taxonomy,
            schema_refs=state.schema_refs,
            namespaces=root_nsmap,
        )

        self._log.info(
            "streaming_build_complete",
            contexts=len(state.contexts),
            units=len(state.units),
            facts=len(state.facts),
        )
        return instance

    def iter_facts(
        self,
        source: str | IO[bytes],
        taxonomy: TaxonomyModel | None = None,
        source_file: str = "",
    ) -> Iterator[Fact]:
        """Yield facts one by one for truly streaming processing."""
        counter = 0
        ctx_iter = etree.iterparse(
            source, events=("end",), huge_tree=True,
            no_network=True, resolve_entities=False,
        )
        for _event, elem in ctx_iter:
            tag = elem.tag
            if not isinstance(tag, str):
                elem.clear()
                continue
            if (not tag.startswith(f"{{{NS_XBRLI}}}")
                    and not tag.startswith(f"{{{NS_LINK}}}")):
                fact = self._parse_fact(elem, counter, source_file, taxonomy)
                if fact is not None:
                    yield fact
                    counter += 1
            elem.clear()

    def _parse_context(self, elem: etree._Element) -> Context | None:
        ctx_id = elem.get("id", "")
        if not ctx_id:
            return None
        entity_elem = elem.find(f"{{{NS_XBRLI}}}entity")
        if entity_elem is None:
            return None
        ident_elem = entity_elem.find(f"{{{NS_XBRLI}}}identifier")
        if ident_elem is None:
            return None
        entity = EntityIdentifier(
            scheme=ident_elem.get("scheme", ""),
            identifier=(ident_elem.text or "").strip(),
        )
        period_elem = elem.find(f"{{{NS_XBRLI}}}period")
        if period_elem is None:
            return None
        period = self._parse_period(period_elem)
        return Context(id=ctx_id, entity=entity, period=period)

    def _parse_period(self, elem: etree._Element) -> Period:
        instant = elem.find(f"{{{NS_XBRLI}}}instant")
        if instant is not None:
            return Period(
                period_type=PeriodType.INSTANT,
                instant=parse_iso_date((instant.text or "").strip()),
            )
        start = elem.find(f"{{{NS_XBRLI}}}startDate")
        end = elem.find(f"{{{NS_XBRLI}}}endDate")
        if start is not None and end is not None:
            return Period(
                period_type=PeriodType.DURATION,
                start_date=parse_iso_date((start.text or "").strip()),
                end_date=parse_iso_date((end.text or "").strip()),
            )
        if elem.find(f"{{{NS_XBRLI}}}forever") is not None:
            return Period(period_type=PeriodType.FOREVER)
        return Period(period_type=PeriodType.DURATION)

    def _parse_unit(self, elem: etree._Element) -> Unit | None:
        unit_id = elem.get("id", "")
        if not unit_id:
            return None
        measures: list[UnitMeasure] = []
        for m in elem.iter(f"{{{NS_XBRLI}}}measure"):
            text = (m.text or "").strip()
            if ":" in text:
                prefix, local = text.split(":", 1)
                ns = m.nsmap.get(prefix, "")
                measures.append(UnitMeasure(namespace=ns, local_name=local))
            else:
                measures.append(UnitMeasure(namespace="", local_name=text))
        return Unit(id=unit_id, measures=measures)

    def _parse_fact(
        self,
        elem: etree._Element,
        counter: int,
        source_file: str,
        taxonomy: TaxonomyModel | None,
    ) -> Fact | None:
        tag = elem.tag
        if not isinstance(tag, str):
            return None
        if tag.startswith("{"):
            ns, local = tag[1:].split("}", 1)
            concept_qname = format_qname(ns, local)
        else:
            concept_qname = tag

        ctx_ref = elem.get("contextRef")
        unit_ref = elem.get("unitRef")
        # Skip structural elements without context
        if ctx_ref is None and unit_ref is None and len(elem) == 0:
            raw = (elem.text or "").strip()
            if not raw:
                return None

        fact_id = elem.get("id", f"__stream_{counter}")
        is_nil = (elem.get("{http://www.w3.org/2001/XMLSchema-instance}nil", "")).lower() in ("true", "1")
        raw_value = "".join(elem.itertext()).strip() if not is_nil else ""
        is_numeric = unit_ref is not None
        numeric_value: Decimal | None = None
        if is_numeric and raw_value:
            try:
                numeric_value = XBRL_DECIMAL_CONTEXT.create_decimal(raw_value)
            except (InvalidOperation, ValueError):
                pass

        decimals_str = elem.get("decimals")
        parsed_decimals: int | str | None = None
        if decimals_str:
            parsed_decimals = "INF" if decimals_str.upper() == "INF" else int(decimals_str) if decimals_str.lstrip("-").isdigit() else None

        return Fact(
            id=fact_id,
            concept_qname=concept_qname,
            context_ref=ctx_ref,
            unit_ref=unit_ref,
            raw_value=raw_value,
            numeric_value=numeric_value,
            is_nil=is_nil,
            is_numeric=is_numeric,
            decimals=parsed_decimals,
            source_line=elem.sourceline,
            source_file=source_file,
        )
