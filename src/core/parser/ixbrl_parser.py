"""Parser for inline XBRL (iXBRL) HTML documents.

Extracts XBRL facts, contexts, and units from iXBRL documents where
the XBRL data is embedded within HTML markup using the ``ix:`` namespace.

Parsing phases:
1. HTML parse (lxml.html)
2. ix:header extraction (contexts, units, schemaRefs)
3. Body walk for ix:nonFraction, ix:nonNumeric, ix:fraction, ix:tuple
4. Transform application (format attr → TransformRegistry)
5. Continuation chain resolution
6. Hidden fact classification

Spec references:
- Inline XBRL 1.1 §4 (document structure)
- Inline XBRL 1.1 §5 (header element)
- Inline XBRL 1.1 §6 (nonFraction, nonNumeric)
- Inline XBRL 1.1 §7 (continuation)
- Inline XBRL 1.1 §8 (transforms)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from lxml import etree, html as lxml_html

from src.core.constants import NS_IX, NS_LINK, NS_XBRLI, NS_XLINK, NS_XSI
from src.core.exceptions import ParseError
from src.core.parser.transform_registry import TransformRegistry
from src.core.parser.xml_parser import (
    LinkbaseRef,
    RawContext,
    RawFact,
    RawUnit,
    RawXBRLDocument,
    SchemaRef,
)
from src.utils.xml_utils import (
    get_element_line,
    get_namespace,
    safe_xml_parser,
    strip_namespace,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Clark-notation constants for ix: namespace
# ---------------------------------------------------------------------------

_IX_HEADER = f"{{{NS_IX}}}header"
_IX_REFERENCES = f"{{{NS_IX}}}references"
_IX_RESOURCES = f"{{{NS_IX}}}resources"
_IX_HIDDEN = f"{{{NS_IX}}}hidden"
_IX_NON_FRACTION = f"{{{NS_IX}}}nonFraction"
_IX_NON_NUMERIC = f"{{{NS_IX}}}nonNumeric"
_IX_FRACTION = f"{{{NS_IX}}}fraction"
_IX_TUPLE = f"{{{NS_IX}}}tuple"
_IX_CONTINUATION = f"{{{NS_IX}}}continuation"
_IX_NUMERATOR = f"{{{NS_IX}}}numerator"
_IX_DENOMINATOR = f"{{{NS_IX}}}denominator"
_IX_EXCLUDE = f"{{{NS_IX}}}exclude"

_XBRLI_CONTEXT = f"{{{NS_XBRLI}}}context"
_XBRLI_UNIT = f"{{{NS_XBRLI}}}unit"
_LINK_SCHEMA_REF = f"{{{NS_LINK}}}schemaRef"
_LINK_LINKBASE_REF = f"{{{NS_LINK}}}linkbaseRef"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class InlineFact:
    """A single inline XBRL fact extracted from the HTML document.

    Attributes:
        concept: Qualified concept name.
        context_ref: Reference to the context element.
        unit_ref: Reference to the unit element (numeric only).
        display_value: The human-readable value as displayed in HTML.
        xbrl_value: The transformed XBRL-canonical value.
        format_attr: The ``@format`` attribute (transform QName).
        scale: Scale factor from ``@scale`` attribute.
        sign: Sign modifier from ``@sign`` attribute.
        decimals: Decimals attribute.
        precision: Precision attribute.
        id: Fact element id.
        is_nil: Whether xsi:nil="true".
        source_line: Source line in the original file.
        continued_at: ID of the continuation element (if any).
        is_hidden: Whether the fact is inside ``ix:hidden``.
        order: Order attribute for tuples.
    """

    concept: str = ""
    context_ref: str = ""
    unit_ref: Optional[str] = None
    display_value: str = ""
    xbrl_value: str = ""
    format_attr: Optional[str] = None
    scale: Optional[str] = None
    sign: Optional[str] = None
    decimals: Optional[str] = None
    precision: Optional[str] = None
    id: Optional[str] = None
    is_nil: bool = False
    source_line: int = 0
    continued_at: Optional[str] = None
    is_hidden: bool = False
    order: Optional[str] = None


@dataclass
class InlineXBRLDocument:
    """Intermediate representation of a parsed iXBRL document.

    Attributes:
        file_path: Path to the source file.
        namespaces: Namespace prefix → URI mapping.
        schema_refs: Taxonomy schema references.
        linkbase_refs: Linkbase references.
        contexts: Context id → RawContext mapping.
        units: Unit id → RawUnit mapping.
        inline_facts: All extracted inline facts.
        hidden_facts: Facts from ix:hidden section.
        continuations: Continuation id → text content mapping.
        parse_errors: List of non-fatal error messages.
    """

    file_path: str = ""
    namespaces: dict[str, str] = field(default_factory=dict)
    schema_refs: list[SchemaRef] = field(default_factory=list)
    linkbase_refs: list[LinkbaseRef] = field(default_factory=list)
    contexts: dict[str, RawContext] = field(default_factory=dict)
    units: dict[str, RawUnit] = field(default_factory=dict)
    inline_facts: list[InlineFact] = field(default_factory=list)
    hidden_facts: list[InlineFact] = field(default_factory=list)
    continuations: dict[str, str] = field(default_factory=dict)
    parse_errors: list[str] = field(default_factory=list)


class IXBRLParser:
    """Parser for inline XBRL (iXBRL) HTML documents.

    Parameters
    ----------
    transform_registry:
        Optional transform registry. If ``None`` a default registry
        with all built-in transforms is created.
    """

    def __init__(
        self,
        transform_registry: TransformRegistry | None = None,
    ) -> None:
        self._transforms = transform_registry or TransformRegistry()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, file_path: str) -> InlineXBRLDocument:
        """Parse an iXBRL HTML file.

        Phases:
        1. HTML parse (lxml.html)
        2. ix:header extraction (contexts, units, schemaRefs)
        3. Body walk for ix:nonFraction, ix:nonNumeric, ix:fraction,
           ix:tuple
        4. Transform application (format attr → TransformRegistry)
        5. Continuation chain resolution
        6. Hidden fact classification

        Parameters
        ----------
        file_path:
            Path to the iXBRL HTML file.

        Returns
        -------
        InlineXBRLDocument

        Raises
        ------
        ParseError
            On fatal HTML parsing errors.
        """
        doc = InlineXBRLDocument(file_path=file_path)

        try:
            tree = self._parse_html(file_path)
        except Exception as exc:  # noqa: BLE001
            raise ParseError(
                f"Failed to parse iXBRL HTML: {exc}",
                file_path=file_path,
                line=0,
                column=0,
            ) from exc

        root = tree.getroot() if hasattr(tree, "getroot") else tree

        # Collect namespaces from root
        self._collect_namespaces(root, doc)

        # Phase 2: Extract ix:header
        self._extract_headers(root, doc)

        # Phase 3 & 4: Walk body for inline facts
        self._walk_for_facts(root, doc, is_hidden=False)

        # Phase 5: Resolve continuation chains
        self._resolve_continuations(root, doc)

        # Phase 6: Classify hidden facts
        self._classify_hidden(doc)

        return doc

    def to_raw_xbrl(self, doc: InlineXBRLDocument) -> RawXBRLDocument:
        """Convert an ``InlineXBRLDocument`` to ``RawXBRLDocument``.

        Transforms all inline facts into standard ``RawFact`` instances
        suitable for downstream validation.

        Parameters
        ----------
        doc:
            The parsed iXBRL document.

        Returns
        -------
        RawXBRLDocument
        """
        raw = RawXBRLDocument(
            file_path=doc.file_path,
            namespaces=dict(doc.namespaces),
            schema_refs=list(doc.schema_refs),
            linkbase_refs=list(doc.linkbase_refs),
            contexts=dict(doc.contexts),
            units=dict(doc.units),
            parse_errors=list(doc.parse_errors),
        )

        for ifact in doc.inline_facts:
            raw_fact = RawFact(
                concept=ifact.concept,
                context_ref=ifact.context_ref,
                unit_ref=ifact.unit_ref,
                value=ifact.xbrl_value,
                decimals=ifact.decimals,
                precision=ifact.precision,
                id=ifact.id,
                is_nil=ifact.is_nil,
                source_line=ifact.source_line,
                namespace=get_namespace(ifact.concept) if ifact.concept.startswith("{") else "",
            )
            raw.facts.append(raw_fact)

        return raw

    # ------------------------------------------------------------------
    # Phase 1: HTML parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_html(file_path: str) -> etree._ElementTree:
        """Parse HTML file, trying XML-mode first for namespace support."""
        # Try as well-formed XHTML first (preserves namespaces)
        try:
            parser = safe_xml_parser()
            tree = etree.parse(file_path, parser)  # noqa: S320
            return tree
        except etree.XMLSyntaxError:
            pass

        # Fall back to lxml HTML parser (more lenient)
        tree = lxml_html.parse(file_path)
        return tree

    @staticmethod
    def _collect_namespaces(
        root: etree._Element, doc: InlineXBRLDocument
    ) -> None:
        """Collect all namespace declarations from the root element."""
        nsmap = root.nsmap if hasattr(root, "nsmap") and root.nsmap else {}
        for prefix, uri in nsmap.items():
            if prefix is None:
                doc.namespaces[""] = uri
            else:
                doc.namespaces[prefix] = uri

        # Also walk descendant namespace maps for additional prefixes
        for elem in root.iter():
            if hasattr(elem, "nsmap") and elem.nsmap:
                for prefix, uri in elem.nsmap.items():
                    if prefix is not None and prefix not in doc.namespaces:
                        doc.namespaces[prefix] = uri

    # ------------------------------------------------------------------
    # Phase 2: ix:header extraction
    # ------------------------------------------------------------------

    def _extract_headers(
        self, root: etree._Element, doc: InlineXBRLDocument
    ) -> None:
        """Find and process all ix:header elements."""
        for header in self._find_elements(root, _IX_HEADER):
            self._process_header(header, doc)

    def _process_header(
        self, header: etree._Element, doc: InlineXBRLDocument
    ) -> None:
        """Process a single ix:header element."""
        # References (schemaRef, linkbaseRef)
        for refs_elem in self._find_elements(header, _IX_REFERENCES):
            for child in refs_elem:
                if not isinstance(child.tag, str):
                    continue
                try:
                    if child.tag == _LINK_SCHEMA_REF:
                        href = child.get(f"{{{NS_XLINK}}}href", "")
                        doc.schema_refs.append(SchemaRef(href=href))
                    elif child.tag == _LINK_LINKBASE_REF:
                        href = child.get(f"{{{NS_XLINK}}}href", "")
                        role = child.get(f"{{{NS_XLINK}}}role", "")
                        arcrole = child.get(f"{{{NS_XLINK}}}arcrole", "")
                        doc.linkbase_refs.append(
                            LinkbaseRef(href=href, role=role, arcrole=arcrole)
                        )
                except Exception as exc:  # noqa: BLE001
                    doc.parse_errors.append(
                        f"Error extracting reference at line "
                        f"{get_element_line(child)}: {exc}"
                    )

        # Resources (contexts, units)
        for res_elem in self._find_elements(header, _IX_RESOURCES):
            for child in res_elem:
                if not isinstance(child.tag, str):
                    continue
                try:
                    if child.tag == _XBRLI_CONTEXT:
                        ctx = self._parse_context(child, doc)
                        if ctx:
                            doc.contexts[ctx.id] = ctx
                    elif child.tag == _XBRLI_UNIT:
                        unit = self._parse_unit(child, doc)
                        if unit:
                            doc.units[unit.id] = unit
                except Exception as exc:  # noqa: BLE001
                    doc.parse_errors.append(
                        f"Error extracting resource at line "
                        f"{get_element_line(child)}: {exc}"
                    )

        # Hidden facts
        for hidden_elem in self._find_elements(header, _IX_HIDDEN):
            self._walk_for_facts(hidden_elem, doc, is_hidden=True)

    def _parse_context(
        self, elem: etree._Element, doc: InlineXBRLDocument
    ) -> Optional[RawContext]:
        """Parse a context element from ix:resources."""
        ctx_id = elem.get("id", "")
        if not ctx_id:
            doc.parse_errors.append(
                f"Context at line {get_element_line(elem)} has no @id"
            )
            return None

        ctx = RawContext(id=ctx_id)

        # Entity
        entity = elem.find(f"{{{NS_XBRLI}}}entity")
        if entity is not None:
            ident = entity.find(f"{{{NS_XBRLI}}}identifier")
            if ident is not None:
                ctx.entity_scheme = ident.get("scheme", "")
                ctx.entity_id = (ident.text or "").strip()

            seg = entity.find(f"{{{NS_XBRLI}}}segment")
            if seg is not None:
                ctx.segments = self._extract_dimension_members(seg)

        # Period
        period = elem.find(f"{{{NS_XBRLI}}}period")
        if period is not None:
            instant = period.find(f"{{{NS_XBRLI}}}instant")
            forever = period.find(f"{{{NS_XBRLI}}}forever")
            start = period.find(f"{{{NS_XBRLI}}}startDate")
            end = period.find(f"{{{NS_XBRLI}}}endDate")

            if instant is not None:
                ctx.period_type = "instant"
                ctx.instant = (instant.text or "").strip()
            elif forever is not None:
                ctx.period_type = "forever"
            elif start is not None and end is not None:
                ctx.period_type = "duration"
                ctx.start_date = (start.text or "").strip()
                ctx.end_date = (end.text or "").strip()

        # Scenario
        scenario = elem.find(f"{{{NS_XBRLI}}}scenario")
        if scenario is not None:
            ctx.scenarios = self._extract_dimension_members(scenario)

        return ctx

    def _parse_unit(
        self, elem: etree._Element, doc: InlineXBRLDocument
    ) -> Optional[RawUnit]:
        """Parse a unit element from ix:resources."""
        unit_id = elem.get("id", "")
        if not unit_id:
            doc.parse_errors.append(
                f"Unit at line {get_element_line(elem)} has no @id"
            )
            return None

        unit = RawUnit(id=unit_id)
        divide = elem.find(f"{{{NS_XBRLI}}}divide")
        if divide is not None:
            num = divide.find(f"{{{NS_XBRLI}}}unitNumerator")
            den = divide.find(f"{{{NS_XBRLI}}}unitDenominator")
            if num is not None:
                unit.divide_numerator = [
                    (m.text or "").strip()
                    for m in num.findall(f"{{{NS_XBRLI}}}measure")
                ]
            if den is not None:
                unit.divide_denominator = [
                    (m.text or "").strip()
                    for m in den.findall(f"{{{NS_XBRLI}}}measure")
                ]
        else:
            unit.measures = [
                (m.text or "").strip()
                for m in elem.findall(f"{{{NS_XBRLI}}}measure")
            ]

        return unit

    @staticmethod
    def _extract_dimension_members(
        container: etree._Element,
    ) -> list[dict[str, str]]:
        """Extract dimension members from a segment or scenario."""
        members: list[dict[str, str]] = []
        for child in container:
            if not isinstance(child.tag, str):
                continue
            members.append(
                {
                    "tag": child.tag,
                    "local": strip_namespace(child.tag),
                    "namespace": get_namespace(child.tag),
                    "dimension": child.get("dimension", ""),
                    "value": (child.text or "").strip(),
                }
            )
        return members

    # ------------------------------------------------------------------
    # Phase 3 & 4: Body walk + transform application
    # ------------------------------------------------------------------

    def _walk_for_facts(
        self,
        root: etree._Element,
        doc: InlineXBRLDocument,
        is_hidden: bool,
    ) -> None:
        """Walk the element tree looking for inline XBRL fact elements."""
        for elem in root.iter():
            if not isinstance(elem.tag, str):
                continue

            try:
                if elem.tag == _IX_NON_FRACTION:
                    self._extract_non_fraction(elem, doc, is_hidden)
                elif elem.tag == _IX_NON_NUMERIC:
                    self._extract_non_numeric(elem, doc, is_hidden)
                elif elem.tag == _IX_FRACTION:
                    self._extract_fraction(elem, doc, is_hidden)
                elif elem.tag == _IX_TUPLE:
                    self._extract_tuple(elem, doc, is_hidden)
            except Exception as exc:  # noqa: BLE001
                doc.parse_errors.append(
                    f"Error extracting fact at line "
                    f"{get_element_line(elem)}: {exc}"
                )

    def _extract_non_fraction(
        self,
        elem: etree._Element,
        doc: InlineXBRLDocument,
        is_hidden: bool,
    ) -> None:
        """Extract an ix:nonFraction fact element."""
        concept = self._resolve_concept_name(elem, doc)
        context_ref = elem.get("contextRef", "")
        unit_ref = elem.get("unitRef")
        format_attr = elem.get("format")
        scale = elem.get("scale")
        sign = elem.get("sign")
        decimals = elem.get("decimals")
        precision = elem.get("precision")
        fact_id = elem.get("id")
        nil_val = elem.get(f"{{{NS_XSI}}}nil", elem.get("nil", "false"))
        is_nil = nil_val.lower() in ("true", "1")

        display_value = self._get_text_content(elem)

        # Apply transform
        xbrl_value = display_value
        if format_attr and not is_nil:
            xbrl_value, err = self._transforms.apply_transform(
                format_attr, display_value
            )
            if err:
                doc.parse_errors.append(
                    f"Transform error at line {get_element_line(elem)}: {err}"
                )

        # Apply scale
        if scale and not is_nil and xbrl_value:
            xbrl_value = self._apply_scale(xbrl_value, scale)

        # Apply sign
        if sign == "-" and not is_nil and xbrl_value:
            xbrl_value = self._apply_sign(xbrl_value)

        fact = InlineFact(
            concept=concept,
            context_ref=context_ref,
            unit_ref=unit_ref,
            display_value=display_value,
            xbrl_value=xbrl_value if not is_nil else "",
            format_attr=format_attr,
            scale=scale,
            sign=sign,
            decimals=decimals,
            precision=precision,
            id=fact_id,
            is_nil=is_nil,
            source_line=get_element_line(elem),
            continued_at=elem.get("continuedAt"),
            is_hidden=is_hidden,
        )
        doc.inline_facts.append(fact)

    def _extract_non_numeric(
        self,
        elem: etree._Element,
        doc: InlineXBRLDocument,
        is_hidden: bool,
    ) -> None:
        """Extract an ix:nonNumeric fact element."""
        concept = self._resolve_concept_name(elem, doc)
        context_ref = elem.get("contextRef", "")
        format_attr = elem.get("format")
        fact_id = elem.get("id")
        nil_val = elem.get(f"{{{NS_XSI}}}nil", elem.get("nil", "false"))
        is_nil = nil_val.lower() in ("true", "1")
        continued_at = elem.get("continuedAt")

        display_value = self._get_text_content(elem)

        # Apply transform
        xbrl_value = display_value
        if format_attr and not is_nil:
            xbrl_value, err = self._transforms.apply_transform(
                format_attr, display_value
            )
            if err:
                doc.parse_errors.append(
                    f"Transform error at line {get_element_line(elem)}: {err}"
                )

        fact = InlineFact(
            concept=concept,
            context_ref=context_ref,
            display_value=display_value,
            xbrl_value=xbrl_value if not is_nil else "",
            format_attr=format_attr,
            id=fact_id,
            is_nil=is_nil,
            source_line=get_element_line(elem),
            continued_at=continued_at,
            is_hidden=is_hidden,
        )
        doc.inline_facts.append(fact)

    def _extract_fraction(
        self,
        elem: etree._Element,
        doc: InlineXBRLDocument,
        is_hidden: bool,
    ) -> None:
        """Extract an ix:fraction fact element."""
        concept = self._resolve_concept_name(elem, doc)
        context_ref = elem.get("contextRef", "")
        unit_ref = elem.get("unitRef")
        fact_id = elem.get("id")

        # Get numerator and denominator
        numerator_val = ""
        denominator_val = ""
        for child in elem:
            if not isinstance(child.tag, str):
                continue
            if child.tag == _IX_NUMERATOR:
                numerator_val = (child.text or "").strip()
            elif child.tag == _IX_DENOMINATOR:
                denominator_val = (child.text or "").strip()

        display_value = f"{numerator_val}/{denominator_val}"

        fact = InlineFact(
            concept=concept,
            context_ref=context_ref,
            unit_ref=unit_ref,
            display_value=display_value,
            xbrl_value=display_value,
            id=fact_id,
            source_line=get_element_line(elem),
            is_hidden=is_hidden,
        )
        doc.inline_facts.append(fact)

    def _extract_tuple(
        self,
        elem: etree._Element,
        doc: InlineXBRLDocument,
        is_hidden: bool,
    ) -> None:
        """Extract an ix:tuple fact element (metadata only)."""
        concept = self._resolve_concept_name(elem, doc)
        fact_id = elem.get("id")
        order = elem.get("order")

        fact = InlineFact(
            concept=concept,
            id=fact_id,
            source_line=get_element_line(elem),
            is_hidden=is_hidden,
            order=order,
        )
        doc.inline_facts.append(fact)

    # ------------------------------------------------------------------
    # Phase 5: Continuation resolution
    # ------------------------------------------------------------------

    def _resolve_continuations(
        self, root: etree._Element, doc: InlineXBRLDocument
    ) -> None:
        """Collect ix:continuation elements and resolve chains."""
        # Build continuation map: id → text content
        for elem in root.iter():
            if not isinstance(elem.tag, str):
                continue
            if elem.tag == _IX_CONTINUATION:
                cont_id = elem.get("id", "")
                if cont_id:
                    doc.continuations[cont_id] = self._get_text_content(elem)

        # Resolve continuation chains for facts with continuedAt
        for fact in doc.inline_facts:
            if fact.continued_at:
                chain_text = self._follow_chain(fact.continued_at, doc)
                if chain_text:
                    fact.xbrl_value = fact.xbrl_value + chain_text

    @staticmethod
    def _follow_chain(
        start_id: str, doc: InlineXBRLDocument, max_depth: int = 100
    ) -> str:
        """Follow a continuation chain, concatenating text."""
        parts: list[str] = []
        current_id = start_id
        visited: set[str] = set()
        depth = 0

        while current_id and depth < max_depth:
            if current_id in visited:
                doc.parse_errors.append(
                    f"Circular continuation chain detected at '{current_id}'"
                )
                break
            visited.add(current_id)

            text = doc.continuations.get(current_id, "")
            if text:
                parts.append(text)

            # Check if continuation itself has a continuedAt
            # (stored in doc.continuations won't have this info,
            # so chain terminates here unless we track it separately)
            depth += 1
            break  # Simple chains: one continuation per fact

        return "".join(parts)

    # ------------------------------------------------------------------
    # Phase 6: Hidden fact classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_hidden(doc: InlineXBRLDocument) -> None:
        """Move hidden facts to the ``hidden_facts`` list."""
        remaining: list[InlineFact] = []
        for fact in doc.inline_facts:
            if fact.is_hidden:
                doc.hidden_facts.append(fact)
            else:
                remaining.append(fact)
        doc.inline_facts = remaining

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_concept_name(
        elem: etree._Element, doc: InlineXBRLDocument
    ) -> str:
        """Resolve the ``@name`` attribute to a Clark-notation QName."""
        name = elem.get("name", "")
        if not name:
            return ""

        if ":" in name:
            prefix, local = name.split(":", maxsplit=1)
            # Look up in element's own nsmap first, then doc namespaces
            ns_uri = ""
            if hasattr(elem, "nsmap") and elem.nsmap:
                ns_uri = elem.nsmap.get(prefix, "")
            if not ns_uri:
                ns_uri = doc.namespaces.get(prefix, "")
            if ns_uri:
                return f"{{{ns_uri}}}{local}"
            return name

        # No prefix — try default namespace
        ns_uri = doc.namespaces.get("", "")
        if ns_uri:
            return f"{{{ns_uri}}}{name}"
        return name

    @staticmethod
    def _get_text_content(elem: etree._Element) -> str:
        """Get text content excluding ix:exclude children."""
        parts: list[str] = []
        if elem.text:
            parts.append(elem.text)

        for child in elem:
            if isinstance(child.tag, str) and child.tag == _IX_EXCLUDE:
                # Skip excluded content but include tail
                if child.tail:
                    parts.append(child.tail)
            else:
                # Include child text recursively
                if isinstance(child.tag, str):
                    child_text = etree.tostring(
                        child, method="text", encoding="unicode"
                    )
                    if child_text:
                        parts.append(child_text)
                if child.tail:
                    parts.append(child.tail)

        return "".join(parts).strip()

    @staticmethod
    def _apply_scale(value: str, scale: str) -> str:
        """Apply a scale factor to a numeric value.

        The scale attribute represents a power of 10 multiplier.
        For example, scale="6" means the value should be multiplied
        by 10^6 (millions).
        """
        try:
            from decimal import Decimal

            dec_value = Decimal(value)
            scale_int = int(scale)
            multiplier = Decimal(10) ** scale_int
            result = dec_value * multiplier
            # Normalise to remove trailing zeros
            return str(result.normalize())
        except Exception:  # noqa: BLE001
            return value

    @staticmethod
    def _apply_sign(value: str) -> str:
        """Negate a numeric value (prepend '-' or remove existing '-')."""
        stripped = value.strip()
        if stripped.startswith("-"):
            return stripped[1:]
        return f"-{stripped}"

    @staticmethod
    def _find_elements(
        root: etree._Element, tag: str
    ) -> list[etree._Element]:
        """Find all descendant elements matching the given Clark-notation tag.

        Works with both namespace-aware and prefix-based element names.
        """
        results: list[etree._Element] = []
        for elem in root.iter():
            if isinstance(elem.tag, str) and elem.tag == tag:
                results.append(elem)
        return results
