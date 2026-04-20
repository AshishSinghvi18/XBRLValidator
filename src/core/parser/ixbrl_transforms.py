"""iXBRL transform engine — applies inline XBRL transformations.

The transform engine converts display values (as shown in the HTML
document) to canonical XBRL values using registered transformation
functions. It handles scale application and sign negation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import structlog

from src.core.constants import NS_IXT_PREFIX
from src.core.exceptions import IXBRLParseError
from src.core.parser.transform_registry import TransformRegistry, TransformResult
from src.utils.decimal_utils import XBRL_DECIMAL_CONTEXT

logger = structlog.get_logger(__name__)


class IXBRLTransformEngine:
    """Engine for applying iXBRL inline transformations.

    Coordinates the transform registry with scale/sign post-processing
    to produce the final canonical XBRL value.
    """

    def __init__(self, registry: TransformRegistry | None = None) -> None:
        self._registry = registry or TransformRegistry()
        self._log = logger.bind(component="ixbrl_transform_engine")

    @property
    def registry(self) -> TransformRegistry:
        """Access the underlying transform registry."""
        return self._registry

    def apply(
        self,
        format_qname: str,
        display_value: str,
        scale: int = 0,
        sign: str = "",
    ) -> TransformResult:
        """Apply a transformation to a display value.

        Args:
            format_qname: Clark-notation QName of the transform format
                (e.g., ``"{http://...}numcommadot"``).
            display_value: The value as displayed in the HTML document.
            scale: Power-of-10 scale factor (e.g., 6 for millions).
            sign: Sign override: ``"-"`` to negate the value.

        Returns:
            TransformResult with the canonical XBRL value.
        """
        # Parse the QName
        namespace, local_name = self._parse_format_qname(format_qname)

        # Apply the format transformation
        result = self._registry.apply(namespace, local_name, display_value)

        if not result.success:
            self._log.warning(
                "transform_failed",
                format=format_qname,
                value=display_value,
                error=result.error_message,
            )
            return result

        # Apply sign negation
        if sign == "-" and result.value:
            result = self._apply_sign(result)

        # Apply scale factor
        if scale != 0 and result.value:
            result = self._apply_scale(result, scale)

        return result

    def _parse_format_qname(self, format_qname: str) -> tuple[str, str]:
        """Parse a Clark-notation QName into (namespace, local_name)."""
        if format_qname.startswith("{"):
            closing = format_qname.index("}")
            namespace = format_qname[1:closing]
            local_name = format_qname[closing + 1:]
            return namespace, local_name
        # No namespace
        return "", format_qname

    def _apply_sign(self, result: TransformResult) -> TransformResult:
        """Apply sign negation to a transform result."""
        value = result.value.strip()
        if not value:
            return result

        # Check if the value is numeric
        try:
            dec = XBRL_DECIMAL_CONTEXT.create_decimal(value)
            negated = XBRL_DECIMAL_CONTEXT.minus(dec)
            return TransformResult(
                value=str(negated),
                success=True,
                source_format=result.source_format,
            )
        except (InvalidOperation, ValueError):
            # Non-numeric value — prepend minus sign
            if value.startswith("-"):
                return TransformResult(
                    value=value[1:],
                    success=True,
                    source_format=result.source_format,
                )
            return TransformResult(
                value=f"-{value}",
                success=True,
                source_format=result.source_format,
            )

    def _apply_scale(self, result: TransformResult, scale: int) -> TransformResult:
        """Apply scale factor (power of 10) to a numeric result."""
        value = result.value.strip()
        if not value:
            return result

        try:
            dec = XBRL_DECIMAL_CONTEXT.create_decimal(value)
            scaled = dec.scaleb(scale, context=XBRL_DECIMAL_CONTEXT)
            return TransformResult(
                value=str(scaled),
                success=True,
                source_format=result.source_format,
            )
        except (InvalidOperation, ValueError):
            # Non-numeric — cannot scale
            return TransformResult(
                value=value,
                success=False,
                error_message=f"Cannot apply scale {scale} to non-numeric value: {value!r}",
                source_format=result.source_format,
            )
