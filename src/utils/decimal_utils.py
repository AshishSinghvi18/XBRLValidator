"""Decimal utilities — Rule 1: Decimal, NEVER float.

Provides a project-wide Decimal context (precision 40), safe
conversion helpers, and string-formatting functions.
"""

from __future__ import annotations

import decimal
from decimal import Decimal, InvalidOperation

# ---------------------------------------------------------------------------
# Project-wide Decimal context — precision 40, ROUND_HALF_EVEN (banker's)
# ---------------------------------------------------------------------------

XBRL_DECIMAL_CONTEXT: decimal.Context = decimal.Context(
    prec=40,
    rounding=decimal.ROUND_HALF_EVEN,
    Emin=-999999,
    Emax=999999,
    traps=[
        decimal.InvalidOperation,
        decimal.DivisionByZero,
        decimal.Overflow,
    ],
)


def ensure_decimal(value: str | int | Decimal | None) -> Decimal:
    """Convert *value* to :class:`~decimal.Decimal` safely.

    Accepts ``str``, ``int``, or an existing ``Decimal``.
    ``float`` is **intentionally not accepted** (Rule 1).

    Args:
        value: The value to convert.  ``None`` is treated as zero.

    Returns:
        A ``Decimal`` created within :data:`XBRL_DECIMAL_CONTEXT`.

    Raises:
        TypeError: If *value* is a ``float`` or other unsupported type.
        decimal.InvalidOperation: If the string cannot be parsed.
    """
    if value is None:
        return Decimal(0)
    if isinstance(value, float):
        raise TypeError(
            f"float values are forbidden (Rule 1). Got {value!r}. "
            "Convert to str first."
        )
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (str, int)):
        return XBRL_DECIMAL_CONTEXT.create_decimal(value)
    raise TypeError(f"Cannot convert {type(value).__name__} to Decimal")


def decimal_to_str(value: Decimal) -> str:
    """Format a ``Decimal`` as a string without scientific notation.

    Trailing zeros beyond the significant digits are preserved to
    reflect the reported precision in an XBRL fact.

    Args:
        value: Decimal value to format.

    Returns:
        Plain decimal string (e.g. ``"1234.5600"``).
    """
    # normalize removes trailing zeros; we use to_eng_string for
    # readability but fall back to format for very large exponents.
    if value.is_zero():
        return "0"
    # Use 'f' format specifier to avoid scientific notation.
    return format(value, "f")


def safe_add(a: Decimal, b: Decimal) -> Decimal:
    """Add two decimals within the XBRL context."""
    return XBRL_DECIMAL_CONTEXT.add(a, b)


def safe_subtract(a: Decimal, b: Decimal) -> Decimal:
    """Subtract *b* from *a* within the XBRL context."""
    return XBRL_DECIMAL_CONTEXT.subtract(a, b)


def safe_multiply(a: Decimal, b: Decimal) -> Decimal:
    """Multiply within the XBRL context."""
    return XBRL_DECIMAL_CONTEXT.multiply(a, b)


def safe_divide(a: Decimal, b: Decimal) -> Decimal:
    """Divide within the XBRL context.

    Raises:
        decimal.DivisionByZero: If *b* is zero.
    """
    return XBRL_DECIMAL_CONTEXT.divide(a, b)


def round_decimal(value: Decimal, decimals: int) -> Decimal:
    """Round *value* to *decimals* decimal places using ROUND_HALF_EVEN.

    If *decimals* is negative, rounds to the left of the decimal point
    (e.g. ``decimals=-3`` rounds to the nearest thousand).

    Args:
        value: Decimal value.
        decimals: Number of decimal places (may be negative).

    Returns:
        Rounded ``Decimal``.
    """
    quantize_exp = Decimal(10) ** (-decimals)
    return value.quantize(quantize_exp, rounding=decimal.ROUND_HALF_EVEN)


def is_decimal_zero(value: Decimal) -> bool:
    """Return ``True`` if *value* is numerically zero."""
    return value.is_zero()


def parse_decimal_or_none(text: str) -> Decimal | None:
    """Try to parse *text* as a Decimal; return ``None`` on failure."""
    try:
        return XBRL_DECIMAL_CONTEXT.create_decimal(text.strip())
    except (InvalidOperation, ValueError):
        return None
