"""Spec-level validators for XBRL, iXBRL, calculations, and dimensions.

Re-exports:
    :class:`InstanceValidator` — XBRL 2.1 §4
    :class:`CalculationValidator` — XBRL 2.1 §5.2.5.2
    :class:`DimensionValidator` — XBRL Dimensions 1.0
    :class:`IXBRLValidator` — Inline XBRL 1.1
"""

from __future__ import annotations

from src.validator.spec.calculation import CalculationValidator
from src.validator.spec.dimensions import DimensionValidator
from src.validator.spec.inline import IXBRLValidator
from src.validator.spec.xbrl21 import InstanceValidator

__all__: list[str] = [
    "CalculationValidator",
    "DimensionValidator",
    "IXBRLValidator",
    "InstanceValidator",
]
