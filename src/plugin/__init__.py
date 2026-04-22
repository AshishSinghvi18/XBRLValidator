"""XBRL Validator plugin system — profile loader and rule engine.

Re-exports:
    ProfileLoader: Dynamic regulatory profile loader.
    RegulatorProfile: Base class for regulatory validation profiles.
"""

from __future__ import annotations

from src.plugin.profile_loader import ProfileLoader, RegulatorProfile

__all__: list[str] = [
    "ProfileLoader",
    "RegulatorProfile",
]
