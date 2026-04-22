"""iXBRL Transform Engine.

Applies inline XBRL transformations to human-readable display values,
producing canonical XBRL fact values with optional scale and sign
adjustments.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from src.core.parser.decimal_parser import apply_scale, parse_xbrl_decimal
from src.core.parser.transform_registry import TransformRegistry


@dataclass(frozen=True)
class TransformResult:
    """Immutable result of an iXBRL transformation."""

    xbrl_value: str
    """The transformed XBRL value string."""

    error_code: str | None
    """``None`` on success; an error code string when the transform failed."""

    original_display: str
    """The original display value before transformation."""


class IXBRLTransformEngine:
    """Engine that applies iXBRL transformations.

    Wraps a :class:`TransformRegistry` and adds numeric post-processing
    (scale and sign adjustments) on top of the raw transform functions.
    """

    def __init__(self, registry: TransformRegistry | None = None) -> None:
        self._registry = registry if registry is not None else TransformRegistry()

    # -- public API ---------------------------------------------------------

    def apply(
        self,
        format_qname: str,
        display_value: str,
        scale: int = 0,
        sign: str | None = None,
    ) -> TransformResult:
        """Apply an iXBRL transformation to *display_value*.

        Parameters
        ----------
        format_qname:
            Clark-notation QName (``{namespace}localName``) identifying the
            transform to apply.
        display_value:
            The human-readable value shown in the iXBRL document.
        scale:
            Power-of-ten scale factor (e.g. ``6`` for millions).  Applied
            only when the transformed result is numeric.
        sign:
            If ``"-"``, the numeric result is negated.

        Returns
        -------
        TransformResult
            The transformation outcome.
        """
        original_display = display_value

        transform_func = self._registry.get_transform(format_qname)
        if transform_func is None:
            return TransformResult(
                xbrl_value=display_value,
                error_code="ixbrl:unknownTransform",
                original_display=original_display,
            )

        try:
            xbrl_value = transform_func(display_value)
        except Exception:
            return TransformResult(
                xbrl_value=display_value,
                error_code="ixbrl:transformError",
                original_display=original_display,
            )

        xbrl_value = self._apply_numeric_adjustments(xbrl_value, scale, sign)

        return TransformResult(
            xbrl_value=xbrl_value,
            error_code=None,
            original_display=original_display,
        )

    def apply_batch(
        self,
        transforms: list[tuple[str, str, int, str | None]],
    ) -> list[TransformResult]:
        """Apply transforms to a batch of inputs.

        Parameters
        ----------
        transforms:
            Sequence of ``(format_qname, display_value, scale, sign)`` tuples.

        Returns
        -------
        list[TransformResult]
            One result per input, in the same order.
        """
        return [
            self.apply(fmt, val, sc, sgn) for fmt, val, sc, sgn in transforms
        ]

    def is_transform_available(self, format_qname: str) -> bool:
        """Return whether *format_qname* is registered in the underlying registry."""
        return self._registry.is_registered(format_qname)

    # -- private helpers ----------------------------------------------------

    def _apply_numeric_adjustments(
        self, value: str, scale: int, sign: str | None
    ) -> str:
        """Apply scale and sign adjustments when *value* is numeric.

        Non-numeric values are returned unchanged.
        """
        try:
            decimal_value = parse_xbrl_decimal(value)
        except (ValueError, InvalidOperation):
            return value

        if scale != 0:
            decimal_value = apply_scale(decimal_value, scale)

        if sign == "-":
            decimal_value = -decimal_value

        return str(decimal_value)
