"""File-size utilities — Rule 2: Streaming First.

Helpers for formatting, parsing, and classifying file sizes against
the configured thresholds.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from src.core.constants import (
    DEFAULT_HUGE_FILE_THRESHOLD_BYTES,
    DEFAULT_LARGE_FILE_THRESHOLD_BYTES,
)

_SIZE_UNITS: dict[str, int] = {
    "B": 1,
    "KB": 1024,
    "MB": 1024**2,
    "GB": 1024**3,
    "TB": 1024**4,
}

_UNIT_LIST: list[tuple[str, int]] = sorted(
    _SIZE_UNITS.items(), key=lambda x: x[1], reverse=True
)

_SIZE_RE: re.Pattern[str] = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(TB|GB|MB|KB|B)?\s*$", re.IGNORECASE
)


def format_bytes(size_bytes: int) -> str:
    """Format *size_bytes* into a human-readable string.

    Examples:
        >>> format_bytes(1536)
        '1.50 KB'
        >>> format_bytes(0)
        '0 B'
    """
    if size_bytes == 0:
        return "0 B"
    for unit, threshold in _UNIT_LIST:
        if abs(size_bytes) >= threshold:
            value = size_bytes / threshold
            # Use integer display when there is no fractional part.
            if value == int(value):
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
    return f"{size_bytes} B"


def parse_size(text: str) -> int:
    """Parse a human-readable size string into bytes.

    Accepts formats like ``"100MB"``, ``"1.5 GB"``, ``"4096"``.
    A bare number (no unit) is treated as bytes.

    Args:
        text: Size string.

    Returns:
        Size in bytes (integer).

    Raises:
        ValueError: If the string cannot be parsed.
    """
    m = _SIZE_RE.match(text)
    if not m:
        raise ValueError(f"Cannot parse size string: {text!r}")
    value = float(m.group(1))
    unit = (m.group(2) or "B").upper()
    multiplier = _SIZE_UNITS.get(unit)
    if multiplier is None:
        raise ValueError(f"Unknown size unit: {unit!r}")
    return int(value * multiplier)


def is_large_file(
    path: str | Path,
    *,
    threshold: int = DEFAULT_LARGE_FILE_THRESHOLD_BYTES,
) -> bool:
    """Return ``True`` if the file at *path* exceeds the large-file threshold.

    Spec: Rule 2 — files > 100 MB must use streaming.
    """
    return os.path.getsize(path) > threshold


def is_huge_file(
    path: str | Path,
    *,
    threshold: int = DEFAULT_HUGE_FILE_THRESHOLD_BYTES,
) -> bool:
    """Return ``True`` if the file at *path* exceeds the huge-file threshold.

    Spec: Rule 2 — files > 1 GB must use streaming + disk spill.
    """
    return os.path.getsize(path) > threshold


def file_size_bytes(path: str | Path) -> int:
    """Return the size of *path* in bytes.

    Raises:
        FileNotFoundError: If the path does not exist.
    """
    return os.path.getsize(path)
