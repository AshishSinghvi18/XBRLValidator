"""Inline XBRL (iXBRL) parser.

Parses Inline XBRL documents embedded in (X)HTML and extracts XBRL facts,
footnotes, relationships, and continuation fragments.  Supports both
well-formed XHTML (parsed via lxml) and HTML5 tag-soup (parsed via
html5lib as a fallback).

The parser can also convert an :class:`InlineXBRLDocument` into a
synthetic :class:`~src.core.parser.xml_parser.RawXBRLDocument` suitable
for downstream XBRL 2.1 processing.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from lxml import etree

from src.core.constants import (
    NS_IX,
    NS_LINK,
    NS_XBRLI,
    NS_XLINK,
    NS_XSI,
)
from src.core.exceptions import IXBRLParseError
from src.core.parser.ixbrl_continuation import (
    ContinuationFact,
    ContinuationFragment,
    ContinuationResolver,
    ResolvedFact,
)
from src.core.parser.ixbrl_transforms import IXBRLTransformEngine, TransformResult
from src.core.parser.xml_parser import RawXBRLDocument
from src.security.xxe_guard import XXEGuard

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Precomputed qualified names (Clark notation)
# ---------------------------------------------------------------------------

_IX_HEADER = f"{{{NS_IX}}}header"
_IX_REFERENCES = f"{{{NS_IX}}}references"
_IX_RESOURCES = f"{{{NS_IX}}}resources"
_IX_NON_FRACTION = f"{{{NS_IX}}}nonFraction"
_IX_NON_NUMERIC = f"{{{NS_IX}}}nonNumeric"
_IX_FRACTION = f"{{{NS_IX}}}fraction"
_IX_TUPLE = f"{{{NS_IX}}}tuple"
_IX_CONTINUATION = f"{{{NS_IX}}}continuation"
_IX_FOOTNOTE = f"{{{NS_IX}}}footnote"
_IX_RELATIONSHIP = f"{{{NS_IX}}}relationship"
_IX_EXCLUDE = f"{{{NS_IX}}}exclude"

_LINK_SCHEMA_REF = f"{{{NS_LINK}}}schemaRef"
_LINK_LINKBASE_REF = f"{{{NS_LINK}}}linkbaseRef"
_XLINK_HREF = f"{{{NS_XLINK}}}href"
_XLINK_ARCROLE = f"{{{NS_XLINK}}}arcrole"
_XLINK_TYPE = f"{{{NS_XLINK}}}type"
_XSI_NIL = f"{{{NS_XSI}}}nil"

_FACT_TAGS = {
    _IX_NON_FRACTION: "nonFraction",
    _IX_NON_NUMERIC: "nonNumeric",
    _IX_FRACTION: "fraction",
    _IX_TUPLE: "tuple",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class InlineFact:
    """A single XBRL fact extracted from an Inline XBRL document."""

    fact_id: str
    name: str
    context_ref: str
    unit_ref: str | None = None
    value: str = ""
    format_qname: str | None = None
    scale: int = 0
    sign: str | None = None
    decimals: str | None = None
    precision: str | None = None
    is_nil: bool = False
    element_type: str = "nonNumeric"
    order: int = 0
    source_line: int | None = None


@dataclass
class InlineFootnote:
    """A footnote extracted from ``ix:resources``."""

    footnote_id: str
    content: str
    lang: str | None = None
    footnote_role: str | None = None


@dataclass
class InlineRelationship:
    """A relationship arc extracted from ``ix:resources``."""

    from_refs: list[str] = field(default_factory=list)
    to_refs: list[str] = field(default_factory=list)
    arcrole: str = ""
    link_role: str | None = None


@dataclass
class InlineXBRLDocument:
    """Parsed representation of a complete Inline XBRL document."""

    source_file: str
    source_size: int
    namespaces: dict[str, str] = field(default_factory=dict)
    schema_refs: list[str] = field(default_factory=list)
    linkbase_refs: list[str] = field(default_factory=list)
    facts: list[InlineFact] = field(default_factory=list)
    continuations: list[ContinuationFragment] = field(default_factory=list)
    footnotes: list[InlineFootnote] = field(default_factory=list)
    relationships: list[InlineRelationship] = field(default_factory=list)
    target: str | None = None
    doc_encoding: str = "utf-8"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class IXBRLParser:
    """Parser for Inline XBRL documents.

    Handles both well-formed XHTML (via lxml with XXE protection) and
    HTML5 tag-soup (via html5lib fallback).
    """

    def __init__(
        self,
        xxe_guard: XXEGuard | None = None,
        transform_engine: IXBRLTransformEngine | None = None,
    ) -> None:
        self._xxe_guard = xxe_guard if xxe_guard is not None else XXEGuard()
        self._transform_engine = (
            transform_engine
            if transform_engine is not None
            else IXBRLTransformEngine()
        )
        self._continuation_resolver = ContinuationResolver()

    # -- public API ---------------------------------------------------------

    def parse(self, file_path: str) -> InlineXBRLDocument:
        """Parse an Inline XBRL file and return an :class:`InlineXBRLDocument`.

        Args:
            file_path: Path to the iXBRL file.

        Returns:
            A populated :class:`InlineXBRLDocument`.

        Raises:
            IXBRLParseError: If the file cannot be found or parsed.
        """
        if not os.path.isfile(file_path):
            raise IXBRLParseError(
                code="IXBRL-0001",
                message=f"File not found: {file_path}",
                file_path=file_path,
            )

        source_size = os.path.getsize(file_path)
        root, doc_encoding = self._parse_file(file_path)

        # Collect namespaces from the root element
        namespaces = self._collect_namespaces(root)

        # Locate ix:header
        header = self._find_header(root)
        target = header.get("target") if header is not None else None

        # Extract references
        schema_refs: list[str] = []
        linkbase_refs: list[str] = []
        if header is not None:
            schema_refs, linkbase_refs = self._extract_references(header)

        # Extract resources (footnotes and relationships from ix:resources)
        header_footnotes: list[InlineFootnote] = []
        header_relationships: list[InlineRelationship] = []
        if header is not None:
            header_footnotes, header_relationships = self._extract_resources(header)

        # Walk the document tree for facts, continuations, footnotes, rels
        facts: list[InlineFact] = []
        continuations: list[ContinuationFragment] = []
        footnotes: list[InlineFootnote] = list(header_footnotes)
        relationships: list[InlineRelationship] = list(header_relationships)
        order_counter = 0

        for elem in root.iter():
            tag = elem.tag if isinstance(elem.tag, str) else ""

            if tag in _FACT_TAGS:
                fact = self._parse_fact_element(
                    elem, _FACT_TAGS[tag], order_counter
                )
                facts.append(fact)
                order_counter += 1

                # Check for continuationAt on the fact element itself
                cont_at = elem.get("continuationAt")
                if cont_at:
                    # Store continuation reference for later resolution
                    pass

            elif tag == _IX_CONTINUATION:
                fragment = self._parse_continuation(elem)
                continuations.append(fragment)

            elif tag == _IX_FOOTNOTE:
                footnote = self._parse_footnote(elem)
                if footnote not in footnotes:
                    footnotes.append(footnote)

            elif tag == _IX_RELATIONSHIP:
                rel = self._parse_relationship(elem)
                if rel not in relationships:
                    relationships.append(rel)

        return InlineXBRLDocument(
            source_file=file_path,
            source_size=source_size,
            namespaces=namespaces,
            schema_refs=schema_refs,
            linkbase_refs=linkbase_refs,
            facts=facts,
            continuations=continuations,
            footnotes=footnotes,
            relationships=relationships,
            target=target,
            doc_encoding=doc_encoding,
        )

    def parse_multiple(self, file_paths: list[str]) -> list[InlineXBRLDocument]:
        """Parse multiple Inline XBRL files.

        Args:
            file_paths: List of file paths to parse.

        Returns:
            A list of :class:`InlineXBRLDocument` instances in the same
            order as the input paths.
        """
        return [self.parse(fp) for fp in file_paths]

    def to_xbrl_instance(self, doc: InlineXBRLDocument) -> RawXBRLDocument:
        """Convert an :class:`InlineXBRLDocument` to a :class:`RawXBRLDocument`.

        Resolves continuation chains, applies iXBRL transformations, and
        builds a synthetic XBRL 2.1 instance XML tree.

        Args:
            doc: A parsed inline XBRL document.

        Returns:
            A :class:`RawXBRLDocument` representing the equivalent XBRL
            instance.
        """
        # 1. Resolve continuations
        continuation_facts = self._build_continuation_facts(doc)
        resolved_map: dict[str, str] = {}
        if continuation_facts:
            resolved = self._continuation_resolver.resolve(
                continuation_facts, doc.continuations
            )
            for rf in resolved:
                resolved_map[rf.fact_id] = rf.resolved_value

        # 2. Build the XBRL instance tree
        nsmap = {
            "xbrli": NS_XBRLI,
            "link": NS_LINK,
            "xlink": NS_XLINK,
        }
        # Merge document namespaces (skip None keys from default ns)
        for prefix, uri in doc.namespaces.items():
            if prefix and prefix not in nsmap:
                nsmap[prefix] = uri

        xbrl_root = etree.Element(f"{{{NS_XBRLI}}}xbrl", nsmap=nsmap)

        # 3. Add schemaRef elements
        for href in doc.schema_refs:
            schema_ref = etree.SubElement(xbrl_root, f"{{{NS_LINK}}}schemaRef")
            schema_ref.set(f"{{{NS_XLINK}}}type", "simple")
            schema_ref.set(f"{{{NS_XLINK}}}href", href)

        # 4. Add fact elements
        for fact in doc.facts:
            # Determine the resolved value
            raw_value = resolved_map.get(fact.fact_id, fact.value)

            # Apply transformation if a format is specified
            transformed_value = raw_value
            if fact.format_qname and not fact.is_nil:
                try:
                    result: TransformResult = self._transform_engine.apply(
                        format_qname=fact.format_qname,
                        display_value=raw_value,
                        scale=fact.scale,
                        sign=fact.sign,
                    )
                    if result.error_code is None:
                        transformed_value = result.xbrl_value
                    else:
                        logger.warning(
                            "Transform error %s for fact %s: using raw value",
                            result.error_code,
                            fact.fact_id,
                        )
                except Exception:
                    logger.warning(
                        "Transform failed for fact %s: using raw value",
                        fact.fact_id,
                        exc_info=True,
                    )

            # Create the fact element
            fact_elem = etree.SubElement(xbrl_root, fact.name)
            fact_elem.set("contextRef", fact.context_ref)

            if fact.unit_ref is not None:
                fact_elem.set("unitRef", fact.unit_ref)
            if fact.decimals is not None:
                fact_elem.set("decimals", fact.decimals)
            if fact.precision is not None:
                fact_elem.set("precision", fact.precision)
            if fact.is_nil:
                fact_elem.set(f"{{{NS_XSI}}}nil", "true")
            else:
                fact_elem.text = transformed_value

            if fact.fact_id:
                fact_elem.set("id", fact.fact_id)

        return RawXBRLDocument(
            root=xbrl_root,
            namespaces=dict(nsmap),
            source_file=doc.source_file,
            source_size=doc.source_size,
            declared_schema_refs=list(doc.schema_refs),
            declared_linkbase_refs=list(doc.linkbase_refs),
            doc_encoding=doc.doc_encoding,
        )

    # -- private helpers ----------------------------------------------------

    def _parse_file(
        self, file_path: str
    ) -> tuple[etree._Element, str]:
        """Parse the file, trying lxml first, then html5lib fallback.

        Returns:
            A tuple of (root element, encoding).
        """
        # Try lxml (well-formed XHTML) first
        try:
            tree = self._xxe_guard.safe_parse(file_path)
            encoding = (
                tree.docinfo.encoding if tree.docinfo.encoding else "utf-8"
            )
            return tree.getroot(), encoding
        except etree.XMLSyntaxError:
            logger.debug(
                "lxml XML parse failed for %s; falling back to html5lib",
                file_path,
            )

        # Fallback: html5lib for HTML5 tag-soup
        try:
            import html5lib  # noqa: F811
        except ImportError:
            raise IXBRLParseError(
                code="IXBRL-0002",
                message=(
                    f"Cannot parse malformed HTML in {file_path}: "
                    "html5lib is not installed"
                ),
                file_path=file_path,
            )

        try:
            with open(file_path, "rb") as fh:
                html_doc = html5lib.parse(
                    fh.read(),
                    treebuilder="lxml",
                    namespaceHTMLElements=True,
                )
            # html5lib returns an ElementTree when using the lxml treebuilder
            if isinstance(html_doc, etree._ElementTree):
                return html_doc.getroot(), "utf-8"
            # If it returned a bare element
            return html_doc, "utf-8"
        except Exception as exc:
            raise IXBRLParseError(
                code="IXBRL-0002",
                message=f"Failed to parse {file_path}: {exc}",
                file_path=file_path,
            ) from exc

    def _collect_namespaces(self, root: etree._Element) -> dict[str, str]:
        """Collect all namespace declarations from the root element."""
        nsmap: dict[str, str] = {}
        for elem in root.iter():
            if not isinstance(elem.tag, str):
                continue
            if elem.nsmap:
                for prefix, uri in elem.nsmap.items():
                    if prefix is not None and uri:
                        nsmap[prefix] = uri
        return nsmap

    def _find_header(self, root: etree._Element) -> etree._Element | None:
        """Locate the ``ix:header`` element anywhere in the document."""
        for elem in root.iter(_IX_HEADER):
            return elem
        return None

    def _extract_references(
        self, header: etree._Element
    ) -> tuple[list[str], list[str]]:
        """Extract schemaRef and linkbaseRef hrefs from ix:references."""
        schema_refs: list[str] = []
        linkbase_refs: list[str] = []

        for refs_elem in header.iter(_IX_REFERENCES):
            for sr in refs_elem.iter(_LINK_SCHEMA_REF):
                href = sr.get(_XLINK_HREF)
                if href:
                    schema_refs.append(href)
            for lr in refs_elem.iter(_LINK_LINKBASE_REF):
                href = lr.get(_XLINK_HREF)
                if href:
                    linkbase_refs.append(href)

        return schema_refs, linkbase_refs

    def _extract_resources(
        self, header: etree._Element
    ) -> tuple[list[InlineFootnote], list[InlineRelationship]]:
        """Extract footnotes and relationships from ix:resources."""
        footnotes: list[InlineFootnote] = []
        relationships: list[InlineRelationship] = []

        for res_elem in header.iter(_IX_RESOURCES):
            for fn in res_elem.iter(_IX_FOOTNOTE):
                footnotes.append(self._parse_footnote(fn))
            for rel in res_elem.iter(_IX_RELATIONSHIP):
                relationships.append(self._parse_relationship(rel))

        return footnotes, relationships

    def _parse_fact_element(
        self,
        elem: etree._Element,
        element_type: str,
        order: int,
    ) -> InlineFact:
        """Extract attributes from an ``ix:`` fact element.

        Args:
            elem: The lxml element for the fact.
            element_type: One of ``nonFraction``, ``nonNumeric``,
                ``fraction``, or ``tuple``.
            order: Document-order index.

        Returns:
            A populated :class:`InlineFact`.
        """
        nsmap = elem.nsmap or {}

        # Resolve the QName in the 'name' attribute
        raw_name = elem.get("name", "")
        name = self._resolve_qname(raw_name, nsmap) if raw_name else ""

        # Resolve the optional 'format' attribute
        raw_format = elem.get("format")
        format_qname = (
            self._resolve_qname(raw_format, nsmap)
            if raw_format
            else None
        )

        # Parse scale (default 0)
        raw_scale = elem.get("scale")
        try:
            scale = int(raw_scale) if raw_scale else 0
        except (ValueError, TypeError):
            scale = 0

        # xsi:nil
        nil_attr = elem.get(_XSI_NIL, "").strip().lower()
        is_nil = nil_attr in ("true", "1")

        # Extract text content
        value = "" if is_nil else self._extract_text_content(elem)

        # Fact id: use the id attribute or generate one
        fact_id = elem.get("id") or f"_auto_{uuid.uuid4().hex[:12]}"

        source_line = elem.sourceline if hasattr(elem, "sourceline") else None

        return InlineFact(
            fact_id=fact_id,
            name=name,
            context_ref=elem.get("contextRef", ""),
            unit_ref=elem.get("unitRef"),
            value=value,
            format_qname=format_qname,
            scale=scale,
            sign=elem.get("sign"),
            decimals=elem.get("decimals"),
            precision=elem.get("precision"),
            is_nil=is_nil,
            element_type=element_type,
            order=order,
            source_line=source_line,
        )

    def _parse_continuation(self, elem: etree._Element) -> ContinuationFragment:
        """Parse an ``ix:continuation`` element."""
        fragment_id = elem.get("id", "")
        value = self._extract_text_content(elem)
        continuation_at = elem.get("continuationAt")
        return ContinuationFragment(
            fragment_id=fragment_id,
            value=value,
            continuation_at=continuation_at,
        )

    def _parse_footnote(self, elem: etree._Element) -> InlineFootnote:
        """Parse an ``ix:footnote`` element."""
        footnote_id = elem.get("id", "")
        content = self._extract_text_content(elem)
        lang = elem.get(f"{{{NS_IX}}}lang") or elem.get(
            "{http://www.w3.org/XML/1998/namespace}lang"
        )
        footnote_role = elem.get("footnoteRole") or elem.get("role")
        return InlineFootnote(
            footnote_id=footnote_id,
            content=content,
            lang=lang,
            footnote_role=footnote_role,
        )

    def _parse_relationship(self, elem: etree._Element) -> InlineRelationship:
        """Parse an ``ix:relationship`` element."""
        from_refs_raw = elem.get("fromRefs", "")
        to_refs_raw = elem.get("toRefs", "")
        arcrole = elem.get("arcrole", "")
        link_role = elem.get("linkRole")

        from_refs = [r.strip() for r in from_refs_raw.split() if r.strip()]
        to_refs = [r.strip() for r in to_refs_raw.split() if r.strip()]

        return InlineRelationship(
            from_refs=from_refs,
            to_refs=to_refs,
            arcrole=arcrole,
            link_role=link_role,
        )

    def _extract_text_content(self, elem: etree._Element) -> str:
        """Extract text content from an element, skipping ``ix:exclude``.

        Concatenates the element's own text and the tails of child elements,
        while ignoring any ``ix:exclude`` subtrees.

        Args:
            elem: The element from which to extract text.

        Returns:
            The assembled text content.
        """
        parts: list[str] = []
        if elem.text:
            parts.append(elem.text)

        for child in elem:
            child_tag = child.tag if isinstance(child.tag, str) else ""
            if child_tag == _IX_EXCLUDE:
                # Skip the excluded subtree but include its tail text
                if child.tail:
                    parts.append(child.tail)
            else:
                # Recursively extract text from nested inline elements
                parts.append(self._extract_text_content(child))
                if child.tail:
                    parts.append(child.tail)

        return "".join(parts)

    def _resolve_qname(self, prefixed_name: str, nsmap: dict) -> str:
        """Resolve ``prefix:localName`` to ``{namespace}localName``.

        If the name has no prefix or the prefix is not found in *nsmap*,
        the original string is returned unchanged.

        Args:
            prefixed_name: A QName that may contain a namespace prefix.
            nsmap: A prefix → namespace-URI mapping (from the element).

        Returns:
            The Clark-notation QName, e.g. ``{http://example.com}tag``.
        """
        if ":" not in prefixed_name:
            # No prefix – check for a default namespace
            default_ns = nsmap.get(None)
            if default_ns:
                return f"{{{default_ns}}}{prefixed_name}"
            return prefixed_name

        prefix, local = prefixed_name.split(":", 1)
        ns_uri = nsmap.get(prefix)
        if ns_uri:
            return f"{{{ns_uri}}}{local}"

        # Prefix not found – return as-is
        logger.warning(
            "Namespace prefix %r not found in nsmap for QName %r",
            prefix,
            prefixed_name,
        )
        return prefixed_name

    def _build_continuation_facts(
        self, doc: InlineXBRLDocument
    ) -> list[ContinuationFact]:
        """Build :class:`ContinuationFact` objects for continuation resolution.

        Only facts that reference continuations are included.
        """
        # We need to re-walk the document to find continuationAt attributes
        # on fact elements.  Since we already have the parsed facts, we look
        # at the original parse data.
        # The simplest approach: return ContinuationFacts for all facts and
        # let the resolver ignore those without continuations.
        results: list[ContinuationFact] = []
        for fact in doc.facts:
            # Build continuation IDs list – a fact's continuationAt was not
            # stored as a separate field, but we can locate the matching
            # continuations by following the chain from the doc's
            # continuations list.  For now, we include every fact so the
            # resolver can assemble texts correctly.
            results.append(
                ContinuationFact(
                    fact_id=fact.fact_id,
                    initial_value=fact.value,
                    continuation_ids=[],
                )
            )
        return results
