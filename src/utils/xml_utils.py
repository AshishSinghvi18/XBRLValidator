"""XML utility functions for XBRL processing.

Provides safe helpers for namespace extraction, element text retrieval,
and attribute parsing.  Uses ``lxml`` for XML processing and ``defusedxml``
for secure parsing.

References:
    - lxml documentation: https://lxml.de/
    - defusedxml: https://github.com/tiran/defusedxml
    - XBRL 2.1 §3 (namespaces)
"""

from __future__ import annotations

from typing import Any
from xml.etree.ElementTree import Element

from lxml import etree


def get_namespace(element: etree._Element | Element) -> str:
    """Extract the namespace URI from an element's tag.

    Works with both ``lxml`` and stdlib ``ElementTree`` elements.

    Args:
        element: An XML element.

    Returns:
        The namespace URI, or ``""`` if the element is in no namespace.

    Examples:
        >>> from lxml import etree
        >>> el = etree.Element("{http://example.com}foo")
        >>> get_namespace(el)
        'http://example.com'
    """
    tag = element.tag if isinstance(element.tag, str) else ""
    if tag.startswith("{"):
        return tag[1 : tag.index("}")]
    return ""


def get_local_name(element: etree._Element | Element) -> str:
    """Extract the local name from an element's tag.

    Args:
        element: An XML element.

    Returns:
        The local part of the tag name.

    Examples:
        >>> from lxml import etree
        >>> el = etree.Element("{http://example.com}foo")
        >>> get_local_name(el)
        'foo'
    """
    tag = element.tag if isinstance(element.tag, str) else ""
    if "}" in tag:
        return tag[tag.index("}") + 1 :]
    return tag


def get_clark_name(element: etree._Element | Element) -> str:
    """Return the full Clark-notation tag of an element.

    This is the raw ``element.tag`` string for ``lxml`` elements,
    already in Clark notation.

    Args:
        element: An XML element.

    Returns:
        Clark-notation tag string.
    """
    return element.tag if isinstance(element.tag, str) else ""


def element_text(element: etree._Element | Element) -> str:
    """Get the complete text content of an element (text + tail of children).

    Unlike ``element.text`` this concatenates all text nodes to handle
    mixed-content elements commonly found in Inline XBRL.

    Args:
        element: An XML element.

    Returns:
        The concatenated text content, stripped of leading/trailing whitespace.
    """
    parts: list[str] = []
    if element.text:
        parts.append(element.text)
    for child in element:
        if child.tail:
            parts.append(child.tail)
    return "".join(parts).strip()


def element_text_recursive(element: etree._Element | Element) -> str:
    """Recursively collect all text content within an element and its descendants.

    This is equivalent to ``lxml.etree.tostring(element, method='text')``,
    but works with stdlib ``ElementTree`` elements too.

    Args:
        element: An XML element.

    Returns:
        All descendant text content concatenated.
    """
    parts: list[str] = []

    def _collect(el: etree._Element | Element) -> None:
        """Depth-first text collector."""
        if el.text:
            parts.append(el.text)
        for child in el:
            _collect(child)
            if child.tail:
                parts.append(child.tail)

    _collect(element)
    return "".join(parts).strip()


def get_attr(
    element: etree._Element | Element,
    name: str,
    default: str | None = None,
) -> str | None:
    """Get an attribute value from an element.

    Handles both Clark-notation attribute names (``{ns}attr``) and
    plain attribute names.

    Args:
        element: An XML element.
        name:    Attribute name (plain or Clark notation).
        default: Default value if attribute is absent.

    Returns:
        Attribute value or *default*.
    """
    value = element.get(name)
    if value is not None:
        return value
    return default


def get_attr_bool(
    element: etree._Element | Element,
    name: str,
    default: bool = False,
) -> bool:
    """Get a boolean attribute value.

    Accepts XML Schema boolean values: ``"true"``, ``"1"`` for True;
    ``"false"``, ``"0"`` for False.

    Args:
        element: An XML element.
        name:    Attribute name.
        default: Default if the attribute is absent.

    Returns:
        Parsed boolean value.
    """
    raw = element.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1")


def build_nsmap(element: etree._Element) -> dict[str | None, str]:
    """Build a complete namespace map for an element and its ancestors.

    lxml's ``nsmap`` property only returns namespaces declared on the
    element itself.  This function walks up the tree to collect all
    inherited namespace bindings.

    Args:
        element: An lxml element.

    Returns:
        Combined namespace prefix → URI map.
    """
    nsmap: dict[str | None, str] = {}
    current: etree._Element | None = element
    while current is not None:
        for prefix, uri in current.nsmap.items():
            if prefix not in nsmap:
                nsmap[prefix] = uri
        parent = current.getparent()
        current = parent
    return nsmap


def safe_parse_xml(source: str | bytes, *, huge_tree: bool = False) -> etree._Element:
    """Parse XML from a string/bytes with security hardening.

    Disables network access, DTD loading, and entity resolution to
    prevent XXE and billion-laughs attacks.

    Args:
        source:    XML content as string or bytes.
        huge_tree: If ``True``, allow very deep/wide trees.

    Returns:
        Root element of the parsed document.

    Raises:
        etree.XMLSyntaxError: If the XML is malformed.
    """
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        dtd_validation=False,
        load_dtd=False,
        huge_tree=huge_tree,
        remove_comments=True,
        remove_pis=True,
    )
    if isinstance(source, str):
        source = source.encode("utf-8")
    return etree.fromstring(source, parser=parser)


def iter_elements(
    root: etree._Element,
    tag: str,
    *,
    namespaces: dict[str, str] | None = None,
) -> list[etree._Element]:
    """Find all descendant elements matching a tag.

    Args:
        root:       Root element to search from.
        tag:        Tag to match (Clark notation or local name).
        namespaces: Optional namespace map for XPath-based search.

    Returns:
        List of matching elements.
    """
    return list(root.iter(tag))


def parse_xml_value(value: str, type_hint: str = "string") -> Any:
    """Parse a raw XML attribute or text value into a Python type.

    Supported *type_hint* values: ``"string"``, ``"integer"``, ``"boolean"``,
    ``"decimal"``.

    Args:
        value:     Raw string value from XML.
        type_hint: Expected XSD simple type.

    Returns:
        Parsed Python value.

    Raises:
        ValueError: If the value cannot be parsed for the given type hint.
    """
    from decimal import Decimal

    value = value.strip()
    if type_hint == "string":
        return value
    if type_hint == "integer":
        return int(value)
    if type_hint == "boolean":
        if value.lower() in ("true", "1"):
            return True
        if value.lower() in ("false", "0"):
            return False
        raise ValueError(f"Invalid boolean value: {value!r}")
    if type_hint == "decimal":
        return Decimal(value)
    raise ValueError(f"Unsupported type_hint: {type_hint!r}")
