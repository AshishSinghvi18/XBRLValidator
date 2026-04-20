"""Date/time parsing for XBRL temporal values.

Handles XML Schema date, dateTime, and duration types as used in
XBRL period elements and other temporal attributes.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

import isodate
from lxml import etree

from src.core.constants import NS_XBRLI
from src.core.exceptions import ParseError
from src.core.model.xbrl_model import Period
from src.core.types import PeriodType
from src.utils.datetime_utils import parse_iso_date, parse_iso_datetime

# Duration pattern per XML Schema xs:duration
_DURATION_RE: re.Pattern[str] = re.compile(
    r"^-?P"
    r"(?:(\d+)Y)?"
    r"(?:(\d+)M)?"
    r"(?:(\d+)D)?"
    r"(?:T"
    r"(?:(\d+)H)?"
    r"(?:(\d+)M)?"
    r"(?:(\d+(?:\.\d+)?)S)?"
    r")?$"
)


def parse_xml_date(text: str) -> date:
    """Parse an XML Schema ``xs:date`` value.

    Accepts formats: ``YYYY-MM-DD``, ``YYYY-MM-DDZ``, ``YYYY-MM-DD±HH:MM``.

    Args:
        text: Date string to parse.

    Returns:
        A ``datetime.date`` object.

    Raises:
        ParseError: If the text is not a valid xs:date.
    """
    stripped = text.strip()
    if not stripped:
        raise ParseError(
            message="Empty string is not a valid xs:date",
            code="PARSE-0040",
        )
    try:
        return parse_iso_date(stripped)
    except ValueError as exc:
        raise ParseError(
            message=f"Invalid xs:date: {stripped!r}: {exc}",
            code="PARSE-0041",
        ) from exc


def parse_xml_datetime(text: str) -> datetime:
    """Parse an XML Schema ``xs:dateTime`` value.

    Returns a timezone-aware datetime (UTC if none specified).

    Args:
        text: DateTime string to parse.

    Returns:
        A timezone-aware ``datetime.datetime`` object.

    Raises:
        ParseError: If the text is not a valid xs:dateTime.
    """
    stripped = text.strip()
    if not stripped:
        raise ParseError(
            message="Empty string is not a valid xs:dateTime",
            code="PARSE-0042",
        )
    try:
        return parse_iso_datetime(stripped)
    except ValueError as exc:
        raise ParseError(
            message=f"Invalid xs:dateTime: {stripped!r}: {exc}",
            code="PARSE-0043",
        ) from exc


def parse_xml_duration(text: str) -> timedelta:
    """Parse an XML Schema ``xs:duration`` value.

    Uses the ``isodate`` library for parsing, but returns a
    ``datetime.timedelta`` for use in date arithmetic.

    Note: Year and month components are approximated (1 year = 365 days,
    1 month = 30 days) since ``timedelta`` cannot represent variable-length
    periods.

    Args:
        text: Duration string (e.g., ``"P1Y2M3D"``, ``"PT1H30M"``).

    Returns:
        A ``datetime.timedelta`` representing the duration.

    Raises:
        ParseError: If the text is not a valid xs:duration.
    """
    stripped = text.strip()
    if not stripped:
        raise ParseError(
            message="Empty string is not a valid xs:duration",
            code="PARSE-0044",
        )

    try:
        parsed = isodate.parse_duration(stripped)
    except (isodate.ISO8601Error, ValueError) as exc:
        raise ParseError(
            message=f"Invalid xs:duration: {stripped!r}: {exc}",
            code="PARSE-0045",
        ) from exc

    # isodate may return a Duration object (with year/month) or timedelta
    if isinstance(parsed, timedelta):
        return parsed

    # Convert isodate.Duration to timedelta with approximations
    total_days = 0
    if hasattr(parsed, "years"):
        total_days += parsed.years * 365
    if hasattr(parsed, "months"):
        total_days += parsed.months * 30
    if hasattr(parsed, "tdelta"):
        return parsed.tdelta + timedelta(days=total_days)

    # Fallback: try to extract days and seconds
    try:
        total_days += parsed.days
        return timedelta(days=total_days, seconds=parsed.seconds,
                         microseconds=parsed.microseconds)
    except AttributeError:
        return timedelta(days=total_days)


def parse_xbrl_period(xml_elem: etree._Element) -> Period:
    """Parse an XBRL ``<xbrli:period>`` element.

    Handles instant, duration (startDate/endDate), and forever periods.

    Args:
        xml_elem: The ``<xbrli:period>`` lxml element.

    Returns:
        A ``Period`` model object.

    Raises:
        ParseError: If the period element is malformed.
    """
    # Check for instant period
    instant_elem = xml_elem.find(f"{{{NS_XBRLI}}}instant")
    if instant_elem is not None:
        text = (instant_elem.text or "").strip()
        if not text:
            raise ParseError(
                message="Empty <xbrli:instant> element",
                code="PARSE-0050",
            )
        return Period(
            period_type=PeriodType.INSTANT,
            instant=parse_xml_date(text),
        )

    # Check for duration period
    start_elem = xml_elem.find(f"{{{NS_XBRLI}}}startDate")
    end_elem = xml_elem.find(f"{{{NS_XBRLI}}}endDate")
    if start_elem is not None and end_elem is not None:
        start_text = (start_elem.text or "").strip()
        end_text = (end_elem.text or "").strip()
        if not start_text:
            raise ParseError(
                message="Empty <xbrli:startDate> element",
                code="PARSE-0051",
            )
        if not end_text:
            raise ParseError(
                message="Empty <xbrli:endDate> element",
                code="PARSE-0052",
            )
        start_date = parse_xml_date(start_text)
        end_date = parse_xml_date(end_text)
        if end_date < start_date:
            raise ParseError(
                message=f"Period endDate {end_date} is before startDate {start_date}",
                code="PARSE-0053",
            )
        return Period(
            period_type=PeriodType.DURATION,
            start_date=start_date,
            end_date=end_date,
        )

    # Check for forever period
    forever_elem = xml_elem.find(f"{{{NS_XBRLI}}}forever")
    if forever_elem is not None:
        return Period(period_type=PeriodType.FOREVER)

    # Malformed period
    raise ParseError(
        message="Period element has no instant, startDate/endDate, or forever child",
        code="PARSE-0054",
    )


def period_contains(period: Period, instant: date) -> bool:
    """Test whether a period contains the given instant date.

    For an instant period, it contains the date if they are equal.
    For a duration period, it contains the date if
    ``startDate <= instant < endDate`` (start-inclusive, end-exclusive
    per XBRL date semantics where endDate is actually exclusive).
    For a forever period, it contains any date.

    Args:
        period: The period to test.
        instant: The instant date to check.

    Returns:
        True if the period contains the instant.
    """
    if period.period_type == PeriodType.FOREVER:
        return True

    if period.period_type == PeriodType.INSTANT:
        return period.instant == instant

    if period.period_type == PeriodType.DURATION:
        if period.start_date is None or period.end_date is None:
            return False
        return period.start_date <= instant < period.end_date

    return False


def periods_equal(a: Period, b: Period) -> bool:
    """Test whether two periods are equal per XBRL spec.

    Delegates to the Period.equals() method.

    Args:
        a: First period.
        b: Second period.

    Returns:
        True if the periods are structurally equal.
    """
    return a.equals(b)
