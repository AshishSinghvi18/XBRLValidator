"""EFM regulatory profile for plugin system.

Spec: EDGAR Filing Manual Chapter 6 — Interactive Data
Reference: https://www.sec.gov/info/edgar/edgarfm.htm
"""

from __future__ import annotations

from src.plugin.profile_loader import ProfileLoader, RegulatorProfile
from src.validator.regulator.efm.efm_validator import EFMValidator


class EFMProfile(RegulatorProfile):
    """SEC EDGAR Filing Manual validation profile.

    Spec: EDGAR Filing Manual Chapter 6 — Interactive Data
    """

    profile_id: str = "efm"
    display_name: str = "SEC EDGAR Filing Manual"

    def get_validators(self) -> list[object]:
        """Return the EFM validator instance.

        Returns:
            A single-element list containing an :class:`EFMValidator`.
        """
        return [EFMValidator()]

    def get_yaml_rules(self) -> list[str]:
        """Return paths to YAML rule files for the EFM profile.

        Returns:
            Empty list — EFM rules are implemented in Python.
        """
        return []


# Register profile with the plugin loader
ProfileLoader.register("efm", EFMProfile)

PROFILE_CLASS = EFMProfile
