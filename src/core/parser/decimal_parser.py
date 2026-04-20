"""XBRL numeric parsing utilities.

All numeric operations use :class:`decimal.Decimal` exclusively to guarantee
the exactness required by XBRL validation rules (Rule 1 and Rule 16).
``float`` is **never** used.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# Pre-compiled pattern for XML Schema double values with scientific notation.
_DOUBLE_RE = re.compile(
    r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$"
)


def parse_xbrl_decimal(text: str, collapse_whitespace: bool = True) -> Decimal:
    """Parse an XBRL decimal lexical value into a :class:`Decimal`.

    Parameters
    ----------
    text:
        Raw lexical representation (e.g. ``" +1.23 "``).
    collapse_whitespace:
        When *True* (default), interior runs of whitespace are collapsed so
        that values such as ``"1 234.56"`` are normalised before parsing.

    Returns
    -------
    Decimal
        The parsed value.

    Raises
    ------
    ValueError
        If *text* is empty after stripping or is not a valid decimal.
    """
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty string is not a valid XBRL decimal")

    if collapse_whitespace:
        stripped = re.sub(r"\s+", "", stripped)

    try:
        return Decimal(stripped)
    except InvalidOperation as exc:
        raise ValueError(
            f"Invalid XBRL decimal value: {text!r}"
        ) from exc


def parse_xbrl_double(text: str) -> Decimal:
    """Parse an XML Schema ``double`` lexical value into a :class:`Decimal`.

    Handles scientific notation (``"1.23E+4"``, ``"1.23e-4"``) and the
    special values ``"INF"``, ``"-INF"`` and ``"NaN"`` defined by XML Schema.

    The mantissa and exponent are parsed separately using :class:`Decimal`
    arithmetic so that ``float`` is never involved.

    Parameters
    ----------
    text:
        Raw lexical representation.

    Returns
    -------
    Decimal
        The parsed value.  Special values map to ``Decimal('Infinity')``,
        ``Decimal('-Infinity')`` and ``Decimal('NaN')``.

    Raises
    ------
    ValueError
        If *text* is not a valid XML Schema double.
    """
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty string is not a valid XML Schema double")

    # Handle special values defined by XML Schema.
    upper = stripped.upper()
    if upper == "INF" or stripped == "+INF":
        return Decimal("Infinity")
    if upper == "-INF":
        return Decimal("-Infinity")
    if upper == "NAN":
        return Decimal("NaN")

    if not _DOUBLE_RE.match(stripped):
        raise ValueError(
            f"Invalid XML Schema double value: {text!r}"
        )

    # Split on 'e'/'E' and compute using Decimal arithmetic.
    parts = re.split(r"[eE]", stripped, maxsplit=1)
    mantissa = Decimal(parts[0])
    if len(parts) == 2:
        exponent = int(parts[1])
        return mantissa * Decimal(10) ** exponent
    return mantissa


def parse_scale(text: str) -> int:
    """Parse the iXBRL ``scale`` attribute value.

    Parameters
    ----------
    text:
        Raw attribute value (e.g. ``"6"`` or ``"-3"``).

    Returns
    -------
    int
        The scale factor.

    Raises
    ------
    ValueError
        If *text* is not a valid integer.
    """
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty string is not a valid scale value")
    try:
        return int(stripped)
    except (ValueError, ArithmeticError) as exc:
        raise ValueError(
            f"Invalid scale value: {text!r}"
        ) from exc


def parse_decimals(text: str) -> int | str:
    """Parse the XBRL ``decimals`` attribute.

    Parameters
    ----------
    text:
        Raw attribute value.  ``"INF"`` is the only accepted non-integer
        value.

    Returns
    -------
    int | str
        The integer number of decimals, or the string ``"INF"``.

    Raises
    ------
    ValueError
        If *text* is not ``"INF"`` and not a valid integer.
    """
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty string is not a valid decimals value")
    if stripped == "INF":
        return "INF"
    try:
        return int(stripped)
    except (ValueError, ArithmeticError) as exc:
        raise ValueError(
            f"Invalid decimals value: {text!r}"
        ) from exc


def parse_precision(text: str) -> int | str:
    """Parse the XBRL ``precision`` attribute.

    Parameters
    ----------
    text:
        Raw attribute value.  ``"INF"`` is the only accepted non-integer
        value.

    Returns
    -------
    int | str
        The integer precision, or the string ``"INF"``.

    Raises
    ------
    ValueError
        If *text* is not ``"INF"``, not a valid integer, or is negative
        (the XBRL specification requires precision ≥ 0).
    """
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty string is not a valid precision value")
    if stripped == "INF":
        return "INF"
    try:
        result = int(stripped)
    except (ValueError, ArithmeticError) as exc:
        raise ValueError(
            f"Invalid precision value: {text!r}"
        ) from exc

    if result < 0:
        raise ValueError(
            f"Precision must be >= 0 per XBRL spec, got {result}"
        )
    return result


def apply_scale(value: Decimal, scale: int) -> Decimal:
    """Apply an iXBRL scale factor to *value*.

    Equivalent to ``value * 10**scale`` but implemented with
    :meth:`Decimal.scaleb` for exactness.

    Parameters
    ----------
    value:
        The base numeric value.
    scale:
        The power-of-ten scale factor (e.g. ``6`` for millions).

    Returns
    -------
    Decimal
        The scaled value.

    Examples
    --------
    >>> apply_scale(Decimal("1.5"), 6)
    Decimal('1500000.0')
    """
    return value.scaleb(scale)


def round_to_decimals(value: Decimal, decimals: int | str) -> Decimal:
    """Round *value* according to the XBRL ``decimals`` attribute.

    Parameters
    ----------
    value:
        The numeric value to round.
    decimals:
        Number of decimal places, or ``"INF"`` for infinite precision
        (no rounding).

    Returns
    -------
    Decimal
        The rounded value.

    Examples
    --------
    >>> round_to_decimals(Decimal("1.2345"), 2)
    Decimal('1.23')
    >>> round_to_decimals(Decimal("12345"), -3)
    Decimal('1.2E+4')
    """
    if decimals == "INF":
        return value

    decimals = int(decimals)

    if decimals >= 0:
        quant = Decimal(10) ** -decimals  # e.g. 0.01 for decimals=2
        return value.quantize(quant, rounding=ROUND_HALF_UP)

    # Negative decimals: round to the left of the decimal point.
    # e.g. decimals=-3 → round to nearest 1000.
    shift = Decimal(10) ** decimals  # e.g. 0.001 for decimals=-3
    shifted = value * shift  # move digits right
    rounded = shifted.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return rounded / shift  # move digits back
