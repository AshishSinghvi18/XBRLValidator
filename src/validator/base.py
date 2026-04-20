"""Base validator class.

Every concrete validator inherits from :class:`BaseValidator` and implements
the :meth:`validate` method.  The base class provides convenience helpers
for emitting messages at each severity level and a logger bound to the
concrete subclass name.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from src.core.model.xbrl_model import ValidationMessage, XBRLInstance
from src.core.types import Severity


class BaseValidator(ABC):
    """Abstract base class for all validators.

    All validators inherit from this and implement :meth:`validate`.
    """

    def __init__(self, instance: XBRLInstance) -> None:
        self._instance: XBRLInstance = instance
        self._messages: list[ValidationMessage] = []
        self._logger: logging.Logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def validate(self) -> list[ValidationMessage]:
        """Run validation and return messages."""

    # ------------------------------------------------------------------
    # Message helpers
    # ------------------------------------------------------------------

    def error(self, code: str, message: str, **kwargs: Any) -> None:
        """Emit an error message."""
        self._messages.append(
            ValidationMessage(
                code=code,
                severity=Severity.ERROR,
                message=message,
                source_file=self._instance.file_path,
                **kwargs,
            )
        )

    def warning(self, code: str, message: str, **kwargs: Any) -> None:
        """Emit a warning message."""
        self._messages.append(
            ValidationMessage(
                code=code,
                severity=Severity.WARNING,
                message=message,
                source_file=self._instance.file_path,
                **kwargs,
            )
        )

    def info(self, code: str, message: str, **kwargs: Any) -> None:
        """Emit an info message."""
        self._messages.append(
            ValidationMessage(
                code=code,
                severity=Severity.INFO,
                message=message,
                source_file=self._instance.file_path,
                **kwargs,
            )
        )

    def inconsistency(self, code: str, message: str, **kwargs: Any) -> None:
        """Emit an inconsistency message."""
        self._messages.append(
            ValidationMessage(
                code=code,
                severity=Severity.INCONSISTENCY,
                message=message,
                source_file=self._instance.file_path,
                **kwargs,
            )
        )
