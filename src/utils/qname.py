"""QName (Qualified Name) utility functions.

Provides helpers for parsing, creating, and resolving XML Qualified Names
in both ``prefix:localName`` and Clark ``{namespace}localName`` notation
as used throughout the XBRL specifications.

Spec references:
- XML Namespaces 1.0 §4 (Qualified Names)
- XBRL 2.1 §1.5 (Notation conventions)
"""

from __future__ import annotations


def parse_qname(qname_str: str) -> tuple[str, str]:
    """Split a prefixed QName into ``(prefix, local_name)``.

    Args:
        qname_str: A string of the form ``prefix:localName`` or just
            ``localName`` (no prefix).

    Returns:
        A tuple ``(prefix, local_name)``. If there is no prefix the first
        element is the empty string.

    Raises:
        ValueError: If *qname_str* is empty.

    Examples:
        >>> parse_qname("us-gaap:Assets")
        ('us-gaap', 'Assets')
        >>> parse_qname("Assets")
        ('', 'Assets')
    """
    if not qname_str:
        raise ValueError("QName string must not be empty")

    if ":" in qname_str:
        prefix, local_name = qname_str.split(":", maxsplit=1)
        return prefix, local_name
    return "", qname_str


def clark_notation(namespace: str, local_name: str) -> str:
    """Create a Clark-notation string ``{namespace}localName``.

    Args:
        namespace: The namespace URI.
        local_name: The local part of the name.

    Returns:
        The Clark-notation representation.

    Raises:
        ValueError: If *local_name* is empty.

    Examples:
        >>> clark_notation("http://www.xbrl.org/2003/instance", "xbrl")
        '{http://www.xbrl.org/2003/instance}xbrl'
    """
    if not local_name:
        raise ValueError("local_name must not be empty")
    return f"{{{namespace}}}{local_name}"


def parse_clark(clark_str: str) -> tuple[str, str]:
    """Parse a Clark-notation string into ``(namespace, local_name)``.

    Args:
        clark_str: A string of the form ``{namespace}localName``.

    Returns:
        A tuple ``(namespace, local_name)``.

    Raises:
        ValueError: If *clark_str* is not in valid Clark notation.

    Examples:
        >>> parse_clark("{http://www.xbrl.org/2003/instance}xbrl")
        ('http://www.xbrl.org/2003/instance', 'xbrl')
    """
    if not clark_str.startswith("{"):
        raise ValueError(f"Not a valid Clark notation string: {clark_str!r}")
    closing = clark_str.find("}")
    if closing == -1:
        raise ValueError(f"Not a valid Clark notation string: {clark_str!r}")
    namespace = clark_str[1:closing]
    local_name = clark_str[closing + 1 :]
    if not local_name:
        raise ValueError(f"Clark notation string has no local name: {clark_str!r}")
    return namespace, local_name


def resolve_qname(qname_str: str, namespaces: dict[str, str]) -> str:
    """Resolve a prefixed QName to Clark notation using a namespace map.

    Args:
        qname_str: A string of the form ``prefix:localName`` or just
            ``localName``.
        namespaces: Mapping of prefix → namespace URI. Use the empty
            string key ``""`` for the default namespace.

    Returns:
        The Clark-notation representation ``{namespace}localName``.

    Raises:
        ValueError: If the prefix is not found in *namespaces*.

    Examples:
        >>> ns = {"xbrli": "http://www.xbrl.org/2003/instance"}
        >>> resolve_qname("xbrli:context", ns)
        '{http://www.xbrl.org/2003/instance}context'
    """
    prefix, local_name = parse_qname(qname_str)
    if prefix not in namespaces:
        raise ValueError(f"Prefix {prefix!r} not found in namespace map")
    return clark_notation(namespaces[prefix], local_name)
