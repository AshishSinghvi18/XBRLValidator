"""Decimal helper functions for XBRL numeric processing.

All XBRL monetary/numeric fact values are represented as ``decimal.Decimal``.
This module provides safe comparison, rounding, and tolerance-computation
utilities.

References:
    - XBRL 2.1 §5.2.5.2 (calculation linkbase consistency)
    - XBRL Calculations 1.1 §4 (rounding rules)
    - IEEE 754 / Python decimal module
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Final

# Sentinel for "infinity" decimals attribute
INF_DECIMALS: Final[str] = "INF"


def safe_decimal(value: str | int | float | Decimal) -> Decimal:
    """Convert a value to ``Decimal`` safely.

    For ``float`` inputs a string-based conversion is used to avoid
    binary floating-point representation artefacts.

    Args:
        value: Numeric value in any common representation.

    Returns:
        Exact ``Decimal`` representation.

    Raises:
        ValueError: If *value* cannot be converted.

    Examples:
        >>> safe_decimal("123.45")
        Decimal('123.45')
        >>> safe_decimal(42)
        Decimal('42')
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"Cannot convert {value!r} to Decimal")
        return Decimal(str(value))
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Cannot convert {value!r} to Decimal: {exc}") from exc


def safe_compare(a: Decimal, b: Decimal, tolerance: Decimal) -> bool:
    """Compare two Decimal values within an absolute tolerance.

    Args:
        a:         First value.
        b:         Second value.
        tolerance: Maximum allowed absolute difference (must be >= 0).

    Returns:
        ``True`` if ``|a - b| <= tolerance``.

    Examples:
        >>> safe_compare(Decimal("10.00"), Decimal("10.01"), Decimal("0.02"))
        True
        >>> safe_compare(Decimal("10.00"), Decimal("10.05"), Decimal("0.02"))
        False
    """
    return abs(a - b) <= tolerance


def round_decimal(value: Decimal, decimals: int) -> Decimal:
    """Round a Decimal to the given number of decimal places.

    Uses ``ROUND_HALF_UP`` as specified by XBRL 2.1 §5.2.5.2 for
    calculation-linkbase consistency checks.

    Args:
        value:    The value to round.
        decimals: Number of decimal places.  Negative values round to
                  powers of ten (e.g. ``-3`` rounds to thousands).

    Returns:
        Rounded ``Decimal`` value.

    Examples:
        >>> round_decimal(Decimal("123.456"), 2)
        Decimal('123.46')
        >>> round_decimal(Decimal("1550"), -2)
        Decimal('1600')
    """
    quantizer = Decimal(10) ** -decimals
    return value.quantize(quantizer, rounding=ROUND_HALF_UP)


def infer_decimals(value: Decimal) -> int:
    """Infer the number of significant decimal places from a value.

    This implements the inference rule described in XBRL 2.1 §4.6.6
    for facts that declare ``precision`` instead of ``decimals``.

    Args:
        value: A ``Decimal`` value.

    Returns:
        Number of decimal places (negative for values rounded to
        powers of ten).

    Examples:
        >>> infer_decimals(Decimal("123.45"))
        2
        >>> infer_decimals(Decimal("1200"))
        -2
    """
    sign, digits, exponent = value.as_tuple()
    if isinstance(exponent, str):
        # Special values (Inf, NaN)
        return 0
    return -exponent


def precision_to_decimals(value: Decimal, precision: int) -> int:
    """Convert XBRL ``precision`` attribute to ``decimals``.

    Per XBRL 2.1 §4.6.6::

        decimals = precision - floor(log10(|value|)) - 1

    Args:
        value:     The reported numeric value (must be non-zero).
        precision: The ``precision`` attribute (positive integer).

    Returns:
        Equivalent ``decimals`` value.

    Raises:
        ValueError: If *value* is zero (precision→decimals is undefined for
                    zero per the spec) or *precision* is not positive.

    Examples:
        >>> precision_to_decimals(Decimal("1234.5"), 4)
        1
    """
    if value == 0:
        raise ValueError(
            "Cannot convert precision to decimals for a zero value "
            "(XBRL 2.1 §4.6.6)"
        )
    if precision <= 0:
        raise ValueError(f"precision must be positive, got {precision}")
    magnitude = int(abs(value).log10())
    return precision - magnitude - 1


def decimals_to_precision(value: Decimal, decimals: int) -> int:
    """Convert XBRL ``decimals`` attribute to ``precision``.

    Per XBRL 2.1 §4.6.6::

        precision = decimals + floor(log10(|value|)) + 1

    Args:
        value:    The reported numeric value (must be non-zero).
        decimals: The ``decimals`` attribute.

    Returns:
        Equivalent ``precision`` value (clamped to minimum of 0).

    Raises:
        ValueError: If *value* is zero.

    Examples:
        >>> decimals_to_precision(Decimal("1234.5"), 1)
        4
    """
    if value == 0:
        raise ValueError(
            "Cannot convert decimals to precision for a zero value "
            "(XBRL 2.1 §4.6.6)"
        )
    magnitude = int(abs(value).log10())
    result = decimals + magnitude + 1
    return max(result, 0)


def compute_tolerance(decimals: int) -> Decimal:
    """Compute the rounding tolerance for a given ``decimals`` value.

    Per XBRL 2.1 §5.2.5.2 the tolerance for calculation consistency is::

        tolerance = 0.5 × 10^(-decimals)

    Args:
        decimals: The ``decimals`` attribute of the parent (summation) fact.

    Returns:
        Tolerance as a ``Decimal``.

    Examples:
        >>> compute_tolerance(2)
        Decimal('0.005')
        >>> compute_tolerance(0)
        Decimal('0.5')
        >>> compute_tolerance(-3)
        Decimal('500')
    """
    return Decimal("0.5") * Decimal(10) ** (-decimals)


def effective_value(value: Decimal, decimals_attr: str | int | None) -> Decimal:
    """Round a fact value to its effective value given the ``decimals`` attribute.

    If ``decimals`` is ``"INF"`` or ``None``, the value is returned unchanged.

    Args:
        value:         Raw numeric fact value.
        decimals_attr: The ``decimals`` attribute (``"INF"``, an integer, or
                       its string representation).

    Returns:
        The rounded effective value.

    Examples:
        >>> effective_value(Decimal("123.456"), "2")
        Decimal('123.46')
        >>> effective_value(Decimal("123.456"), "INF")
        Decimal('123.456')
    """
    if decimals_attr is None or str(decimals_attr) == INF_DECIMALS:
        return value
    dec = int(decimals_attr)
    return round_decimal(value, dec)
