"""Hashing utilities for content integrity and caching.

Provides SHA-256 based hashing for files, byte content, and taxonomy
cache key generation.
"""

from __future__ import annotations

import hashlib

_READ_CHUNK_SIZE = 65_536  # 64 KB


def file_sha256(file_path: str) -> str:
    """Compute the SHA-256 hex digest of a file.

    Reads the file in 64 KB chunks to keep memory usage constant
    regardless of file size.

    Args:
        file_path: Path to the file to hash.

    Returns:
        The lowercase hex-encoded SHA-256 digest.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        OSError: On I/O errors.
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as fh:
        while True:
            chunk = fh.read(_READ_CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def content_sha256(content: bytes) -> str:
    """Compute the SHA-256 hex digest of a byte string.

    Args:
        content: The bytes to hash.

    Returns:
        The lowercase hex-encoded SHA-256 digest.
    """
    return hashlib.sha256(content).hexdigest()


def taxonomy_cache_key(urls: list[str]) -> str:
    """Create a deterministic cache key from a list of taxonomy URLs.

    The URLs are sorted before hashing so that the same set of URLs
    always produces the same key, regardless of input order.

    Args:
        urls: List of taxonomy schema/linkbase URLs.

    Returns:
        The lowercase hex-encoded SHA-256 digest of the sorted,
        newline-joined URL list.
    """
    normalised = "\n".join(sorted(urls))
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()
