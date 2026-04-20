"""Numeric parsing for XBRL — Rule 16 compliance (Decimal, NEVER float).

Implements strict parsing for:
  - xs:decimal (no scientific notation, no thousands separators)
  - xs:double (scientific notation allowed, result still Decimal)
  - scale, decimals, precision attributes
  - Value rounding per XBRL 2.1 §4.6.6 (ROUND_HALF_UP)
"""

from __future__ import annotations

import decimal
import re
from decimal import Decimal, InvalidOperation
from typing import Literal, Union

from src.core.exceptions import ParseError
from src.utils.decimal_utils import XBRL_DECIMAL_CONTEXT

# xs:decimal: optional sign, digits, optional decimal point + digits
# NO scientific notation, NO thousands separators
_XS_DECIMAL_RE: re.Pattern[str] = re.compile(
    r"^[+-]?(\d+\.?\d*|\.\d+)$"
)

# xs:double: allows scientific notation
_XS_DOUBLE_RE: re.Pattern[str] = re.compile(
    r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$|^[+-]?INF$|^NaN$"
)

# Thousands separator detection (to reject)
_THOUSANDS_RE: re.Pattern[str] = re.compile(r"\d{1,3}(,\d{3})+")


def parse_xbrl_decimal(text: str) -> Decimal:
    """Parse an xs:decimal value strictly.

    No scientific notation allowed. No thousands separators. Result is
    always a ``Decimal``, never a float.

    Args:
        text: The raw text value from the XBRL document.

    Returns:
        A ``Decimal`` representing the parsed value.

    Raises:
        ParseError: If the text is not a valid xs:decimal.
    """
    stripped = text.strip()
    if not stripped:
        raise ParseError(
            message="Empty string is not a valid xs:decimal",
            code="PARSE-0010",
        )

    # Reject thousands separators
    if _THOUSANDS_RE.search(stripped):
        raise ParseError(
            message=f"Thousands separators not allowed in xs:decimal: {stripped!r}",
            code="PARSE-0011",
        )

    # Reject scientific notation
    if "e" in stripped.lower():
        raise ParseError(
            message=f"Scientific notation not allowed in xs:decimal: {stripped!r}",
            code="PARSE-0012",
        )

    if not _XS_DECIMAL_RE.match(stripped):
        raise ParseError(
            message=f"Invalid xs:decimal value: {stripped!r}",
            code="PARSE-0013",
        )

    try:
        return XBRL_DECIMAL_CONTEXT.create_decimal(stripped)
    except (InvalidOperation, ValueError) as exc:
        raise ParseError(
            message=f"Cannot parse xs:decimal: {stripped!r}: {exc}",
            code="PARSE-0014",
        ) from exc


def parse_xbrl_double(text: str) -> Decimal:
    """Parse an xs:double value. Scientific notation is allowed.

    The result is always a ``Decimal`` (Rule 1: NEVER float).

    Args:
        text: The raw text value.

    Returns:
        A ``Decimal`` representing the parsed value.

    Raises:
        ParseError: If the text is not a valid xs:double.
    """
    stripped = text.strip()
    if not stripped:
        raise ParseError(
            message="Empty string is not a valid xs:double",
            code="PARSE-0020",
        )

    # Handle special values
    upper = stripped.upper().lstrip("+-")
    if upper == "INF":
        return Decimal("Infinity") if not stripped.startswith("-") else Decimal("-Infinity")
    if upper == "NAN":
        return Decimal("NaN")

    if not _XS_DOUBLE_RE.match(stripped):
        raise ParseError(
            message=f"Invalid xs:double value: {stripped!r}",
            code="PARSE-0021",
        )

    try:
        return XBRL_DECIMAL_CONTEXT.create_decimal(stripped)
    except (InvalidOperation, ValueError) as exc:
        raise ParseError(
            message=f"Cannot parse xs:double: {stripped!r}: {exc}",
            code="PARSE-0022",
        ) from exc


def parse_scale(text: str) -> int:
    """Parse an iXBRL ``scale`` attribute value.

    The scale is an integer that represents a power of 10 by which
    the displayed value should be multiplied to obtain the XBRL value.

    Args:
        text: The raw scale attribute value.

    Returns:
        Integer scale value.

    Raises:
        ParseError: If the text is not a valid integer.
    """
    stripped = text.strip()
    if not stripped:
        return 0
    try:
        return int(stripped)
    except ValueError as exc:
        raise ParseError(
            message=f"Invalid scale value: {stripped!r}",
            code="PARSE-0030",
        ) from exc


def parse_decimals(text: str) -> Union[int, Literal["INF"]]:
    """Parse the ``decimals`` attribute of an XBRL fact.

    Args:
        text: The raw decimals attribute value ("INF" or an integer).

    Returns:
        Integer number of decimal places, or the literal string ``"INF"``.

    Raises:
        ParseError: If the text is not valid.
    """
    stripped = text.strip()
    if stripped.upper() == "INF":
        return "INF"
    try:
        return int(stripped)
    except ValueError as exc:
        raise ParseError(
            message=f"Invalid decimals value: {stripped!r}",
            code="PARSE-0031",
        ) from exc


def parse_precision(text: str) -> Union[int, Literal["INF"]]:
    """Parse the ``precision`` attribute of an XBRL fact.

    Args:
        text: The raw precision attribute value ("INF" or an integer).

    Returns:
        Integer precision, or the literal string ``"INF"``.

    Raises:
        ParseError: If the text is not valid or precision is negative.
    """
    stripped = text.strip()
    if stripped.upper() == "INF":
        return "INF"
    try:
        val = int(stripped)
    except ValueError as exc:
        raise ParseError(
            message=f"Invalid precision value: {stripped!r}",
            code="PARSE-0032",
        ) from exc
    if val < 0:
        raise ParseError(
            message=f"Precision must be non-negative, got: {val}",
            code="PARSE-0033",
        )
    return val


def apply_scale(value: Decimal, scale: int) -> Decimal:
    """Apply a scale factor to a value using ``Decimal.scaleb``.

    The scale represents a power of 10:
    ``result = value * 10^scale``

    Args:
        value: The base ``Decimal`` value.
        scale: Integer power of 10.

    Returns:
        Scaled ``Decimal`` value.
    """
    if scale == 0:
        return value
    return value.scaleb(scale, context=XBRL_DECIMAL_CONTEXT)


def round_to_decimals(value: Decimal, decimals: int) -> Decimal:
    """Round a value to the specified number of decimal places using ROUND_HALF_UP.

    Per XBRL 2.1 §4.6.6, inference of decimals from precision and
    vice-versa uses ROUND_HALF_UP.

    Args:
        value: The ``Decimal`` value to round.
        decimals: Number of decimal places. Negative values round to
            the left of the decimal point (e.g., -3 rounds to thousands).

    Returns:
        Rounded ``Decimal`` value.
    """
    if value.is_zero():
        return Decimal("0")
    quantize_exp = Decimal(10) ** (-decimals)
    return value.quantize(quantize_exp, rounding=decimal.ROUND_HALF_UP)
