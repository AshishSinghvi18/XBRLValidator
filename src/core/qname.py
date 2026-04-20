"""QName utilities for XBRL namespace-qualified names.

All QNames in this engine use James Clark notation internally:
``{http://example.com/ns}localName``.  Functions in this module
convert between prefixed form (``prefix:localName``), Clark notation,
and ``(namespace, localName)`` tuples.
"""

from __future__ import annotations

import re

from src.core.constants import STANDARD_NAMESPACES

# Pre-compiled pattern for Clark notation: {namespace}localName
_CLARK_RE: re.Pattern[str] = re.compile(r"^\{([^}]*)\}(.+)$")

# Pre-compiled pattern for prefixed QName: prefix:localName
_PREFIXED_RE: re.Pattern[str] = re.compile(r"^([^:]+):(.+)$")


def parse_qname(
    text: str,
    nsmap: dict[str, str],
) -> tuple[str, str]:
    """Resolve a prefixed QName to ``(namespace, local_name)``.

    Args:
        text: QName string, e.g. ``"xbrli:context"`` or ``"localOnly"``.
        nsmap: Mapping of prefix → namespace URI.  The key ``""`` (empty
            string) represents the default namespace.

    Returns:
        ``(namespace_uri, local_name)`` tuple.

    Raises:
        ValueError: If the prefix is not found in *nsmap*.
    """
    clark_match = _CLARK_RE.match(text)
    if clark_match:
        return clark_match.group(1), clark_match.group(2)

    prefixed_match = _PREFIXED_RE.match(text)
    if prefixed_match:
        prefix, local = prefixed_match.group(1), prefixed_match.group(2)
        ns = nsmap.get(prefix)
        if ns is None:
            raise ValueError(
                f"Prefix '{prefix}' not found in namespace map: {sorted(nsmap)}"
            )
        return ns, local

    # No prefix — use default namespace (empty-string key) if available.
    default_ns = nsmap.get("", "")
    return default_ns, text


def format_qname(namespace: str, local_name: str) -> str:
    """Build a Clark-notation QName from namespace and local name.

    Args:
        namespace: Namespace URI (may be empty for no-namespace names).
        local_name: The local part of the name.

    Returns:
        Clark-notation string ``"{namespace}localName"`` or just
        ``"localName"`` when namespace is empty.
    """
    if namespace:
        return f"{{{namespace}}}{local_name}"
    return local_name


def clark_notation(namespace: str, local_name: str) -> str:
    """Alias for :func:`format_qname` — returns ``"{ns}local"``."""
    return format_qname(namespace, local_name)


def split_clark(clark: str) -> tuple[str, str]:
    """Split a Clark-notation string into ``(namespace, local_name)``.

    Args:
        clark: String in the form ``"{namespace}localName"``.

    Returns:
        ``(namespace, local_name)`` tuple.

    Raises:
        ValueError: If *clark* is not valid Clark notation.
    """
    m = _CLARK_RE.match(clark)
    if m:
        return m.group(1), m.group(2)
    # No namespace — treat the entire string as a local name.
    if "{" not in clark:
        return "", clark
    raise ValueError(f"Invalid Clark notation: {clark!r}")


def is_standard_namespace(namespace: str) -> bool:
    """Return ``True`` if *namespace* is a well-known XBRL/W3C namespace.

    Uses :data:`src.core.constants.STANDARD_NAMESPACES` plus the
    ``NS_IXT_PREFIX`` prefix match (inline transformations use
    versioned namespace URIs).
    """
    if namespace in STANDARD_NAMESPACES:
        return True
    # Inline XBRL transformation namespaces are versioned but share a prefix.
    from src.core.constants import NS_IXT_PREFIX

    return bool(namespace.startswith(NS_IXT_PREFIX))
