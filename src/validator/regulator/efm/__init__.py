"""SEC EDGAR Filing Manual (EFM) regulator validation module.

Provides :class:`EFMValidator` for SEC filing rule checks and
:class:`EFMProfile` for plugin-system integration.

Reference: EDGAR Filing Manual Chapter 6 — Interactive Data
"""

from __future__ import annotations

from src.validator.regulator.efm.efm_profile import EFMProfile
from src.validator.regulator.efm.efm_validator import EFMValidator

__all__: list[str] = ["EFMProfile", "EFMValidator"]