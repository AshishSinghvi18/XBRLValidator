"""Date and time utility functions for XBRL temporal processing.

Handles parsing and comparison of XBRL date/datetime values as used in
``<xbrli:instant>``, ``<xbrli:startDate>``, and ``<xbrli:endDate>`` elements.

References:
    - XBRL 2.1 §4.7.2 (period element)
    - XML Schema Part 2 §3.2.7 (dateTime), §3.2.9 (date)
    - ISO 8601 date/time formats
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Union

# Type for values that can be either date or datetime
DateOrDatetime = Union[date, datetime]

# Regex for XSD date (YYYY-MM-DD with optional timezone)
_XSD_DATE_RE = re.compile(
    r"^(-?\d{4,})-(\d{2})-(\d{2})"
    r"(Z|[+-]\d{2}:\d{2})?$"
)

# Regex for XSD dateTime (YYYY-MM-DDThh:mm:ss with optional fractional seconds and TZ)
_XSD_DATETIME_RE = re.compile(
    r"^(-?\d{4,})-(\d{2})-(\d{2})"
    r"T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?"
    r"(Z|[+-]\d{2}:\d{2})?$"
)

_TZ_RE = re.compile(r"^([+-])(\d{2}):(\d{2})$")


def _parse_tz(tz_str: str | None) -> timezone | None:
    """Parse an XSD timezone suffix into a ``timezone`` object.

    Args:
        tz_str: Timezone string (``"Z"``, ``"+05:30"``, ``"-08:00"``, or ``None``).

    Returns:
        ``timezone`` object or ``None`` if no timezone specified.
    """
    if tz_str is None:
        return None
    if tz_str == "Z":
        return timezone.utc

    match = _TZ_RE.match(tz_str)
    if not match:
        raise ValueError(f"Invalid timezone: {tz_str!r}")
    sign = 1 if match.group(1) == "+" else -1
    hours = int(match.group(2))
    minutes = int(match.group(3))
    offset = timedelta(hours=hours, minutes=minutes) * sign
    return timezone(offset)


def parse_xsd_date(value: str) -> date:
    """Parse an XSD date string (``YYYY-MM-DD``) into a Python ``date``.

    Args:
        value: Date string in XML Schema ``date`` format.

    Returns:
        Parsed ``date`` object.

    Raises:
        ValueError: If *value* is not a valid XSD date.

    Examples:
        >>> parse_xsd_date("2024-01-15")
        datetime.date(2024, 1, 15)
    """
    value = value.strip()
    match = _XSD_DATE_RE.match(value)
    if not match:
        raise ValueError(f"Invalid XSD date: {value!r}")

    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    return date(year, month, day)


def parse_xsd_datetime(value: str) -> datetime:
    """Parse an XSD dateTime string into a Python ``datetime``.

    Args:
        value: DateTime string in XML Schema ``dateTime`` format.

    Returns:
        Parsed ``datetime`` object (timezone-aware if TZ is specified).

    Raises:
        ValueError: If *value* is not a valid XSD dateTime.

    Examples:
        >>> parse_xsd_datetime("2024-01-15T10:30:00Z")
        datetime.datetime(2024, 1, 15, 10, 30, tzinfo=datetime.timezone.utc)
    """
    value = value.strip()
    match = _XSD_DATETIME_RE.match(value)
    if not match:
        raise ValueError(f"Invalid XSD dateTime: {value!r}")

    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    hour = int(match.group(4))
    minute = int(match.group(5))
    second = int(match.group(6))
    frac_str = match.group(7)
    microsecond = 0
    if frac_str:
        # Pad or truncate to 6 digits for microseconds
        frac_str = frac_str[:6].ljust(6, "0")
        microsecond = int(frac_str)

    tz = _parse_tz(match.group(8))
    return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=tz)


def parse_xsd_date_or_datetime(value: str) -> DateOrDatetime:
    """Parse a string that may be either an XSD date or dateTime.

    Args:
        value: Date or dateTime string.

    Returns:
        ``date`` or ``datetime`` object.

    Raises:
        ValueError: If *value* matches neither format.

    Examples:
        >>> parse_xsd_date_or_datetime("2024-01-15")
        datetime.date(2024, 1, 15)
        >>> parse_xsd_date_or_datetime("2024-01-15T00:00:00")
        datetime.datetime(2024, 1, 15, 0, 0)
    """
    value = value.strip()
    if "T" in value:
        return parse_xsd_datetime(value)
    return parse_xsd_date(value)


def instant_to_date(value: str) -> date:
    """Parse an XBRL instant period value to a ``date``.

    Per XBRL 2.1 §4.7.2, an instant may be either a date or dateTime.
    When a dateTime is used, only the date part is significant for
    period comparisons.

    Args:
        value: Instant period text content.

    Returns:
        The effective date.

    Examples:
        >>> instant_to_date("2024-12-31")
        datetime.date(2024, 12, 31)
        >>> instant_to_date("2024-12-31T00:00:00")
        datetime.date(2024, 12, 31)
    """
    parsed = parse_xsd_date_or_datetime(value)
    if isinstance(parsed, datetime):
        return parsed.date()
    return parsed


def duration_days(start: str, end: str) -> int:
    """Calculate the number of days in an XBRL duration period.

    Args:
        start: Start date string.
        end:   End date string.

    Returns:
        Number of days (end - start).

    Raises:
        ValueError: If dates are invalid or end < start.

    Examples:
        >>> duration_days("2024-01-01", "2024-12-31")
        365
    """
    start_date = instant_to_date(start)
    end_date = instant_to_date(end)
    delta = end_date - start_date
    if delta.days < 0:
        raise ValueError(
            f"Duration end date {end} is before start date {start}"
        )
    return delta.days


def is_same_instant(a: str, b: str) -> bool:
    """Check whether two instant values refer to the same date.

    Args:
        a: First instant value.
        b: Second instant value.

    Returns:
        ``True`` if both instants resolve to the same date.

    Examples:
        >>> is_same_instant("2024-12-31", "2024-12-31T00:00:00")
        True
    """
    return instant_to_date(a) == instant_to_date(b)


def format_xsd_date(d: date) -> str:
    """Format a Python ``date`` as an XSD date string.

    Args:
        d: A ``date`` object.

    Returns:
        String in ``YYYY-MM-DD`` format.

    Examples:
        >>> format_xsd_date(date(2024, 1, 15))
        '2024-01-15'
    """
    return d.isoformat()


def format_xsd_datetime(dt: datetime) -> str:
    """Format a Python ``datetime`` as an XSD dateTime string.

    If the datetime is timezone-aware, the timezone offset is included.

    Args:
        dt: A ``datetime`` object.

    Returns:
        String in XSD dateTime format.

    Examples:
        >>> from datetime import timezone
        >>> format_xsd_datetime(datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc))
        '2024-01-15T10:30:00+00:00'
    """
    return dt.isoformat()
