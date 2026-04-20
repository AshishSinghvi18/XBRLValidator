"""Date/time utilities for XBRL temporal values.

Handles ISO 8601 date and datetime parsing as required by
XML Schema ``xs:date`` and ``xs:dateTime`` types.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

from dateutil import parser as dateutil_parser

# ISO 8601 date pattern: YYYY-MM-DD with optional timezone
_ISO_DATE_RE: re.Pattern[str] = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})"
    r"(Z|[+-]\d{2}:\d{2})?$"
)

# ISO 8601 dateTime pattern (simplified — dateutil handles the heavy lifting)
_ISO_DATETIME_RE: re.Pattern[str] = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"
)


def parse_iso_date(text: str) -> date:
    """Parse an ISO 8601 / XML Schema ``xs:date`` string.

    Accepts formats like ``"2024-01-15"``, ``"2024-01-15Z"``,
    ``"2024-01-15+05:30"``.

    Args:
        text: Date string.

    Returns:
        A :class:`datetime.date` object.

    Raises:
        ValueError: If the string is not a valid date.
    """
    text = text.strip()
    m = _ISO_DATE_RE.match(text)
    if not m:
        raise ValueError(f"Invalid ISO date: {text!r}")
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return date(year, month, day)


def parse_iso_datetime(text: str) -> datetime:
    """Parse an ISO 8601 / XML Schema ``xs:dateTime`` string.

    Returns a timezone-aware ``datetime``.  If no timezone is specified,
    UTC is assumed (per XBRL processing conventions).

    Args:
        text: DateTime string.

    Returns:
        A timezone-aware :class:`datetime.datetime`.

    Raises:
        ValueError: If the string is not a valid datetime.
    """
    text = text.strip()
    try:
        dt = dateutil_parser.isoparse(text)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid ISO datetime: {text!r}") from exc
    # Ensure timezone awareness — default to UTC.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def now_utc() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def format_iso_date(d: date) -> str:
    """Format a date as ``YYYY-MM-DD``."""
    return d.isoformat()


def format_iso_datetime(dt: datetime) -> str:
    """Format a datetime as an ISO 8601 string with timezone.

    If the datetime is UTC, uses the ``Z`` suffix.
    """
    if dt.tzinfo is not None and dt.utcoffset() == UTC.utcoffset(None):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return dt.isoformat()


def is_valid_iso_date(text: str) -> bool:
    """Return ``True`` if *text* is a valid ISO 8601 date string."""
    try:
        parse_iso_date(text)
        return True
    except ValueError:
        return False


def is_valid_iso_datetime(text: str) -> bool:
    """Return ``True`` if *text* is a valid ISO 8601 datetime string."""
    try:
        parse_iso_datetime(text)
        return True
    except ValueError:
        return False
