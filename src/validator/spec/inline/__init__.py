"""Inline XBRL 1.1 validators.

Re-exports:
    :class:`IXBRLValidator`
"""

from __future__ import annotations

from src.validator.spec.inline.ixbrl_validator import IXBRLValidator

__all__: list[str] = ["IXBRLValidator"]
