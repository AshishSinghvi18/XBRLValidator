"""Cryptographic hash utilities.

SHA-256 is used for taxonomy cache keys, duplicate-document detection,
and integrity checks.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.core.constants import DEFAULT_IO_CHUNK_SIZE


def sha256_file(
    path: str | Path,
    *,
    chunk_size: int = DEFAULT_IO_CHUNK_SIZE,
) -> str:
    """Compute the SHA-256 hex digest of a file.

    Reads the file in chunks to avoid loading large files into memory.

    Args:
        path: Path to the file.
        chunk_size: Read buffer size in bytes.

    Returns:
        Lowercase hex digest string (64 characters).

    Raises:
        FileNotFoundError: If *path* does not exist.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute the SHA-256 hex digest of a byte string.

    Args:
        data: Raw bytes.

    Returns:
        Lowercase hex digest string.
    """
    return hashlib.sha256(data).hexdigest()


def sha256_string(text: str, *, encoding: str = "utf-8") -> str:
    """Compute the SHA-256 hex digest of a text string.

    Args:
        text: Unicode string.
        encoding: Encoding used to convert *text* to bytes.

    Returns:
        Lowercase hex digest string.
    """
    return hashlib.sha256(text.encode(encoding)).hexdigest()
