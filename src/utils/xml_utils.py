"""XML utilities — Rule 3: Zero-Trust Parsing.

All XML parsing goes through :func:`safe_parse_xml` which disables
external entities, DTD loading, network resolution, and caps entity
expansion.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO

from lxml import etree

from src.core.constants import DEFAULT_MAX_ENTITY_EXPANSIONS
from src.core.exceptions import XMLParseError, XXEError


def _hardened_parser(
    *,
    huge_tree: bool = False,
    max_entity_expansions: int = DEFAULT_MAX_ENTITY_EXPANSIONS,
) -> etree.XMLParser:
    """Create an lxml ``XMLParser`` with all dangerous features disabled.

    Spec: Rule 3 — Zero-Trust Parsing.
    """
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        dtd_validation=False,
        load_dtd=False,
        huge_tree=huge_tree,
        recover=False,
    )
    # lxml 4.9+: set_element_class_lookup is not needed for security.
    # Entity expansion is bounded by resolve_entities=False.
    return parser


def safe_parse_xml(
    source: str | Path | IO[bytes],
    *,
    huge_tree: bool = False,
) -> etree._ElementTree:
    """Parse an XML document with all XXE / entity-expansion protections.

    Args:
        source: File path, ``Path`` object, or binary file-like.
        huge_tree: Allow very deep / wide trees (for huge filings).

    Returns:
        Parsed ``lxml.etree._ElementTree``.

    Raises:
        XXEError: If external entity usage is detected.
        XMLParseError: On any well-formedness error.
    """
    parser = _hardened_parser(huge_tree=huge_tree)
    try:
        tree = etree.parse(str(source), parser) if isinstance(source, (str, Path)) else etree.parse(source, parser)
    except etree.XMLSyntaxError as exc:
        msg = str(exc)
        if "entity" in msg.lower() or "xxe" in msg.lower():
            raise XXEError(
                message=f"Potential XXE in document: {msg}",
                code="SEC-0001",
            ) from exc
        raise XMLParseError(
            message=f"XML parse error: {msg}",
            code="PARSE-0001",
            file_path=str(source) if isinstance(source, (str, Path)) else "<stream>",
            line=getattr(exc, "lineno", None),
            column=getattr(exc, "offset", None),
        ) from exc
    return tree


def safe_parse_xml_string(
    xml_bytes: bytes,
    *,
    huge_tree: bool = False,
) -> etree._Element:
    """Parse an XML byte string with full protections.

    Returns the root element.

    Raises:
        XXEError: If external entity usage is detected.
        XMLParseError: On any well-formedness error.
    """
    parser = _hardened_parser(huge_tree=huge_tree)
    try:
        return etree.fromstring(xml_bytes, parser)
    except etree.XMLSyntaxError as exc:
        msg = str(exc)
        if "entity" in msg.lower():
            raise XXEError(
                message=f"Potential XXE in XML string: {msg}",
                code="SEC-0001",
            ) from exc
        raise XMLParseError(
            message=f"XML parse error: {msg}",
            code="PARSE-0001",
            file_path="<string>",
            line=getattr(exc, "lineno", None),
            column=getattr(exc, "offset", None),
        ) from exc


def get_element_text(element: etree._Element) -> str:
    """Return the full text content of *element* (including tail of children).

    Uses ``itertext()`` to collect all text nodes, joining them without
    separator — matching the XPath ``string()`` semantics.
    """
    return "".join(element.itertext())


def get_attribute(
    element: etree._Element,
    name: str,
    *,
    namespace: str | None = None,
    default: str | None = None,
) -> str | None:
    """Safely read an attribute from *element*.

    Args:
        element: lxml element.
        name: Local attribute name.
        namespace: Namespace URI (if the attribute is namespace-qualified).
        default: Value to return if the attribute is absent.

    Returns:
        Attribute value string, or *default*.
    """
    qname = f"{{{namespace}}}{name}" if namespace else name
    return element.get(qname, default)


def namespace_map_from_element(element: etree._Element) -> dict[str, str]:
    """Build a ``{prefix: namespace}`` map from *element*'s in-scope namespaces.

    The default namespace (if any) uses the empty string ``""`` as key.
    """
    nsmap: dict[str, str] = {}
    for prefix, uri in element.nsmap.items():
        nsmap[prefix if prefix is not None else ""] = uri
    return nsmap
