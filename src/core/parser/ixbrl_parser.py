"""iXBRL parser — extracts XBRL data from Inline XBRL (HTML) documents.

Handles ix:nonNumeric, ix:nonFraction, ix:fraction elements,
continuation chains, and inline transformations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

import structlog
from lxml import etree

from src.core.constants import NS_IX, NS_XBRLI, NS_LINK, NS_XLINK, NS_ISO4217
from src.core.exceptions import IXBRLParseError
from src.core.model.xbrl_model import (
    Context, DimensionMember, EntityIdentifier, Fact, Footnote,
    Period, SchemaRef, TaxonomyModel, Unit, UnitMeasure, XBRLInstance,
)
from src.core.parser.ixbrl_continuation import ContinuationResolver
from src.core.parser.ixbrl_transforms import IXBRLTransformEngine
from src.core.parser.transform_registry import TransformRegistry
from src.core.qname import format_qname
from src.core.types import InputFormat, PeriodType
from src.utils.datetime_utils import parse_iso_date
from src.utils.decimal_utils import XBRL_DECIMAL_CONTEXT
from src.utils.xml_utils import safe_parse_xml, namespace_map_from_element

logger = structlog.get_logger(__name__)


@dataclass
class InlineXBRLDocument:
    """Parsed iXBRL document — contains extracted XBRL data."""

    facts: list[Fact] = field(default_factory=list)
    contexts: dict[str, Context] = field(default_factory=dict)
    units: dict[str, Unit] = field(default_factory=dict)
    footnotes: list[Footnote] = field(default_factory=list)
    schema_refs: list[SchemaRef] = field(default_factory=list)
    namespaces: dict[str, str] = field(default_factory=dict)
    source_file: str = ""
    hidden_facts: list[Fact] = field(default_factory=list)

    def to_instance(
        self,
        taxonomy: TaxonomyModel | None = None,
    ) -> XBRLInstance:
        """Convert to a standard XBRLInstance."""
        return XBRLInstance(
            file_path=self.source_file,
            format_type=InputFormat.IXBRL_HTML,
            contexts=self.contexts,
            units=self.units,
            facts=self.facts + self.hidden_facts,
            footnotes=self.footnotes,
            taxonomy=taxonomy,
            schema_refs=self.schema_refs,
            namespaces=self.namespaces,
        )


class IXBRLParser:
    """Parse Inline XBRL (iXBRL) documents.

    Extracts XBRL facts from ix:nonNumeric, ix:nonFraction, and
    ix:fraction elements within an HTML/XHTML document. Handles
    continuation chains and applies inline transformations.
    """

    def __init__(
        self,
        transform_engine: IXBRLTransformEngine | None = None,
    ) -> None:
        self._transform_engine = transform_engine or IXBRLTransformEngine()
        self._continuation_resolver = ContinuationResolver()
        self._log = logger.bind(component="ixbrl_parser")

    def parse(self, file_path: str | Path) -> InlineXBRLDocument:
        """Parse an iXBRL document from a file.

        Args:
            file_path: Path to the iXBRL HTML/XHTML file.

        Returns:
            InlineXBRLDocument with extracted XBRL data.

        Raises:
            IXBRLParseError: If the document cannot be parsed.
            FileNotFoundError: If the file does not exist.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        self._log.info("ixbrl_parse_start", path=str(path))

        try:
            tree = safe_parse_xml(path, huge_tree=True)
        except Exception as exc:
            # Try HTML parsing as fallback
            try:
                parser = etree.HTMLParser(recover=True)
                tree = etree.parse(str(path), parser)
            except Exception as html_exc:
                raise IXBRLParseError(
                    message=f"Failed to parse iXBRL document: {exc}",
                    code="IXBRL-0001",
                    file_path=str(path),
                ) from html_exc

        root = tree.getroot()
        nsmap = namespace_map_from_element(root)

        doc = InlineXBRLDocument(
            source_file=str(path),
            namespaces=nsmap,
        )

        # Build continuation index
        continuation_index = self._continuation_resolver.build_continuation_index(root)

        # Extract resources from ix:resources or ix:header
        self._extract_resources(root, doc, nsmap)

        # Extract facts
        fact_counter = 0
        for elem in root.iter():
            tag = elem.tag if isinstance(elem.tag, str) else ""
            if tag == f"{{{NS_IX}}}nonFraction":
                fact = self._parse_non_fraction(
                    elem, nsmap, fact_counter, str(path), continuation_index
                )
                if fact is not None:
                    doc.facts.append(fact)
                    fact_counter += 1
            elif tag == f"{{{NS_IX}}}nonNumeric":
                fact = self._parse_non_numeric(
                    elem, nsmap, fact_counter, str(path), continuation_index
                )
                if fact is not None:
                    doc.facts.append(fact)
                    fact_counter += 1
            elif tag == f"{{{NS_IX}}}fraction":
                fact = self._parse_fraction(
                    elem, nsmap, fact_counter, str(path)
                )
                if fact is not None:
                    doc.facts.append(fact)
                    fact_counter += 1

        # Identify hidden facts (inside ix:hidden)
        for hidden_elem in root.iter(f"{{{NS_IX}}}hidden"):
            for child in hidden_elem:
                child_tag = child.tag if isinstance(child.tag, str) else ""
                if child_tag.startswith(f"{{{NS_IX}}}"):
                    for fact in doc.facts:
                        if fact.source_line == child.sourceline:
                            fact.is_hidden = True

        self._log.info(
            "ixbrl_parse_complete",
            facts=len(doc.facts),
            contexts=len(doc.contexts),
            units=len(doc.units),
        )
        return doc

    def _extract_resources(
        self,
        root: etree._Element,
        doc: InlineXBRLDocument,
        nsmap: dict[str, str],
    ) -> None:
        """Extract contexts, units, schema refs from ix:resources or ix:header."""
        # Look for ix:resources or ix:header
        resources_elem = None
        for tag_name in [f"{{{NS_IX}}}resources", f"{{{NS_IX}}}header"]:
            for elem in root.iter(tag_name):
                resources_elem = elem
                break
            if resources_elem is not None:
                break

        if resources_elem is None:
            # Fall back to searching the whole document
            resources_elem = root

        # Extract schema refs
        for elem in resources_elem.iter(f"{{{NS_LINK}}}schemaRef"):
            href = elem.get(f"{{{NS_XLINK}}}href", "")
            if href:
                doc.schema_refs.append(SchemaRef(href=href))

        # Extract contexts
        for elem in resources_elem.iter(f"{{{NS_XBRLI}}}context"):
            ctx = self._parse_context(elem, nsmap)
            if ctx is not None:
                doc.contexts[ctx.id] = ctx

        # Extract units
        for elem in resources_elem.iter(f"{{{NS_XBRLI}}}unit"):
            unit = self._parse_unit(elem, nsmap)
            if unit is not None:
                doc.units[unit.id] = unit

    def _parse_context(
        self, elem: etree._Element, nsmap: dict[str, str]
    ) -> Context | None:
        """Parse an xbrli:context element."""
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

        segment_dims: list[DimensionMember] = []
        segment = entity_elem.find(f"{{{NS_XBRLI}}}segment")
        if segment is not None:
            segment_dims = self._extract_dimensions(segment)

        scenario_dims: list[DimensionMember] = []
        scenario = elem.find(f"{{{NS_XBRLI}}}scenario")
        if scenario is not None:
            scenario_dims = self._extract_dimensions(scenario)

        return Context(
            id=ctx_id,
            entity=entity,
            period=period,
            segment_dims=segment_dims,
            scenario_dims=scenario_dims,
        )

    def _parse_period(self, elem: etree._Element) -> Period:
        """Parse a period element."""
        instant_elem = elem.find(f"{{{NS_XBRLI}}}instant")
        if instant_elem is not None:
            return Period(
                period_type=PeriodType.INSTANT,
                instant=parse_iso_date((instant_elem.text or "").strip()),
            )
        start_elem = elem.find(f"{{{NS_XBRLI}}}startDate")
        end_elem = elem.find(f"{{{NS_XBRLI}}}endDate")
        if start_elem is not None and end_elem is not None:
            return Period(
                period_type=PeriodType.DURATION,
                start_date=parse_iso_date((start_elem.text or "").strip()),
                end_date=parse_iso_date((end_elem.text or "").strip()),
            )
        if elem.find(f"{{{NS_XBRLI}}}forever") is not None:
            return Period(period_type=PeriodType.FOREVER)
        return Period(period_type=PeriodType.DURATION)

    def _extract_dimensions(
        self, container: etree._Element
    ) -> list[DimensionMember]:
        """Extract dimension members from a segment/scenario container."""
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
                typed_val = etree.tostring(child, encoding="unicode")
                dims.append(DimensionMember(
                    dimension=dim_qname,
                    typed_value=typed_val,
                    is_typed=True,
                ))
        return dims

    def _resolve_prefixed(self, text: str, elem: etree._Element) -> str:
        """Resolve a prefixed QName to Clark notation."""
        if not text or text.startswith("{"):
            return text
        parts = text.split(":", 1)
        if len(parts) == 2:
            prefix, local = parts
            ns = elem.nsmap.get(prefix, "")
            return format_qname(ns, local)
        return text

    def _parse_unit(
        self, elem: etree._Element, nsmap: dict[str, str]
    ) -> Unit | None:
        """Parse an xbrli:unit element."""
        unit_id = elem.get("id", "")
        if not unit_id:
            return None

        divide = elem.find(f"{{{NS_XBRLI}}}divide")
        if divide is not None:
            num_elem = divide.find(f"{{{NS_XBRLI}}}unitNumerator")
            den_elem = divide.find(f"{{{NS_XBRLI}}}unitDenominator")
            num = self._parse_measures(num_elem) if num_elem is not None else []
            den = self._parse_measures(den_elem) if den_elem is not None else []
            return Unit(id=unit_id, numerator_measures=num, denominator_measures=den)

        measures = self._parse_measures(elem)
        return Unit(id=unit_id, measures=measures)

    def _parse_measures(self, container: etree._Element) -> list[UnitMeasure]:
        """Parse measure elements within a unit."""
        result: list[UnitMeasure] = []
        for m in container.iter(f"{{{NS_XBRLI}}}measure"):
            text = (m.text or "").strip()
            if ":" in text:
                prefix, local = text.split(":", 1)
                ns = m.nsmap.get(prefix, "")
                result.append(UnitMeasure(namespace=ns, local_name=local))
            else:
                result.append(UnitMeasure(namespace="", local_name=text))
        return result

    def _parse_non_fraction(
        self,
        elem: etree._Element,
        nsmap: dict[str, str],
        counter: int,
        source_file: str,
        continuation_index: dict[str, etree._Element],
    ) -> Fact | None:
        """Parse an ix:nonFraction element (numeric fact)."""
        name_attr = elem.get("name", "")
        if not name_attr:
            return None

        concept_qname = self._resolve_prefixed(name_attr, elem)
        fact_id = elem.get("id", f"__ix_nf_{counter}")
        context_ref = elem.get("contextRef", "")
        unit_ref = elem.get("unitRef", "")
        nil_attr = elem.get(f"{{{NS_XBRLI}}}nil", elem.get("nil", ""))
        is_nil = nil_attr.lower() in ("true", "1")

        # Get display value
        display_value = "".join(elem.itertext()).strip() if not is_nil else ""

        # Apply transformation if format is specified
        format_attr = elem.get("format", "")
        scale_attr = elem.get("scale", "0")
        sign_attr = elem.get("sign", "")

        raw_value = display_value
        if format_attr and display_value:
            fmt_qname = self._resolve_prefixed(format_attr, elem)
            result = self._transform_engine.apply(
                fmt_qname, display_value,
                scale=int(scale_attr) if scale_attr else 0,
                sign=sign_attr,
            )
            if result.success:
                raw_value = result.value
        elif display_value:
            # No format — apply scale and sign directly
            raw_value = display_value
            if sign_attr == "-" and raw_value and not raw_value.startswith("-"):
                raw_value = f"-{raw_value}"
            if scale_attr and scale_attr != "0":
                try:
                    dec = XBRL_DECIMAL_CONTEXT.create_decimal(raw_value)
                    scaled = dec.scaleb(int(scale_attr), context=XBRL_DECIMAL_CONTEXT)
                    raw_value = str(scaled)
                except (InvalidOperation, ValueError):
                    pass

        # Parse numeric value
        numeric_value: Decimal | None = None
        if raw_value and not is_nil:
            try:
                numeric_value = XBRL_DECIMAL_CONTEXT.create_decimal(raw_value)
            except (InvalidOperation, ValueError):
                pass

        decimals_str = elem.get("decimals")
        parsed_decimals: int | str | None = None
        if decimals_str:
            parsed_decimals = "INF" if decimals_str.upper() == "INF" else (
                int(decimals_str) if decimals_str.lstrip("-").isdigit() else None
            )

        return Fact(
            id=fact_id,
            concept_qname=concept_qname,
            context_ref=context_ref or None,
            unit_ref=unit_ref or None,
            raw_value=raw_value,
            numeric_value=numeric_value,
            is_nil=is_nil,
            is_numeric=True,
            decimals=parsed_decimals,
            source_line=elem.sourceline,
            source_file=source_file,
        )

    def _parse_non_numeric(
        self,
        elem: etree._Element,
        nsmap: dict[str, str],
        counter: int,
        source_file: str,
        continuation_index: dict[str, etree._Element],
    ) -> Fact | None:
        """Parse an ix:nonNumeric element (non-numeric fact)."""
        name_attr = elem.get("name", "")
        if not name_attr:
            return None

        concept_qname = self._resolve_prefixed(name_attr, elem)
        fact_id = elem.get("id", f"__ix_nn_{counter}")
        context_ref = elem.get("contextRef", "")
        nil_attr = elem.get(f"{{{NS_XBRLI}}}nil", elem.get("nil", ""))
        is_nil = nil_attr.lower() in ("true", "1")

        # Get text content (resolve continuations)
        if not is_nil:
            raw_value = self._continuation_resolver.resolve_element(
                elem, continuation_index
            )
        else:
            raw_value = ""

        # Apply transformation if format is specified
        format_attr = elem.get("format", "")
        if format_attr and raw_value:
            fmt_qname = self._resolve_prefixed(format_attr, elem)
            result = self._transform_engine.apply(fmt_qname, raw_value)
            if result.success:
                raw_value = result.value

        lang = elem.get("{http://www.w3.org/XML/1998/namespace}lang")

        return Fact(
            id=fact_id,
            concept_qname=concept_qname,
            context_ref=context_ref or None,
            unit_ref=None,
            raw_value=raw_value.strip(),
            is_nil=is_nil,
            is_numeric=False,
            language=lang,
            source_line=elem.sourceline,
            source_file=source_file,
        )

    def _parse_fraction(
        self,
        elem: etree._Element,
        nsmap: dict[str, str],
        counter: int,
        source_file: str,
    ) -> Fact | None:
        """Parse an ix:fraction element."""
        name_attr = elem.get("name", "")
        if not name_attr:
            return None

        concept_qname = self._resolve_prefixed(name_attr, elem)
        fact_id = elem.get("id", f"__ix_fr_{counter}")
        context_ref = elem.get("contextRef", "")
        unit_ref = elem.get("unitRef", "")

        # Get numerator and denominator
        numerator_elem = elem.find(f"{{{NS_IX}}}numerator")
        denominator_elem = elem.find(f"{{{NS_IX}}}denominator")

        num_text = "".join(numerator_elem.itertext()).strip() if numerator_elem is not None else "0"
        den_text = "".join(denominator_elem.itertext()).strip() if denominator_elem is not None else "1"

        raw_value = f"{num_text}/{den_text}"

        # Compute numeric value
        numeric_value: Decimal | None = None
        try:
            num_dec = XBRL_DECIMAL_CONTEXT.create_decimal(num_text)
            den_dec = XBRL_DECIMAL_CONTEXT.create_decimal(den_text)
            if not den_dec.is_zero():
                numeric_value = XBRL_DECIMAL_CONTEXT.divide(num_dec, den_dec)
        except (InvalidOperation, ValueError):
            pass

        return Fact(
            id=fact_id,
            concept_qname=concept_qname,
            context_ref=context_ref or None,
            unit_ref=unit_ref or None,
            raw_value=raw_value,
            numeric_value=numeric_value,
            is_nil=False,
            is_numeric=True,
            source_line=elem.sourceline,
            source_file=source_file,
        )
