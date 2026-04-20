"""Date and time utility functions for XBRL validation.

Provides parsing and formatting helpers for XBRL date strings and
ISO 8601 durations.

Spec references:
- XBRL 2.1 §4.7.1 (instant periods)
- XBRL 2.1 §4.7.2 (duration periods)
- ISO 8601 (date and duration formats)
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

# ISO 8601 duration pattern: P[nY][nM][nD][T[nH][nM][nS]]
_DURATION_RE = re.compile(
    r"^P"
    r"(?:(?P<years>\d+)Y)?"
    r"(?:(?P<months>\d+)M)?"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
    r")?$"
)


def parse_xbrl_date(date_str: str) -> date | datetime:
    """Parse an XBRL date string.

    Supports ``YYYY-MM-DD`` (returns :class:`date`) and
    ``YYYY-MM-DDThh:mm:ss`` (returns :class:`datetime`).

    Args:
        date_str: The date string to parse.

    Returns:
        A :class:`date` or :class:`datetime` instance.

    Raises:
        ValueError: If *date_str* does not match a supported format.

    Examples:
        >>> parse_xbrl_date("2024-01-15")
        datetime.date(2024, 1, 15)
        >>> parse_xbrl_date("2024-01-15T10:30:00")
        datetime.datetime(2024, 1, 15, 10, 30)
    """
    date_str = date_str.strip()

    if "T" in date_str:
        try:
            return datetime.fromisoformat(date_str)
        except ValueError as exc:
            raise ValueError(f"Invalid XBRL datetime string: {date_str!r}") from exc

    try:
        return date.fromisoformat(date_str)
    except ValueError as exc:
        raise ValueError(f"Invalid XBRL date string: {date_str!r}") from exc


def parse_xbrl_duration(duration_str: str) -> timedelta | None:
    """Parse an ISO 8601 duration string into a :class:`timedelta`.

    Supports the ``PnYnMnDTnHnMnS`` format. Years are approximated as
    365 days and months as 30 days since :class:`timedelta` does not
    have year/month fields.

    Args:
        duration_str: An ISO 8601 duration string (e.g. ``P1Y2M3D``).

    Returns:
        A :class:`timedelta` representing the duration, or ``None`` if
        the string does not match the expected format.

    Examples:
        >>> parse_xbrl_duration("P1Y2M3D")
        datetime.timedelta(days=428)
        >>> parse_xbrl_duration("PT1H30M")
        datetime.timedelta(seconds=5400)
    """
    duration_str = duration_str.strip()
    match = _DURATION_RE.match(duration_str)
    if not match:
        return None

    parts = match.groupdict()
    years = int(parts["years"] or 0)
    months = int(parts["months"] or 0)
    days = int(parts["days"] or 0)
    hours = int(parts["hours"] or 0)
    minutes = int(parts["minutes"] or 0)
    seconds = int(parts["seconds"] or 0)

    total_days = years * 365 + months * 30 + days
    return timedelta(days=total_days, hours=hours, minutes=minutes, seconds=seconds)


def is_valid_instant(date_str: str) -> bool:
    """Check whether *date_str* is a valid XBRL instant date.

    Args:
        date_str: A date or datetime string to validate.

    Returns:
        ``True`` if parseable as an XBRL date, ``False`` otherwise.
    """
    try:
        parse_xbrl_date(date_str)
        return True
    except ValueError:
        return False


def is_valid_duration(start_str: str, end_str: str) -> bool:
    """Check whether a start/end pair forms a valid XBRL duration.

    A valid duration requires ``start < end`` (per XBRL 2.1 §4.7.2).

    Args:
        start_str: Start date string.
        end_str: End date string.

    Returns:
        ``True`` if both dates parse successfully and start < end.
    """
    try:
        start = parse_xbrl_date(start_str)
        end = parse_xbrl_date(end_str)

        # Normalise to comparable types: if one is date and the other
        # datetime, promote the date to datetime at midnight.
        if isinstance(start, datetime) and isinstance(end, date) and not isinstance(end, datetime):
            end = datetime(end.year, end.month, end.day)
        elif isinstance(end, datetime) and isinstance(start, date) and not isinstance(start, datetime):
            start = datetime(start.year, start.month, start.day)

        return start < end  # type: ignore[operator]
    except ValueError:
        return False


def format_date(d: date) -> str:
    """Format a :class:`date` or :class:`datetime` as an XBRL date string.

    Args:
        d: The date to format.

    Returns:
        ``YYYY-MM-DD`` for a plain date, or ``YYYY-MM-DDThh:mm:ss``
        for a datetime.

    Examples:
        >>> format_date(date(2024, 1, 15))
        '2024-01-15'
    """
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%dT%H:%M:%S")
    return d.isoformat()
