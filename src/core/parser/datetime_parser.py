"""XBRL date, time, duration, and period parsing utilities.

Parses XML Schema date/dateTime/duration formats and XBRL ``<xbrli:period>``
elements into strongly-typed Python objects.

References:
    * XML Schema Part 2 — Datatypes §3.2.7 (date), §3.2.7 (dateTime), §3.2.6 (duration)
    * XBRL 2.1 §4.7.2 — Period element structure
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Union

import isodate
from dateutil.parser import isoparse
from lxml import etree

from src.core.constants import NS_XBRLI
from src.core.types import PeriodType

__all__ = [
    "Period",
    "parse_xml_date",
    "parse_xml_datetime",
    "parse_xml_duration",
    "parse_xbrl_period",
    "period_contains",
    "periods_equal",
]

# ---------------------------------------------------------------------------
# Regex for XML Schema date (YYYY-MM-DD with optional timezone)
# ---------------------------------------------------------------------------
_XSD_DATE_RE = re.compile(
    r"^-?(?P<year>\d{4,})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"(?P<tz>Z|[+-]\d{2}:\d{2})?$"
)


# ---------------------------------------------------------------------------
# Period dataclass
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Period:
    """Immutable representation of an XBRL period.

    Attributes:
        period_type: The kind of period (INSTANT, DURATION, or FOREVER).
        start_date:  Start date for DURATION periods; ``None`` otherwise.
        end_date:    End date for DURATION periods, or the instant date for
                     INSTANT periods; ``None`` for FOREVER.
        instant:     The instant date for INSTANT periods; ``None`` otherwise.
                     Always equal to *end_date* when the period is INSTANT.
        is_forever:  ``True`` when the period is FOREVER.
    """

    period_type: PeriodType
    start_date: date | None = None
    end_date: date | None = None
    instant: date | None = None
    is_forever: bool = False


# ---------------------------------------------------------------------------
# XML Schema date parsing
# ---------------------------------------------------------------------------
def parse_xml_date(text: str) -> date:
    """Parse an XML Schema ``date`` value into a :class:`datetime.date`.

    Accepts formats such as ``2024-01-15``, ``2024-01-15Z``, and
    ``2024-01-15+05:30``.  The timezone offset, if present, is discarded
    because :class:`datetime.date` is timezone-naïve.

    Args:
        text: The raw date string.

    Returns:
        A :class:`datetime.date` instance.

    Raises:
        ValueError: If *text* is not a valid XML Schema date.
    """
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty date string")

    match = _XSD_DATE_RE.match(stripped)
    if match:
        return date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )

    # Fallback: let dateutil attempt to parse it.  This handles edge-cases
    # that the regex might miss while still raising on truly invalid input.
    try:
        parsed = isoparse(stripped)
        return parsed.date() if isinstance(parsed, datetime) else parsed
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid XML Schema date: {text!r}") from exc


# ---------------------------------------------------------------------------
# XML Schema dateTime parsing
# ---------------------------------------------------------------------------
def parse_xml_datetime(text: str) -> datetime:
    """Parse an XML Schema ``dateTime`` value into a :class:`datetime.datetime`.

    Returns a timezone-aware :class:`datetime.datetime` when a timezone
    designator is present; otherwise returns a naïve instance.

    Args:
        text: The raw dateTime string.

    Returns:
        A :class:`datetime.datetime` instance.

    Raises:
        ValueError: If *text* is not a valid XML Schema dateTime.
    """
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty dateTime string")

    try:
        return isoparse(stripped)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid XML Schema dateTime: {text!r}") from exc


# ---------------------------------------------------------------------------
# XML Schema / ISO 8601 duration parsing
# ---------------------------------------------------------------------------
def parse_xml_duration(text: str) -> Union[timedelta, isodate.Duration]:
    """Parse an ISO 8601 / XML Schema ``duration`` into a delta object.

    For durations expressible in days and smaller units the return type is
    :class:`datetime.timedelta`.  For durations involving months or years
    the return type is :class:`isodate.Duration` (which supports calendar
    arithmetic via :pypi:`python-dateutil` *relativedelta*).

    Args:
        text: The raw duration string (e.g. ``P1Y2M3DT4H5M6S``).

    Returns:
        A :class:`timedelta` or :class:`isodate.Duration`.

    Raises:
        ValueError: If *text* is not a valid ISO 8601 duration.
    """
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty duration string")

    try:
        return isodate.parse_duration(stripped)
    except (isodate.ISO8601Error, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid XML Schema duration: {text!r}") from exc


# ---------------------------------------------------------------------------
# XBRL period element parsing
# ---------------------------------------------------------------------------
def _elem_text(parent: etree._Element, tag: str) -> str | None:
    """Return stripped text of a direct child element, or ``None``."""
    child = parent.find(tag)
    if child is not None and child.text is not None:
        return child.text.strip()
    return None


def _parse_date_or_datetime(text: str) -> date:
    """Parse text that may be either an XML Schema date or dateTime.

    XBRL allows both ``date`` and ``dateTime`` lexical forms inside
    ``<xbrli:instant>``, ``<xbrli:startDate>``, and ``<xbrli:endDate>``.
    When a dateTime is provided the date portion is extracted.
    """
    if "T" in text:
        return parse_xml_datetime(text).date()
    return parse_xml_date(text)


def parse_xbrl_period(xml_elem: etree._Element) -> Period:
    """Parse an XBRL ``<xbrli:period>`` element into a :class:`Period`.

    The element must contain exactly one of:

    * ``<xbrli:instant>``                           → INSTANT period
    * ``<xbrli:startDate>`` + ``<xbrli:endDate>``   → DURATION period
    * ``<xbrli:forever/>``                           → FOREVER period

    Args:
        xml_elem: An lxml element representing ``<xbrli:period>``.

    Returns:
        A :class:`Period` instance.

    Raises:
        ValueError: If the element does not match any recognised pattern.
    """
    tag_instant = f"{{{NS_XBRLI}}}instant"
    tag_start = f"{{{NS_XBRLI}}}startDate"
    tag_end = f"{{{NS_XBRLI}}}endDate"
    tag_forever = f"{{{NS_XBRLI}}}forever"

    # --- instant ---
    instant_text = _elem_text(xml_elem, tag_instant)
    if instant_text is not None:
        d = _parse_date_or_datetime(instant_text)
        return Period(
            period_type=PeriodType.INSTANT,
            instant=d,
            end_date=d,
        )

    # --- duration ---
    start_text = _elem_text(xml_elem, tag_start)
    end_text = _elem_text(xml_elem, tag_end)
    if start_text is not None and end_text is not None:
        return Period(
            period_type=PeriodType.DURATION,
            start_date=_parse_date_or_datetime(start_text),
            end_date=_parse_date_or_datetime(end_text),
        )

    # --- forever ---
    if xml_elem.find(tag_forever) is not None:
        return Period(
            period_type=PeriodType.FOREVER,
            is_forever=True,
        )

    raise ValueError(
        "Unrecognised <xbrli:period> structure: expected "
        "<instant>, <startDate>+<endDate>, or <forever>"
    )


# ---------------------------------------------------------------------------
# Period comparison helpers
# ---------------------------------------------------------------------------
def period_contains(period: Period, instant: date) -> bool:
    """Check whether *instant* falls within *period*.

    Containment semantics follow XBRL 2.1 §4.7.2:

    * **INSTANT** — ``True`` iff *instant* equals the period's instant date.
    * **DURATION** — ``True`` iff ``start_date <= instant < end_date``
      (start-inclusive, end-exclusive).
    * **FOREVER** — always ``True``.

    Args:
        period:  The period to test against.
        instant: The date to check.

    Returns:
        ``True`` if the date is contained in the period.
    """
    if period.period_type is PeriodType.FOREVER:
        return True
    if period.period_type is PeriodType.INSTANT:
        return instant == period.instant
    if period.period_type is PeriodType.DURATION:
        if period.start_date is None or period.end_date is None:
            return False
        return period.start_date <= instant < period.end_date
    return False


def periods_equal(a: Period, b: Period) -> bool:
    """Check structural equality of two :class:`Period` instances.

    Two periods are equal when they share the same type and the same
    date boundaries:

    * **INSTANT** — same instant date.
    * **DURATION** — same start *and* end dates.
    * **FOREVER** — both are FOREVER.

    Args:
        a: First period.
        b: Second period.

    Returns:
        ``True`` if the periods are structurally equal.
    """
    if a.period_type is not b.period_type:
        return False
    if a.period_type is PeriodType.INSTANT:
        return a.instant == b.instant
    if a.period_type is PeriodType.DURATION:
        return a.start_date == b.start_date and a.end_date == b.end_date
    # FOREVER
    return True
