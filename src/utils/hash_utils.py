"""SHA-256 hashing utilities for taxonomy cache keys and content fingerprints.

Provides deterministic, reproducible hashing for use as cache keys,
content-addressable storage identifiers, and integrity checks.

References:
    - FIPS 180-4 (SHA-256)
    - Python hashlib documentation
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_hex(data: str | bytes) -> str:
    """Compute the SHA-256 hex digest of the given data.

    Args:
        data: Input data as string (UTF-8 encoded) or bytes.

    Returns:
        Lowercase hex-encoded SHA-256 digest (64 characters).

    Examples:
        >>> sha256_hex("hello")
        '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_bytes(data: str | bytes) -> bytes:
    """Compute the raw SHA-256 digest of the given data.

    Args:
        data: Input data as string (UTF-8 encoded) or bytes.

    Returns:
        Raw 32-byte SHA-256 digest.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).digest()


def sha256_file(path: str | Path, *, chunk_size: int = 65536) -> str:
    """Compute the SHA-256 hex digest of a file's contents.

    Reads the file in chunks to handle arbitrarily large files without
    loading the entire contents into memory.

    Args:
        path:       File path.
        chunk_size: Read buffer size in bytes (default 64 KB).

    Returns:
        Lowercase hex-encoded SHA-256 digest.

    Raises:
        FileNotFoundError: If *path* does not exist.
        OSError: If the file cannot be read.

    Examples:
        >>> import tempfile, os
        >>> # (example only – actual usage with real files)
    """
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def cache_key(*parts: str) -> str:
    """Build a deterministic cache key from multiple string components.

    Joins *parts* with a null separator and hashes the result.
    This ensures distinct inputs produce distinct keys even when
    individual parts contain common substrings.

    Args:
        *parts: String components to combine.

    Returns:
        64-character hex digest suitable for use as a cache key.

    Examples:
        >>> k1 = cache_key("http://example.com/tax.xsd", "2024-01-01")
        >>> k2 = cache_key("http://example.com/tax.xsd", "2024-01-02")
        >>> k1 != k2
        True
    """
    combined = "\x00".join(parts)
    return sha256_hex(combined)


def content_fingerprint(content: bytes) -> str:
    """Generate a content-addressable fingerprint for binary content.

    Useful for deduplicating taxonomy documents that may be fetched
    from different URLs but have identical content.

    Args:
        content: Raw document bytes.

    Returns:
        64-character hex digest.
    """
    return hashlib.sha256(content).hexdigest()
