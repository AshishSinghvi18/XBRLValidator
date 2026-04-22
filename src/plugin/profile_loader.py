"""Dynamic regulatory profile loader — XBRL validator plugin system."""

from __future__ import annotations

from src.core.exceptions import ProfileNotFoundError


class RegulatorProfile:
    """Base class for regulatory validation profiles.

    Subclass this to create a profile for a specific regulator
    (EFM, ESEF, FERC, etc.). Each profile can contribute additional
    validators and YAML-based rule files.
    """

    profile_id: str = ""
    display_name: str = ""

    def get_validators(self) -> list[object]:
        """Return additional validators contributed by this profile.

        Returns:
            A list of validator objects that implement a ``validate()``
            method accepting an XBRLInstance.
        """
        return []

    def get_yaml_rules(self) -> list[str]:
        """Return paths to YAML rule files for this profile.

        Returns:
            A list of file paths pointing to YAML rule definitions.
        """
        return []


class ProfileLoader:
    """Dynamically loads regulatory profiles from the regulator package.

    Profiles are registered via :meth:`register` and loaded on demand
    via :meth:`load`.
    """

    _profiles: dict[str, type[RegulatorProfile]] = {}

    @classmethod
    def register(cls, profile_id: str, profile_class: type[RegulatorProfile]) -> None:
        """Register a regulatory profile class.

        Args:
            profile_id: Short identifier (e.g. ``"efm"``, ``"esef"``).
            profile_class: The :class:`RegulatorProfile` subclass.
        """
        cls._profiles[profile_id] = profile_class

    @classmethod
    def load(cls, profile_id: str) -> RegulatorProfile:
        """Load and instantiate a regulatory profile.

        If the profile is not already registered, attempts to discover
        it from the ``src.regulator`` package.

        Args:
            profile_id: Short identifier (e.g. ``"efm"``, ``"esef"``).

        Returns:
            An instantiated :class:`RegulatorProfile`.

        Raises:
            ProfileNotFoundError: If the profile cannot be found.
        """
        if profile_id not in cls._profiles:
            cls._try_discover(profile_id)

        profile_class = cls._profiles.get(profile_id)
        if profile_class is None:
            raise ProfileNotFoundError(profile_id)

        return profile_class()

    @classmethod
    def available_profiles(cls) -> list[str]:
        """Return a list of all registered profile IDs.

        Returns:
            Sorted list of profile identifier strings.
        """
        return sorted(cls._profiles.keys())

    @classmethod
    def _try_discover(cls, profile_id: str) -> None:
        """Attempt to auto-discover a profile from the regulator package.

        Tries to import ``src.regulator.<profile_id>`` and looks for
        a module-level ``PROFILE_CLASS`` attribute that points to a
        :class:`RegulatorProfile` subclass.
        """
        module_name = f"src.regulator.{profile_id}"
        try:
            import importlib

            module = importlib.import_module(module_name)
            profile_class = getattr(module, "PROFILE_CLASS", None)
            if profile_class is not None and isinstance(profile_class, type):
                if issubclass(profile_class, RegulatorProfile):
                    cls.register(profile_id, profile_class)
        except (ImportError, AttributeError):
            pass
