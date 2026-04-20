"""Error code catalog loader.

Loads and indexes the canonical error-code registry from
``config/error_codes.yaml`` so that validators and the self-check
pass can look up metadata for any code.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ErrorCodeEntry:
    """One row from the error-code YAML registry.

    Attributes:
        code: Machine-readable code (e.g. ``XBRL21-0001``).
        severity: Expected severity string (``error``, ``warning``, …).
        source: Subsystem that emits this code.
        spec: Specification reference.
        desc: Short human-readable description.
        fix: Suggested remediation text.
    """

    code: str
    severity: str
    source: str
    spec: str
    desc: str
    fix: str = ""


class ErrorCatalog:
    """Registry of all validation error codes loaded from ``config/error_codes.yaml``.

    Uses a simple singleton pattern so the YAML file is parsed at most once
    per process.
    """

    _instance: Optional["ErrorCatalog"] = None

    def __init__(self, config_path: str | None = None) -> None:
        self._entries: dict[str, ErrorCodeEntry] = {}
        if config_path is None:
            config_path = str(
                Path(__file__).parent.parent.parent / "config" / "error_codes.yaml"
            )
        self._load(config_path)

    @classmethod
    def get_instance(cls) -> "ErrorCatalog":
        """Return the singleton catalog, creating it on first call."""
        if cls._instance is None:
            cls._instance = ErrorCatalog()
        return cls._instance

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self, path: str) -> None:
        """Load error codes from YAML file.

        Each top-level key in the YAML document is an error code whose value
        is a mapping with ``severity``, ``source``, ``spec``, ``desc``, and
        optional ``fix`` fields.
        """
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                logger.warning("Error catalog at %s is not a mapping", path)
                return
            for code, meta in data.items():
                if not isinstance(meta, dict):
                    continue
                self._entries[str(code)] = ErrorCodeEntry(
                    code=str(code),
                    severity=meta.get("severity", "error"),
                    source=meta.get("source", ""),
                    spec=meta.get("spec", ""),
                    desc=meta.get("desc", ""),
                    fix=meta.get("fix", ""),
                )
            logger.debug("Loaded %d error codes from %s", len(self._entries), path)
        except FileNotFoundError:
            logger.warning("Error catalog file not found: %s", path)
        except yaml.YAMLError as exc:
            logger.error("Failed to parse error catalog %s: %s", path, exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, code: str) -> ErrorCodeEntry | None:
        """Return the entry for *code*, or ``None`` if unknown."""
        return self._entries.get(code)

    def get_fix(self, code: str) -> str:
        """Return the suggested fix for *code*, or empty string."""
        entry = self._entries.get(code)
        return entry.fix if entry else ""

    def get_description(self, code: str) -> str:
        """Return the human-readable description for *code*, or empty string."""
        entry = self._entries.get(code)
        return entry.desc if entry else ""

    def is_valid_code(self, code: str) -> bool:
        """Return ``True`` if *code* exists in the catalog."""
        return code in self._entries

    def all_codes(self) -> list[str]:
        """Return a sorted list of every known error code."""
        return sorted(self._entries.keys())
