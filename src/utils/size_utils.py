"""Size utility functions for file-size validation and formatting.

Provides human-readable size formatting, size-string parsing, and
file-size checks used by the validation pipeline.
"""

from __future__ import annotations

import os
import re

from src.core.exceptions import FileTooLargeError

_SIZE_UNITS: list[tuple[str, int]] = [
    ("TB", 1 << 40),
    ("GB", 1 << 30),
    ("MB", 1 << 20),
    ("KB", 1 << 10),
]

_PARSE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(TB|GB|MB|KB|B)?\s*$", re.IGNORECASE)


def format_bytes(size_bytes: int) -> str:
    """Format a byte count as a human-readable string.

    Uses binary units (1 KB = 1024 bytes).

    Args:
        size_bytes: Non-negative size in bytes.

    Returns:
        A human-readable string such as ``"1.5 GB"`` or ``"512 B"``.

    Examples:
        >>> format_bytes(1536)
        '1.5 KB'
        >>> format_bytes(0)
        '0 B'
    """
    if size_bytes < 0:
        raise ValueError("size_bytes must be non-negative")

    for suffix, threshold in _SIZE_UNITS:
        if size_bytes >= threshold:
            value = size_bytes / threshold
            # Avoid trailing zeros: use up to 2 decimal places
            formatted = f"{value:.2f}".rstrip("0").rstrip(".")
            return f"{formatted} {suffix}"
    return f"{size_bytes} B"


def parse_size(size_str: str) -> int:
    """Parse a human-readable size string into bytes.

    Accepts formats like ``"100MB"``, ``"1.5 GB"``, ``"1024"``, ``"512B"``.
    If no unit is specified the value is treated as bytes.

    Args:
        size_str: Size string to parse.

    Returns:
        The size in bytes as an integer.

    Raises:
        ValueError: If *size_str* is not a recognised format.

    Examples:
        >>> parse_size("100MB")
        104857600
        >>> parse_size("1024")
        1024
    """
    match = _PARSE_RE.match(size_str)
    if not match:
        raise ValueError(f"Cannot parse size string: {size_str!r}")

    value = match.group(1)
    unit = (match.group(2) or "B").upper()

    multipliers: dict[str, int] = {
        "B": 1,
        "KB": 1 << 10,
        "MB": 1 << 20,
        "GB": 1 << 30,
        "TB": 1 << 40,
    }

    return int(float(value) * multipliers[unit])


def check_file_size(file_path: str, max_bytes: int) -> None:
    """Raise :class:`FileTooLargeError` if a file exceeds *max_bytes*.

    Args:
        file_path: Path to the file to check.
        max_bytes: Maximum allowed size in bytes.

    Raises:
        FileTooLargeError: If the file size exceeds *max_bytes*.
        FileNotFoundError: If *file_path* does not exist.
    """
    size = get_file_size(file_path)
    if size > max_bytes:
        raise FileTooLargeError(
            f"File {file_path} exceeds maximum allowed size",
            file_size=size,
            max_size=max_bytes,
        )


def get_file_size(file_path: str) -> int:
    """Get the size of a file in bytes.

    Args:
        file_path: Path to the file.

    Returns:
        File size in bytes.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
    """
    return os.path.getsize(file_path)
