"""Calculation linkbase validators — XBRL 2.1 §5.2.5.2.

Re-exports:
    :class:`CalculationValidator`
"""

from __future__ import annotations

from src.validator.spec.calculation.calc_validator import CalculationValidator

__all__: list[str] = ["CalculationValidator"]
