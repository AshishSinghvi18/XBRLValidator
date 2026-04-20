"""DOM model builder — transforms raw parsed XML into the canonical XBRLInstance model."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass, field

import structlog
from lxml import etree

from src.core.constants import (
    NS_XBRLI, NS_LINK, NS_XLINK, NS_ISO4217, NS_XBRLDI,
)
from src.core.exceptions import ParseError
from src.core.model.xbrl_model import (
    Context, DimensionMember, EntityIdentifier, Fact, Footnote,
    LinkbaseRef, Period, SchemaRef, TaxonomyModel, Unit, UnitMeasure,
    XBRLInstance,
)
from src.core.qname import format_qname, split_clark
from src.core.types import InputFormat, PeriodType, QName
from src.utils.datetime_utils import parse_iso_date
from src.utils.decimal_utils import XBRL_DECIMAL_CONTEXT

logger = structlog.get_logger(__name__)


@dataclass
class RawXBRLDocument:
    """Intermediate representation from XMLParser."""
    root: etree._Element
    namespaces: dict[str, str] = field(default_factory=dict)
    source_file: str = ""
    source_size: int = 0
    schema_refs: list[str] = field(default_factory=list)
    linkbase_refs: list[str] = field(default_factory=list)
    doc_encoding: str = "utf-8"


class ModelBuilder:
    """Build XBRLInstance from a RawXBRLDocument and optional taxonomy."""

    def __init__(self) -> None:
        self._log = logger.bind(component="model_builder")

    def build(
        self,
        raw: RawXBRLDocument,
        taxonomy: TaxonomyModel | None = None,
    ) -> XBRLInstance:
        """Parse all contexts, units, facts, footnotes from the raw DOM."""
        self._log.info("model_build_start", source=raw.source_file)
        root = raw.root
        nsmap = raw.namespaces

        instance = XBRLInstance(
            file_path=raw.source_file,
            format_type=InputFormat.XBRL_XML,
            taxonomy=taxonomy,
            namespaces=nsmap,
        )

        # Schema refs
        for href in raw.schema_refs:
            instance.schema_refs.append(SchemaRef(href=href))

        # Contexts
        for ctx_elem in root.iter(f"{{{NS_XBRLI}}}context"):
            ctx = self._build_context(ctx_elem, nsmap)
            if ctx is not None:
                instance.contexts[ctx.id] = ctx

        # Units
        for unit_elem in root.iter(f"{{{NS_XBRLI}}}unit"):
            unit = self._build_unit(unit_elem, nsmap)
            if unit is not None:
                instance.units[unit.id] = unit

        # Facts — items that are direct children of xbrli:xbrl
        fact_counter = 0
        for child in root:
            tag = child.tag
            if isinstance(tag, str) and not tag.startswith(f"{{{NS_XBRLI}}}") and not tag.startswith(f"{{{NS_LINK}}}"):
                fact = self._build_fact(child, nsmap, fact_counter, raw.source_file, taxonomy)
                if fact is not None:
                    instance.facts.append(fact)
                    fact_counter += 1

        # Footnotes
        for fn_link in root.iter(f"{{{NS_LINK}}}footnoteLink"):
            footnotes = self._build_footnotes(fn_link, nsmap)
            instance.footnotes.extend(footnotes)

        self._log.info(
            "model_build_complete",
            contexts=len(instance.contexts),
            units=len(instance.units),
            facts=len(instance.facts),
            footnotes=len(instance.footnotes),
        )
        return instance

    def _build_context(
        self, elem: etree._Element, nsmap: dict[str, str]
    ) -> Context | None:
        ctx_id = elem.get("id", "")
        if not ctx_id:
            return None

        # Entity
        entity_elem = elem.find(f"{{{NS_XBRLI}}}entity")
        if entity_elem is None:
            return None
        ident_elem = entity_elem.find(f"{{{NS_XBRLI}}}identifier")
        if ident_elem is None:
            return None
        scheme = ident_elem.get("scheme", "")
        identifier = (ident_elem.text or "").strip()
        entity = EntityIdentifier(scheme=scheme, identifier=identifier)

        # Period
        period_elem = elem.find(f"{{{NS_XBRLI}}}period")
        if period_elem is None:
            return None
        period = self._build_period(period_elem)

        # Segment dimensions
        segment_dims: list[DimensionMember] = []
        segment = entity_elem.find(f"{{{NS_XBRLI}}}segment")
        if segment is not None:
            segment_dims = self._extract_dimensions(segment, nsmap)

        # Scenario dimensions
        scenario_dims: list[DimensionMember] = []
        scenario = elem.find(f"{{{NS_XBRLI}}}scenario")
        if scenario is not None:
            scenario_dims = self._extract_dimensions(scenario, nsmap)

        return Context(
            id=ctx_id,
            entity=entity,
            period=period,
            segment_dims=segment_dims,
            scenario_dims=scenario_dims,
        )

    def _build_period(self, elem: etree._Element) -> Period:
        instant_elem = elem.find(f"{{{NS_XBRLI}}}instant")
        if instant_elem is not None:
            d = parse_iso_date((instant_elem.text or "").strip())
            return Period(period_type=PeriodType.INSTANT, instant=d)

        start_elem = elem.find(f"{{{NS_XBRLI}}}startDate")
        end_elem = elem.find(f"{{{NS_XBRLI}}}endDate")
        if start_elem is not None and end_elem is not None:
            sd = parse_iso_date((start_elem.text or "").strip())
            ed = parse_iso_date((end_elem.text or "").strip())
            return Period(period_type=PeriodType.DURATION, start_date=sd, end_date=ed)

        forever = elem.find(f"{{{NS_XBRLI}}}forever")
        if forever is not None:
            return Period(period_type=PeriodType.FOREVER)

        return Period(period_type=PeriodType.DURATION)

    def _extract_dimensions(
        self, container: etree._Element, nsmap: dict[str, str]
    ) -> list[DimensionMember]:
        dims: list[DimensionMember] = []
        for child in container:
            tag = child.tag if isinstance(child.tag, str) else ""
            if "explicitMember" in tag:
                dim_attr = child.get("dimension", "")
                dim_qname = self._resolve_prefixed(dim_attr, child)
                member_text = (child.text or "").strip()
                member_qname = self._resolve_prefixed(member_text, child)
                dims.append(DimensionMember(
                    dimension=dim_qname,
                    member=member_qname,
                    is_typed=False,
                ))
            elif "typedMember" in tag:
                dim_attr = child.get("dimension", "")
                dim_qname = self._resolve_prefixed(dim_attr, child)
                typed_val = etree.tostring(child, encoding="unicode", method="xml")
                dims.append(DimensionMember(
                    dimension=dim_qname,
                    typed_value=typed_val,
                    is_typed=True,
                ))
        return dims

    def _resolve_prefixed(self, text: str, elem: etree._Element) -> QName:
        """Resolve a prefixed QName to Clark notation using element's nsmap."""
        if not text or text.startswith("{"):
            return text
        parts = text.split(":", 1)
        if len(parts) == 2:
            prefix, local = parts
            ns = elem.nsmap.get(prefix, "")
            return format_qname(ns, local)
        return text

    def _build_unit(
        self, elem: etree._Element, nsmap: dict[str, str]
    ) -> Unit | None:
        unit_id = elem.get("id", "")
        if not unit_id:
            return None

        divide = elem.find(f"{{{NS_XBRLI}}}divide")
        if divide is not None:
            num_elem = divide.find(f"{{{NS_XBRLI}}}unitNumerator")
            den_elem = divide.find(f"{{{NS_XBRLI}}}unitDenominator")
            num_measures = self._parse_measures(num_elem, elem) if num_elem is not None else []
            den_measures = self._parse_measures(den_elem, elem) if den_elem is not None else []
            return Unit(
                id=unit_id,
                numerator_measures=num_measures,
                denominator_measures=den_measures,
            )

        measures = self._parse_measures(elem, elem)
        return Unit(id=unit_id, measures=measures)

    def _parse_measures(
        self, container: etree._Element, unit_elem: etree._Element
    ) -> list[UnitMeasure]:
        result: list[UnitMeasure] = []
        for m in container.iter(f"{{{NS_XBRLI}}}measure"):
            text = (m.text or "").strip()
            if ":" in text:
                prefix, local = text.split(":", 1)
                ns = m.nsmap.get(prefix, unit_elem.nsmap.get(prefix, ""))
                result.append(UnitMeasure(namespace=ns, local_name=local))
            else:
                result.append(UnitMeasure(namespace="", local_name=text))
        return result

    def _build_fact(
        self,
        elem: etree._Element,
        nsmap: dict[str, str],
        counter: int,
        source_file: str,
        taxonomy: TaxonomyModel | None,
    ) -> Fact | None:
        tag = elem.tag
        if not isinstance(tag, str):
            return None

        ns, local = split_clark(tag) if tag.startswith("{") else ("", tag)
        concept_qname = format_qname(ns, local)

        fact_id = elem.get("id", f"__auto_{counter}")
        context_ref = elem.get("contextRef")
        unit_ref = elem.get("unitRef")
        nil_attr = elem.get(f"{{{NS_XBRLI}}}nil") or elem.get("nil", "")
        is_nil = nil_attr.lower() in ("true", "1")

        raw_value = "".join(elem.itertext()).strip() if not is_nil else ""
        decimals_str = elem.get("decimals")
        precision_str = elem.get("precision")
        lang = elem.get("{http://www.w3.org/XML/1998/namespace}lang")

        # Determine if numeric
        is_numeric = unit_ref is not None
        if taxonomy is not None:
            is_numeric = taxonomy.is_numeric_concept(concept_qname) or is_numeric

        # Parse numeric value
        numeric_value: Decimal | None = None
        if is_numeric and raw_value and not is_nil:
            try:
                numeric_value = XBRL_DECIMAL_CONTEXT.create_decimal(raw_value)
            except (InvalidOperation, ValueError):
                numeric_value = None

        # Parse decimals
        parsed_decimals: int | str | None = None
        if decimals_str is not None:
            if decimals_str.upper() == "INF":
                parsed_decimals = "INF"
            else:
                try:
                    parsed_decimals = int(decimals_str)
                except ValueError:
                    parsed_decimals = None

        # Parse precision
        parsed_precision: int | str | None = None
        if precision_str is not None:
            if precision_str.upper() == "INF":
                parsed_precision = "INF"
            else:
                try:
                    parsed_precision = int(precision_str)
                except ValueError:
                    parsed_precision = None

        # Detect tuples
        is_tuple = len(elem) > 0 and context_ref is None and unit_ref is None
        if is_tuple and not any(
            isinstance(c.tag, str) and not c.tag.startswith(f"{{{NS_XBRLI}}}")
            for c in elem
        ):
            is_tuple = False

        return Fact(
            id=fact_id,
            concept_qname=concept_qname,
            context_ref=context_ref,
            unit_ref=unit_ref,
            raw_value=raw_value,
            numeric_value=numeric_value,
            is_nil=is_nil,
            is_numeric=is_numeric,
            is_tuple=is_tuple,
            decimals=parsed_decimals,
            precision=parsed_precision,
            language=lang,
            source_line=elem.sourceline,
            source_file=source_file,
        )

    def _build_footnotes(
        self, fn_link: etree._Element, nsmap: dict[str, str]
    ) -> list[Footnote]:
        footnotes: list[Footnote] = []
        # Collect locators
        locs: dict[str, str] = {}
        for loc in fn_link.iter(f"{{{NS_LINK}}}loc"):
            label = loc.get(f"{{{NS_XLINK}}}label", "")
            href = loc.get(f"{{{NS_XLINK}}}href", "")
            if label and href:
                locs[label] = href

        # Collect arcs
        arc_map: dict[str, list[str]] = {}
        for arc in fn_link.iter(f"{{{NS_LINK}}}footnoteArc"):
            from_label = arc.get(f"{{{NS_XLINK}}}from", "")
            to_label = arc.get(f"{{{NS_XLINK}}}to", "")
            if from_label and to_label:
                arc_map.setdefault(to_label, []).append(from_label)

        # Collect footnotes
        for fn in fn_link.iter(f"{{{NS_LINK}}}footnote"):
            fn_label = fn.get(f"{{{NS_XLINK}}}label", "")
            fn_id = fn.get("id", fn_label)
            role = fn.get(f"{{{NS_XLINK}}}role", "")
            lang = fn.get("{http://www.w3.org/XML/1998/namespace}lang", "")
            content = "".join(fn.itertext()).strip()

            fact_refs: list[str] = []
            for from_label in arc_map.get(fn_label, []):
                href = locs.get(from_label, "")
                if href:
                    fact_id = href.split("#", 1)[-1] if "#" in href else href
                    fact_refs.append(fact_id)

            footnotes.append(Footnote(
                id=fn_id,
                role=role,
                language=lang,
                content=content,
                fact_refs=fact_refs,
                source_line=fn.sourceline,
            ))

        return footnotes
