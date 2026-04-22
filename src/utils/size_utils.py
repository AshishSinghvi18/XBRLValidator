"""File-size formatting and parsing utilities.

Provides human-readable formatting of byte counts and parsing of
human-written size strings (e.g. ``"100MB"``, ``"2.5 GiB"``).
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Final

# IEC binary units (powers of 1024)
_IEC_UNITS: Final[list[tuple[str, int]]] = [
    ("EiB", 1 << 60),
    ("PiB", 1 << 50),
    ("TiB", 1 << 40),
    ("GiB", 1 << 30),
    ("MiB", 1 << 20),
    ("KiB", 1 << 10),
]

# SI decimal units (powers of 1000)
_SI_UNITS: Final[list[tuple[str, int]]] = [
    ("EB", 10**18),
    ("PB", 10**15),
    ("TB", 10**12),
    ("GB", 10**9),
    ("MB", 10**6),
    ("KB", 10**3),
]

_SIZE_RE = re.compile(
    r"^\s*([0-9]+(?:\.[0-9]+)?)\s*"
    r"(EiB|PiB|TiB|GiB|MiB|KiB|EB|PB|TB|GB|MB|KB|B|bytes?)?\s*$",
    re.IGNORECASE,
)

_UNIT_MAP: Final[dict[str, int]] = {
    "eib": 1 << 60,
    "pib": 1 << 50,
    "tib": 1 << 40,
    "gib": 1 << 30,
    "mib": 1 << 20,
    "kib": 1 << 10,
    "eb": 10**18,
    "pb": 10**15,
    "tb": 10**12,
    "gb": 10**9,
    "mb": 10**6,
    "kb": 10**3,
    "b": 1,
    "byte": 1,
    "bytes": 1,
}


def format_bytes(size_bytes: int, *, binary: bool = True) -> str:
    """Format a byte count as a human-readable string.

    Args:
        size_bytes: Non-negative byte count.
        binary:     If ``True`` (default), use IEC binary units (KiB, MiB, …).
                    If ``False``, use SI decimal units (KB, MB, …).

    Returns:
        Formatted string, e.g. ``"1.50 GiB"`` or ``"256 B"``.

    Examples:
        >>> format_bytes(1536)
        '1.50 KiB'
        >>> format_bytes(1500, binary=False)
        '1.50 KB'
        >>> format_bytes(42)
        '42 B'
    """
    if size_bytes < 0:
        return f"-{format_bytes(-size_bytes, binary=binary)}"

    units = _IEC_UNITS if binary else _SI_UNITS
    for unit_name, unit_size in units:
        if size_bytes >= unit_size:
            value = Decimal(size_bytes) / Decimal(unit_size)
            formatted = f"{value:.2f}".rstrip("0").rstrip(".")
            return f"{formatted} {unit_name}"
    return f"{size_bytes} B"


def parse_size(text: str) -> int:
    """Parse a human-readable size string into bytes.

    Accepts formats like ``"100MB"``, ``"2.5 GiB"``, ``"1024"``,
    ``"512 bytes"``.

    Args:
        text: Human-readable size string.

    Returns:
        Size in bytes (rounded to nearest integer).

    Raises:
        ValueError: If *text* cannot be parsed.

    Examples:
        >>> parse_size("100 MB")
        100000000
        >>> parse_size("1 GiB")
        1073741824
        >>> parse_size("1024")
        1024
    """
    match = _SIZE_RE.match(text)
    if not match:
        raise ValueError(f"Cannot parse size string: {text!r}")

    number = Decimal(match.group(1))
    unit_str = match.group(2)
    if unit_str is None:
        # No unit specified – assume bytes
        return int(number)

    unit_key = unit_str.lower()
    if unit_key not in _UNIT_MAP:
        raise ValueError(f"Unknown size unit: {unit_str!r}")

    return int(number * _UNIT_MAP[unit_key])


def check_file_size(
    size_bytes: int,
    limit_bytes: int,
    *,
    label: str = "file",
) -> None:
    """Check that a file size is within the allowed limit.

    Args:
        size_bytes:  Actual file size.
        limit_bytes: Maximum allowed size.
        label:       Human-readable label for error messages.

    Raises:
        ValueError: If *size_bytes* exceeds *limit_bytes*.
    """
    if size_bytes > limit_bytes:
        raise ValueError(
            f"{label} size {format_bytes(size_bytes)} exceeds limit "
            f"of {format_bytes(limit_bytes)}"
        )
