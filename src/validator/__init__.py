"""XBRL validator entry point.

Provides :class:`XBRLValidator`, the main orchestrator that coordinates
all spec-level validation passes in the correct order.
"""

from __future__ import annotations

from src.core.model.instance import ValidationMessage, XBRLInstance
from src.core.types import InputFormat, Severity


class XBRLValidator:
    """Main validation orchestrator.

    Coordinates all spec validators in the correct order:

    1. XBRL 2.1 instance structural validation (§4).
    2. Inline XBRL 1.1 validation (if input format is iXBRL).

    Calculation and dimension validation require additional network /
    taxonomy inputs and should be invoked separately via
    :class:`~src.validator.spec.CalculationValidator` and
    :class:`~src.validator.spec.DimensionValidator`.
    """

    def validate(
        self, instance: XBRLInstance
    ) -> list[ValidationMessage]:
        """Run all validation passes on an instance.

        Args:
            instance: The parsed XBRL instance document.

        Returns:
            Aggregated list of :class:`ValidationMessage` objects from
            all validation passes.
        """
        messages: list[ValidationMessage] = []

        # 1. Instance structural validation
        from src.validator.spec.xbrl21 import InstanceValidator

        messages.extend(InstanceValidator().validate(instance))

        # 2. iXBRL-specific validation (if applicable)
        if instance.input_format in (
            InputFormat.IXBRL_HTML,
            InputFormat.IXBRL_XHTML,
        ):
            from src.validator.spec.inline import IXBRLValidator

            messages.extend(IXBRLValidator().validate(instance))

        return messages
