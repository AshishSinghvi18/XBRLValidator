"""Regulator-specific validation modules.

Each sub-package implements validation rules for a specific regulatory body.
Currently implemented: EFM (SEC EDGAR Filing Manual).
"""

from __future__ import annotations

from src.validator.regulator import efm

__all__: list[str] = ["efm"]