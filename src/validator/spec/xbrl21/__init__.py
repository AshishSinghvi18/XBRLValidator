"""XBRL 2.1 spec validators — §4 instance validation.

Re-exports:
    :class:`InstanceValidator`
"""

from __future__ import annotations

from src.validator.spec.xbrl21.instance_validator import InstanceValidator

__all__: list[str] = ["InstanceValidator"]
