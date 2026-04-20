"""DOM parser for XBRL XML instance documents.

Parses standard XBRL 2.1 instance documents into a ``RawXBRLDocument``
intermediate representation using lxml's full DOM parser.

Security: All XML parsing uses a hardened ``lxml.etree.XMLParser`` with
``resolve_entities=False``, ``no_network=True``, ``dtd_validation=False``,
``load_dtd=False``, and ``huge_tree=False`` to prevent XXE, DTD bombs,
and other XML-based attacks.

Spec references:
- XBRL 2.1 §4 (instance documents)
- XBRL 2.1 §4.1 (xbrl root element)
- XBRL 2.1 §4.4 (schemaRef)
- XBRL 2.1 §4.5 (linkbaseRef)
- XBRL 2.1 §4.7 (context element)
- XBRL 2.1 §4.8 (unit element)
- XBRL 2.1 §4.6 (facts/items)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional

from lxml import etree

from src.core.constants import (
    DEFAULT_LARGE_FILE_THRESHOLD_BYTES,
    NS_LINK,
    NS_XBRLI,
    NS_XLINK,
    NS_XSI,
)
from src.core.exceptions import ParseError
from src.utils.size_utils import get_file_size
from src.utils.xml_utils import (
    get_element_line,
    get_namespace,
    safe_xml_parser,
    strip_namespace,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes for parsed XBRL data
# ---------------------------------------------------------------------------


@dataclass
class SchemaRef:
    """Reference to a taxonomy schema document (XBRL 2.1 §4.4)."""

    href: str
    namespace: str = ""


@dataclass
class LinkbaseRef:
    """Reference to a linkbase document (XBRL 2.1 §4.5)."""

    href: str
    role: str = ""
    arcrole: str = ""


@dataclass
class RawContext:
    """Raw parsed context element (XBRL 2.1 §4.7).

    Attributes:
        id: Context identifier.
        entity_scheme: Entity identifier scheme URI.
        entity_id: Entity identifier value.
        period_type: One of ``"instant"``, ``"duration"``, or ``"forever"``.
        instant: Instant date string (if period_type is instant).
        start_date: Start date string (if period_type is duration).
        end_date: End date string (if period_type is duration).
        segments: List of raw segment element dicts.
        scenarios: List of raw scenario element dicts.
    """

    id: str
    entity_scheme: str = ""
    entity_id: str = ""
    period_type: str = ""
    instant: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    segments: list[dict[str, str]] = field(default_factory=list)
    scenarios: list[dict[str, str]] = field(default_factory=list)


@dataclass
class RawUnit:
    """Raw parsed unit element (XBRL 2.1 §4.8).

    Attributes:
        id: Unit identifier.
        measures: List of measure QNames (simple unit).
        divide_numerator: List of numerator measure QNames (divide unit).
        divide_denominator: List of denominator measure QNames (divide unit).
    """

    id: str
    measures: list[str] = field(default_factory=list)
    divide_numerator: list[str] = field(default_factory=list)
    divide_denominator: list[str] = field(default_factory=list)


@dataclass
class RawFact:
    """Raw parsed fact/item element (XBRL 2.1 §4.6).

    Attributes:
        concept: Fully qualified concept name (Clark notation).
        context_ref: Reference to the context element.
        unit_ref: Reference to the unit element (numeric items only).
        value: Raw text value from the element.
        decimals: Decimals attribute value.
        precision: Precision attribute value.
        id: Fact element id attribute.
        is_nil: Whether xsi:nil="true".
        source_line: Source line number in the original file.
        namespace: Namespace URI of the concept.
    """

    concept: str
    context_ref: str
    unit_ref: Optional[str] = None
    value: str = ""
    decimals: Optional[str] = None
    precision: Optional[str] = None
    id: Optional[str] = None
    is_nil: bool = False
    source_line: int = 0
    namespace: str = ""


@dataclass
class RawFootnote:
    """Raw parsed footnote data."""

    fact_id: str = ""
    footnote_id: str = ""
    role: str = ""
    lang: str = ""
    content: str = ""
    source_line: int = 0


@dataclass
class RawXBRLDocument:
    """Intermediate representation of a parsed XBRL document.

    Produced by DOM and streaming parsers alike. Downstream validators
    operate on this normalised structure rather than raw XML.
    """

    file_path: str = ""
    namespaces: dict[str, str] = field(default_factory=dict)
    schema_refs: list[SchemaRef] = field(default_factory=list)
    linkbase_refs: list[LinkbaseRef] = field(default_factory=list)
    contexts: dict[str, RawContext] = field(default_factory=dict)
    units: dict[str, RawUnit] = field(default_factory=dict)
    facts: list[RawFact] = field(default_factory=list)
    footnotes: list[RawFootnote] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Clark-notation tag helpers
# ---------------------------------------------------------------------------

_XBRLI_XBRL = f"{{{NS_XBRLI}}}xbrl"
_XBRLI_CONTEXT = f"{{{NS_XBRLI}}}context"
_XBRLI_UNIT = f"{{{NS_XBRLI}}}unit"
_XBRLI_ENTITY = f"{{{NS_XBRLI}}}entity"
_XBRLI_IDENTIFIER = f"{{{NS_XBRLI}}}identifier"
_XBRLI_PERIOD = f"{{{NS_XBRLI}}}period"
_XBRLI_INSTANT = f"{{{NS_XBRLI}}}instant"
_XBRLI_START = f"{{{NS_XBRLI}}}startDate"
_XBRLI_END = f"{{{NS_XBRLI}}}endDate"
_XBRLI_FOREVER = f"{{{NS_XBRLI}}}forever"
_XBRLI_SEGMENT = f"{{{NS_XBRLI}}}segment"
_XBRLI_SCENARIO = f"{{{NS_XBRLI}}}scenario"
_XBRLI_MEASURE = f"{{{NS_XBRLI}}}measure"
_XBRLI_DIVIDE = f"{{{NS_XBRLI}}}divide"
_XBRLI_NUMERATOR = f"{{{NS_XBRLI}}}unitNumerator"
_XBRLI_DENOMINATOR = f"{{{NS_XBRLI}}}unitDenominator"

_LINK_SCHEMA_REF = f"{{{NS_LINK}}}schemaRef"
_LINK_LINKBASE_REF = f"{{{NS_LINK}}}linkbaseRef"
_LINK_FOOTNOTE_LINK = f"{{{NS_LINK}}}footnoteLink"
_LINK_FOOTNOTE = f"{{{NS_LINK}}}footnote"
_LINK_FOOTNOTE_ARC = f"{{{NS_LINK}}}footnoteArc"
_LINK_LOC = f"{{{NS_LINK}}}loc"

_RESERVED_NAMESPACES = frozenset({NS_XBRLI, NS_LINK, NS_XLINK, NS_XSI})


class XMLParser:
    """DOM parser for XBRL XML instance documents.

    Security: Uses hardened lxml XMLParser (resolve_entities=False,
    no_network=True, dtd_validation=False, load_dtd=False,
    huge_tree=False).

    Parameters
    ----------
    large_file_threshold:
        Files larger than this threshold (bytes) should use the
        streaming parser instead. This parser will still attempt
        parsing but will log a warning.
    """

    def __init__(
        self,
        large_file_threshold: int = DEFAULT_LARGE_FILE_THRESHOLD_BYTES,
    ) -> None:
        self._large_file_threshold = large_file_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, file_path: str) -> RawXBRLDocument:
        """Parse an XBRL XML file into a ``RawXBRLDocument``.

        Extracts namespaces, schemaRefs, linkbaseRefs, contexts, units,
        facts, and footnotes from the instance document.

        Error codes emitted in ``parse_errors``:
            PARSE-0001  XML well-formedness error
            PARSE-0002  Missing xbrli:xbrl root element
            PARSE-0003  Context parsing error
            PARSE-0004  Unit parsing error
            PARSE-0005  Fact parsing error
            PARSE-0006  Footnote parsing error
            PARSE-0007  General unexpected error

        Parameters
        ----------
        file_path:
            Path to the XBRL instance file.

        Returns
        -------
        RawXBRLDocument
            The parsed intermediate representation.

        Raises
        ------
        ParseError
            On fatal XML well-formedness errors.
        """
        doc = RawXBRLDocument(file_path=file_path)

        file_size = get_file_size(file_path)
        if file_size > self._large_file_threshold:
            logger.warning(
                "File %s (%s bytes) exceeds large-file threshold; "
                "consider using the streaming parser",
                file_path,
                file_size,
            )

        parser = safe_xml_parser()
        try:
            tree = etree.parse(file_path, parser)  # noqa: S320
        except etree.XMLSyntaxError as exc:
            raise ParseError(
                f"PARSE-0001: XML syntax error: {exc}",
                file_path=file_path,
                line=getattr(exc, "lineno", 0) or 0,
                column=getattr(exc, "offset", 0) or 0,
            ) from exc

        root = tree.getroot()
        self._extract_from_root(root, doc)
        return doc

    def parse_bytes(self, data: bytes, source_name: str = "<bytes>") -> RawXBRLDocument:
        """Parse XBRL XML from an in-memory byte string.

        Parameters
        ----------
        data:
            Raw XML bytes.
        source_name:
            A descriptive label used in error messages.

        Returns
        -------
        RawXBRLDocument
        """
        doc = RawXBRLDocument(file_path=source_name)
        parser = safe_xml_parser()
        try:
            root = etree.fromstring(data, parser)  # noqa: S320
        except etree.XMLSyntaxError as exc:
            raise ParseError(
                f"PARSE-0001: XML syntax error: {exc}",
                file_path=source_name,
                line=getattr(exc, "lineno", 0) or 0,
                column=getattr(exc, "offset", 0) or 0,
            ) from exc

        self._extract_from_root(root, doc)
        return doc

    # ------------------------------------------------------------------
    # Internal extraction
    # ------------------------------------------------------------------

    def _extract_from_root(
        self, root: etree._Element, doc: RawXBRLDocument
    ) -> None:
        """Walk the root element and populate *doc*."""
        # Collect namespace map
        doc.namespaces = dict(root.nsmap) if root.nsmap else {}
        # lxml may include None key for default namespace
        if None in doc.namespaces:
            doc.namespaces[""] = doc.namespaces.pop(None)  # type: ignore[call-overload]

        root_tag = root.tag
        if root_tag != _XBRLI_XBRL:
            local = strip_namespace(root_tag)
            if local != "xbrl":
                doc.parse_errors.append(
                    f"PARSE-0002: Expected root element {{}}xbrl, got {root_tag}"
                )

        for child in root:
            if not isinstance(child.tag, str):
                continue  # skip comments/PIs
            try:
                self._dispatch_child(child, doc)
            except Exception as exc:  # noqa: BLE001
                doc.parse_errors.append(
                    f"PARSE-0007: Unexpected error at line "
                    f"{get_element_line(child)}: {exc}"
                )

    def _dispatch_child(
        self, elem: etree._Element, doc: RawXBRLDocument
    ) -> None:
        """Route a child element of <xbrli:xbrl> to the correct extractor."""
        tag = elem.tag
        if tag == _LINK_SCHEMA_REF:
            self._extract_schema_ref(elem, doc)
        elif tag == _LINK_LINKBASE_REF:
            self._extract_linkbase_ref(elem, doc)
        elif tag == _XBRLI_CONTEXT:
            self._extract_context(elem, doc)
        elif tag == _XBRLI_UNIT:
            self._extract_unit(elem, doc)
        elif tag == _LINK_FOOTNOTE_LINK:
            self._extract_footnotes(elem, doc)
        else:
            ns = get_namespace(tag)
            if ns not in _RESERVED_NAMESPACES and ns:
                self._extract_fact(elem, doc)

    # -- schemaRef / linkbaseRef -----------------------------------------

    def _extract_schema_ref(
        self, elem: etree._Element, doc: RawXBRLDocument
    ) -> None:
        href = elem.get(f"{{{NS_XLINK}}}href", "")
        doc.schema_refs.append(SchemaRef(href=href))

    def _extract_linkbase_ref(
        self, elem: etree._Element, doc: RawXBRLDocument
    ) -> None:
        href = elem.get(f"{{{NS_XLINK}}}href", "")
        role = elem.get(f"{{{NS_XLINK}}}role", "")
        arcrole = elem.get(f"{{{NS_XLINK}}}arcrole", "")
        doc.linkbase_refs.append(LinkbaseRef(href=href, role=role, arcrole=arcrole))

    # -- context ---------------------------------------------------------

    def _extract_context(
        self, elem: etree._Element, doc: RawXBRLDocument
    ) -> None:
        ctx_id = elem.get("id", "")
        if not ctx_id:
            doc.parse_errors.append(
                f"PARSE-0003: Context at line {get_element_line(elem)} "
                f"has no @id attribute"
            )
            return

        ctx = RawContext(id=ctx_id)
        try:
            # Entity
            entity_elem = elem.find(_XBRLI_ENTITY)
            if entity_elem is not None:
                ident = entity_elem.find(_XBRLI_IDENTIFIER)
                if ident is not None:
                    ctx.entity_scheme = ident.get("scheme", "")
                    ctx.entity_id = (ident.text or "").strip()
                # Segments
                seg = entity_elem.find(_XBRLI_SEGMENT)
                if seg is not None:
                    ctx.segments = self._extract_dimension_members(seg)

            # Period
            period_elem = elem.find(_XBRLI_PERIOD)
            if period_elem is not None:
                instant = period_elem.find(_XBRLI_INSTANT)
                forever = period_elem.find(_XBRLI_FOREVER)
                start = period_elem.find(_XBRLI_START)
                end = period_elem.find(_XBRLI_END)

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
            scenario_elem = elem.find(_XBRLI_SCENARIO)
            if scenario_elem is not None:
                ctx.scenarios = self._extract_dimension_members(scenario_elem)

        except Exception as exc:  # noqa: BLE001
            doc.parse_errors.append(
                f"PARSE-0003: Error parsing context '{ctx_id}' "
                f"at line {get_element_line(elem)}: {exc}"
            )

        doc.contexts[ctx_id] = ctx

    @staticmethod
    def _extract_dimension_members(
        container: etree._Element,
    ) -> list[dict[str, str]]:
        """Extract dimension members from a segment or scenario element."""
        members: list[dict[str, str]] = []
        for child in container:
            if not isinstance(child.tag, str):
                continue
            local = strip_namespace(child.tag)
            ns = get_namespace(child.tag)
            members.append(
                {
                    "tag": child.tag,
                    "local": local,
                    "namespace": ns,
                    "dimension": child.get("dimension", ""),
                    "value": (child.text or "").strip(),
                }
            )
        return members

    # -- unit ------------------------------------------------------------

    def _extract_unit(
        self, elem: etree._Element, doc: RawXBRLDocument
    ) -> None:
        unit_id = elem.get("id", "")
        if not unit_id:
            doc.parse_errors.append(
                f"PARSE-0004: Unit at line {get_element_line(elem)} "
                f"has no @id attribute"
            )
            return

        unit = RawUnit(id=unit_id)
        try:
            divide = elem.find(_XBRLI_DIVIDE)
            if divide is not None:
                num = divide.find(_XBRLI_NUMERATOR)
                den = divide.find(_XBRLI_DENOMINATOR)
                if num is not None:
                    unit.divide_numerator = [
                        (m.text or "").strip()
                        for m in num.findall(_XBRLI_MEASURE)
                    ]
                if den is not None:
                    unit.divide_denominator = [
                        (m.text or "").strip()
                        for m in den.findall(_XBRLI_MEASURE)
                    ]
            else:
                unit.measures = [
                    (m.text or "").strip()
                    for m in elem.findall(_XBRLI_MEASURE)
                ]
        except Exception as exc:  # noqa: BLE001
            doc.parse_errors.append(
                f"PARSE-0004: Error parsing unit '{unit_id}' "
                f"at line {get_element_line(elem)}: {exc}"
            )

        doc.units[unit_id] = unit

    # -- fact ------------------------------------------------------------

    def _extract_fact(
        self, elem: etree._Element, doc: RawXBRLDocument
    ) -> None:
        tag = elem.tag
        ns = get_namespace(tag)
        context_ref = elem.get("contextRef", "")
        if not context_ref:
            # Tuples or non-fact children — skip silently
            return

        try:
            nil_attr = elem.get(f"{{{NS_XSI}}}nil", "false")
            is_nil = nil_attr.lower() in ("true", "1")

            value = ""
            if not is_nil:
                value = self._get_fact_value(elem)

            fact = RawFact(
                concept=tag,
                context_ref=context_ref,
                unit_ref=elem.get("unitRef"),
                value=value,
                decimals=elem.get("decimals"),
                precision=elem.get("precision"),
                id=elem.get("id"),
                is_nil=is_nil,
                source_line=get_element_line(elem),
                namespace=ns,
            )
            doc.facts.append(fact)
        except Exception as exc:  # noqa: BLE001
            doc.parse_errors.append(
                f"PARSE-0005: Error parsing fact '{tag}' "
                f"at line {get_element_line(elem)}: {exc}"
            )

    @staticmethod
    def _get_fact_value(elem: etree._Element) -> str:
        """Extract the text value of a fact element.

        For simple elements returns the text content. For elements
        with children (e.g. tuples) returns the serialised inner XML.
        """
        if len(elem) == 0:
            return (elem.text or "").strip()
        # Complex content — serialise children
        parts: list[str] = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            parts.append(
                etree.tostring(child, encoding="unicode", with_tail=True)
            )
        return "".join(parts).strip()

    # -- footnotes -------------------------------------------------------

    def _extract_footnotes(
        self, elem: etree._Element, doc: RawXBRLDocument
    ) -> None:
        """Extract footnotes from a link:footnoteLink element."""
        try:
            # Collect locators
            locs: dict[str, str] = {}
            for loc in elem.findall(_LINK_LOC):
                label = loc.get(f"{{{NS_XLINK}}}label", "")
                href = loc.get(f"{{{NS_XLINK}}}href", "")
                if label:
                    locs[label] = href

            # Collect footnote content
            fn_content: dict[str, RawFootnote] = {}
            for fn in elem.findall(_LINK_FOOTNOTE):
                label = fn.get(f"{{{NS_XLINK}}}label", "")
                fn_id = fn.get("id", label)
                role = fn.get(f"{{{NS_XLINK}}}role", "")
                lang = fn.get(f"{{{NS_XBRLI}}}lang", fn.get("lang", ""))
                content = etree.tostring(fn, method="text", encoding="unicode")
                fn_content[label] = RawFootnote(
                    footnote_id=fn_id,
                    role=role,
                    lang=lang,
                    content=(content or "").strip(),
                    source_line=get_element_line(fn),
                )

            # Wire arcs
            for arc in elem.findall(_LINK_FOOTNOTE_ARC):
                from_label = arc.get(f"{{{NS_XLINK}}}from", "")
                to_label = arc.get(f"{{{NS_XLINK}}}to", "")

                fact_href = locs.get(from_label, "")
                # Extract fact id from href (e.g. "#fact1" → "fact1")
                fact_id = fact_href.split("#")[-1] if "#" in fact_href else fact_href

                if to_label in fn_content:
                    footnote = fn_content[to_label]
                    footnote.fact_id = fact_id
                    doc.footnotes.append(footnote)
        except Exception as exc:  # noqa: BLE001
            doc.parse_errors.append(
                f"PARSE-0006: Error parsing footnotes "
                f"at line {get_element_line(elem)}: {exc}"
            )
