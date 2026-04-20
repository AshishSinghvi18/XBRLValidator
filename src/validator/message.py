"""Validation message utilities.

Convenience factories for creating :class:`ValidationMessage` instances at
each severity level, plus a display formatter.
"""

from src.core.model.xbrl_model import ValidationMessage
from src.core.types import Severity


def error(code: str, message: str, **kwargs) -> ValidationMessage:
    """Create an error-level validation message."""
    return ValidationMessage(code=code, severity=Severity.ERROR, message=message, **kwargs)


def warning(code: str, message: str, **kwargs) -> ValidationMessage:
    """Create a warning-level validation message."""
    return ValidationMessage(code=code, severity=Severity.WARNING, message=message, **kwargs)


def info(code: str, message: str, **kwargs) -> ValidationMessage:
    """Create an info-level validation message."""
    return ValidationMessage(code=code, severity=Severity.INFO, message=message, **kwargs)


def inconsistency(code: str, message: str, **kwargs) -> ValidationMessage:
    """Create an inconsistency-level validation message."""
    return ValidationMessage(code=code, severity=Severity.INCONSISTENCY, message=message, **kwargs)


def format_message(msg: ValidationMessage) -> str:
    """Format a validation message for display.

    Args:
        msg: The validation message to format.

    Returns:
        Human-readable string representation.
    """
    loc = f" at line {msg.source_line}" if msg.source_line else ""
    file_info = f" in {msg.source_file}" if msg.source_file else ""
    return f"[{msg.severity.value}] {msg.code}: {msg.message}{loc}{file_info}"
