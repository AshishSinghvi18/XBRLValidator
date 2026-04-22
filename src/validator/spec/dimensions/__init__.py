"""XBRL Dimensions 1.0 (XDT) validators.

Re-exports:
    :class:`DimensionValidator`
"""

from __future__ import annotations

from src.validator.spec.dimensions.dimension_validator import DimensionValidator

__all__: list[str] = ["DimensionValidator"]
