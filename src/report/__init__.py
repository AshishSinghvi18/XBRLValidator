"""XBRL Validator report formatting package.

Re-exports:
    ReportFormatter: Multi-format validation report formatter.
"""

from __future__ import annotations

from src.report.formatter import ReportFormatter

__all__: list[str] = [
    "ReportFormatter",
]
