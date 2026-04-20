"""XML utility functions for secure and efficient XML processing.

All XML parsing in the validator MUST use :func:`safe_xml_parser` to
prevent XXE, DTD-bomb, and related attacks.

Spec references:
- OWASP XML External Entity Prevention Cheat Sheet
- lxml security documentation
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from lxml import etree


def safe_xml_parser() -> etree.XMLParser:
    """Create a hardened :class:`lxml.etree.XMLParser`.

    The returned parser has the following security settings:

    - ``resolve_entities=False`` — prevents XXE expansion.
    - ``no_network=True`` — blocks network access during parsing.
    - ``dtd_validation=False`` — skips DTD validation.
    - ``load_dtd=False`` — prevents loading external DTDs.
    - ``huge_tree=False`` — rejects very deep/wide trees.

    Returns:
        A configured :class:`lxml.etree.XMLParser` instance.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        dtd_validation=False,
        load_dtd=False,
        huge_tree=False,
    )


def get_text_content(element: etree._Element) -> str:
    """Get the full text content of an element including tail text.

    Concatenates ``element.text`` and ``element.tail`` (when present).

    Args:
        element: An lxml element.

    Returns:
        The combined text content, or an empty string if there is none.
    """
    text = element.text or ""
    tail = element.tail or ""
    return text + tail


def get_element_line(element: etree._Element) -> int:
    """Get the source line number of an element.

    Args:
        element: An lxml element that was parsed with line-number tracking.

    Returns:
        The 1-based line number, or ``0`` if line information is unavailable.
    """
    sourceline = element.sourceline
    return sourceline if sourceline is not None else 0


def strip_namespace(tag: str) -> str:
    """Remove the namespace from a Clark-notation tag string.

    Args:
        tag: A tag string, optionally in ``{namespace}localName`` form.

    Returns:
        The local name portion only.

    Examples:
        >>> strip_namespace("{http://www.xbrl.org/2003/instance}xbrl")
        'xbrl'
        >>> strip_namespace("xbrl")
        'xbrl'
    """
    if tag.startswith("{"):
        closing = tag.find("}")
        if closing != -1:
            return tag[closing + 1 :]
    return tag


def get_namespace(tag: str) -> str:
    """Extract the namespace URI from a Clark-notation tag string.

    Args:
        tag: A tag string in ``{namespace}localName`` form.

    Returns:
        The namespace URI, or an empty string if *tag* has no namespace.

    Examples:
        >>> get_namespace("{http://www.xbrl.org/2003/instance}xbrl")
        'http://www.xbrl.org/2003/instance'
        >>> get_namespace("xbrl")
        ''
    """
    if tag.startswith("{"):
        closing = tag.find("}")
        if closing != -1:
            return tag[1:closing]
    return ""


def iter_with_cleanup(context: Any) -> Generator[etree._Element, None, None]:
    """Iterate over an lxml iterparse context with memory cleanup.

    After yielding each element the element is cleared and its parent
    reference is released, keeping memory usage constant regardless of
    document size.

    Args:
        context: An :func:`lxml.etree.iterparse` context (iterable of
            ``(event, element)`` tuples).

    Yields:
        Each element from the context, already processed.
    """
    for _event, element in context:
        yield element
        # element.clear() releases the element's children and text,
        # but lxml still holds a back-reference from the parent.
        # parent.remove() drops that reference so the element (and
        # its subtree) can be garbage-collected immediately, keeping
        # memory usage O(1) regardless of document size.
        element.clear()
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)
