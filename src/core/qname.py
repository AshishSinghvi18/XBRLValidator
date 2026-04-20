"""QName handling utilities using Clark notation ``{namespace}localName``.

Throughout this validator, qualified names are stored in *Clark notation*
(also known as James Clark notation)::

    {http://www.xbrl.org/2003/instance}xbrl

This avoids prefix-dependency issues and enables O(1) equality checks.

References:
    - James Clark – XML Namespaces (http://www.jclark.com/xml/xmlns.htm)
    - XBRL 2.1 §4.1 (QName resolution)
"""

from __future__ import annotations

import re

_CLARK_RE = re.compile(r"^\{([^}]*)\}(.+)$")
"""Regex to parse Clark notation ``{namespace}localName``."""

_PREFIXED_RE = re.compile(r"^([^:]+):(.+)$")
"""Regex to parse prefixed QNames ``prefix:localName``."""


def parse_qname(text: str) -> tuple[str, str]:
    """Parse a Clark-notation QName into (namespace_uri, local_name).

    Args:
        text: A string in Clark notation, e.g. ``"{http://example.com}foo"``.

    Returns:
        A tuple ``(namespace_uri, local_name)``.

    Raises:
        ValueError: If *text* is not valid Clark notation.

    Examples:
        >>> parse_qname("{http://www.xbrl.org/2003/instance}xbrl")
        ('http://www.xbrl.org/2003/instance', 'xbrl')
    """
    match = _CLARK_RE.match(text)
    if match is None:
        raise ValueError(
            f"Invalid Clark-notation QName: {text!r}. "
            "Expected format: '{namespace}localName'"
        )
    return match.group(1), match.group(2)


def format_qname(namespace_uri: str, local_name: str) -> str:
    """Format a namespace URI and local name into Clark notation.

    Args:
        namespace_uri: The namespace URI (may be empty for no-namespace).
        local_name:    The local part of the QName.

    Returns:
        Clark-notation string ``{namespace_uri}local_name``.

    Raises:
        ValueError: If *local_name* is empty.

    Examples:
        >>> format_qname("http://www.xbrl.org/2003/instance", "xbrl")
        '{http://www.xbrl.org/2003/instance}xbrl'
    """
    if not local_name:
        raise ValueError("local_name must not be empty")
    return f"{{{namespace_uri}}}{local_name}"


def resolve_prefix(prefix: str, nsmap: dict[str | None, str]) -> str:
    """Resolve a namespace prefix to its URI using a namespace map.

    Args:
        prefix: The namespace prefix (e.g. ``"xbrli"``).
        nsmap:  A mapping of prefix → namespace URI.  A key of ``None``
                represents the default namespace.

    Returns:
        The namespace URI bound to *prefix*.

    Raises:
        KeyError: If *prefix* is not in *nsmap*.
    """
    try:
        return nsmap[prefix]
    except KeyError:
        available = ", ".join(repr(k) for k in nsmap if k is not None)
        raise KeyError(
            f"Prefix {prefix!r} not found in namespace map. "
            f"Available prefixes: {available or '(none)'}"
        ) from None


def qname_from_prefixed(prefixed: str, nsmap: dict[str | None, str]) -> str:
    """Convert a prefixed QName (``prefix:localName``) to Clark notation.

    If *prefixed* has no colon, the default namespace (key ``None``) is used.

    Args:
        prefixed: A prefixed QName string, e.g. ``"xbrli:context"``,
                  or an unprefixed local name, e.g. ``"context"``.
        nsmap:    Namespace prefix map.

    Returns:
        Clark-notation string.

    Raises:
        KeyError: If the prefix (or default namespace) is not in *nsmap*.
        ValueError: If the local name part is empty.

    Examples:
        >>> ns = {"xbrli": "http://www.xbrl.org/2003/instance"}
        >>> qname_from_prefixed("xbrli:context", ns)
        '{http://www.xbrl.org/2003/instance}context'
    """
    match = _PREFIXED_RE.match(prefixed)
    if match:
        prefix, local = match.group(1), match.group(2)
        ns_uri = resolve_prefix(prefix, nsmap)
    else:
        local = prefixed
        if None not in nsmap:
            raise KeyError(
                f"No default namespace in nsmap for unprefixed name {prefixed!r}"
            )
        ns_uri = nsmap[None]

    if not local:
        raise ValueError("local name part must not be empty")
    return format_qname(ns_uri, local)


def local_name(qname: str) -> str:
    """Extract the local-name part from a Clark-notation QName.

    If *qname* is not in Clark notation (no braces), returns it unchanged.

    Args:
        qname: Clark-notation QName or a plain local name.

    Returns:
        The local-name portion.

    Examples:
        >>> local_name("{http://www.xbrl.org/2003/instance}xbrl")
        'xbrl'
        >>> local_name("xbrl")
        'xbrl'
    """
    match = _CLARK_RE.match(qname)
    if match:
        return match.group(2)
    return qname


def namespace_uri(qname: str) -> str:
    """Extract the namespace URI from a Clark-notation QName.

    If *qname* is not in Clark notation, returns an empty string.

    Args:
        qname: Clark-notation QName or a plain local name.

    Returns:
        The namespace URI, or ``""`` if not present.

    Examples:
        >>> namespace_uri("{http://www.xbrl.org/2003/instance}xbrl")
        'http://www.xbrl.org/2003/instance'
        >>> namespace_uri("xbrl")
        ''
    """
    match = _CLARK_RE.match(qname)
    if match:
        return match.group(1)
    return ""
