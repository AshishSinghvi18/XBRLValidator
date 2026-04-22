"""Locale and language tag utilities.

Provides BCP 47 language tag validation and normalisation for use in
XBRL label resolution and iXBRL ``xml:lang`` processing.

References:
    - BCP 47 / RFC 5646 (Tags for Identifying Languages)
    - XBRL 2.1 §5.2.2.2.1 (label language matching)
    - Inline XBRL 1.1 §4.3 (xml:lang inheritance)
"""

from __future__ import annotations

import re
from typing import Final

# BCP 47 language tag regex (simplified but practical)
# Covers: language[-script][-region][-variant]*[-extension]*[-privateuse]
# Full BCP 47 is extremely complex; this covers the patterns used in XBRL practice.
_BCP47_RE: Final[re.Pattern[str]] = re.compile(
    r"^"
    r"(?P<language>[a-zA-Z]{2,3})"                # Primary language subtag (2-3 alpha)
    r"(?:-(?P<extlang>[a-zA-Z]{3}))?"              # Optional extended language subtag
    r"(?:-(?P<script>[a-zA-Z]{4}))?"               # Optional script subtag (4 alpha)
    r"(?:-(?P<region>[a-zA-Z]{2}|[0-9]{3}))?"      # Optional region subtag
    r"(?:-(?P<variants>(?:[a-zA-Z0-9]{5,8}|[0-9][a-zA-Z0-9]{3})"  # Variants
    r"(?:-(?:[a-zA-Z0-9]{5,8}|[0-9][a-zA-Z0-9]{3}))*))?"
    r"(?:-(?P<extensions>[a-zA-Z0-9](?:-[a-zA-Z0-9]{2,8})+))?"    # Extensions
    r"(?:-(?P<privateuse>x(?:-[a-zA-Z0-9]{1,8})+))?$",             # Private use
    re.IGNORECASE,
)

# Grandfathered / irregular tags (subset of commonly encountered ones)
_GRANDFATHERED_TAGS: Final[frozenset[str]] = frozenset({
    "i-default",
    "i-enochian",
    "i-mingo",
    "sgn-be-fr",
    "sgn-be-nl",
    "sgn-ch-de",
    "art-lojban",
    "cel-gaulish",
    "zh-guoyu",
    "zh-hakka",
    "zh-min",
    "zh-min-nan",
    "zh-xiang",
})


def is_valid_language_tag(tag: str) -> bool:
    """Check whether a string is a valid BCP 47 language tag.

    This is a practical validator covering patterns used in XBRL
    taxonomies and filings.  It does not validate subtag values
    against the IANA Language Subtag Registry.

    Args:
        tag: Language tag string.

    Returns:
        ``True`` if the tag has valid BCP 47 structure.

    Examples:
        >>> is_valid_language_tag("en")
        True
        >>> is_valid_language_tag("en-US")
        True
        >>> is_valid_language_tag("zh-Hant-TW")
        True
        >>> is_valid_language_tag("not a tag!")
        False
    """
    if not tag:
        return False
    # Check grandfathered tags
    if tag.lower() in _GRANDFATHERED_TAGS:
        return True
    return _BCP47_RE.match(tag) is not None


def normalise_language_tag(tag: str) -> str:
    """Normalise a BCP 47 language tag to canonical casing.

    Per BCP 47 §2.1.1:
    - Language subtag → lowercase
    - Script subtag → title case
    - Region subtag → uppercase
    - All other subtags → lowercase

    Args:
        tag: Language tag string.

    Returns:
        Normalised tag.

    Raises:
        ValueError: If *tag* is not a valid BCP 47 tag.

    Examples:
        >>> normalise_language_tag("EN-us")
        'en-US'
        >>> normalise_language_tag("ZH-hant-tw")
        'zh-Hant-TW'
    """
    if not tag:
        raise ValueError("Language tag must not be empty")

    # Handle grandfathered tags
    if tag.lower() in _GRANDFATHERED_TAGS:
        return tag.lower()

    match = _BCP47_RE.match(tag)
    if not match:
        raise ValueError(f"Invalid BCP 47 language tag: {tag!r}")

    parts: list[str] = []

    # Language subtag → lowercase
    language = match.group("language")
    parts.append(language.lower())

    # Extended language → lowercase
    extlang = match.group("extlang")
    if extlang:
        parts.append(extlang.lower())

    # Script → title case
    script = match.group("script")
    if script:
        parts.append(script.title())

    # Region → uppercase
    region = match.group("region")
    if region:
        parts.append(region.upper())

    # Variants → lowercase
    variants = match.group("variants")
    if variants:
        parts.append(variants.lower())

    # Extensions → lowercase
    extensions = match.group("extensions")
    if extensions:
        parts.append(extensions.lower())

    # Private use → lowercase
    privateuse = match.group("privateuse")
    if privateuse:
        parts.append(privateuse.lower())

    return "-".join(parts)


def language_matches(tag: str, pattern: str) -> bool:
    """Check if a language tag matches a pattern using prefix matching.

    Per RFC 4647 §3.3 (Basic Filtering), a tag matches a pattern if
    the pattern is a case-insensitive prefix of the tag, matching on
    subtag boundaries.

    Args:
        tag:     The language tag to check (e.g. ``"en-US"``).
        pattern: The pattern to match against (e.g. ``"en"``).

    Returns:
        ``True`` if *tag* matches *pattern*.

    Examples:
        >>> language_matches("en-US", "en")
        True
        >>> language_matches("en-US", "en-US")
        True
        >>> language_matches("en-US", "en-GB")
        False
        >>> language_matches("en", "en-US")
        False
    """
    tag_lower = tag.lower()
    pattern_lower = pattern.lower()

    if tag_lower == pattern_lower:
        return True

    # Pattern must be a prefix followed by a hyphen
    return tag_lower.startswith(pattern_lower + "-")


def extract_primary_language(tag: str) -> str:
    """Extract the primary language subtag from a BCP 47 tag.

    Args:
        tag: A BCP 47 language tag.

    Returns:
        The primary language subtag in lowercase.

    Examples:
        >>> extract_primary_language("en-US")
        'en'
        >>> extract_primary_language("zh-Hant-TW")
        'zh'
    """
    return tag.split("-")[0].lower()


def find_best_match(
    target: str,
    available: list[str],
    *,
    fallback: str | None = None,
) -> str | None:
    """Find the best matching language tag from a list of available tags.

    Implements a simplified version of RFC 4647 §3.4 (Lookup):
    1. Exact match (case-insensitive).
    2. Prefix match (longest match first).
    3. Fallback.

    Args:
        target:    Desired language tag.
        available: List of available language tags.
        fallback:  Fallback tag if no match found.

    Returns:
        Best matching tag from *available*, or *fallback*.

    Examples:
        >>> find_best_match("en-US", ["en", "de", "fr"])
        'en'
        >>> find_best_match("ja", ["en", "de"], fallback="en")
        'en'
    """
    target_lower = target.lower()

    # Exact match
    for t in available:
        if t.lower() == target_lower:
            return t

    # Prefix match (try progressively shorter prefixes)
    parts = target_lower.split("-")
    for length in range(len(parts) - 1, 0, -1):
        prefix = "-".join(parts[:length])
        for t in available:
            if t.lower() == prefix:
                return t

    return fallback
