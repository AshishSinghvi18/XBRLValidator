"""Multi-level taxonomy cache for XBRL schema and linkbase files.

Implements a 3-level caching strategy:

- **L1 HOT**:  ``.tax_cache/_parsed/{hash}.msgpack``  (~200ms load)
- **L2 WARM**: ``.tax_cache/{name}/{ver}/*.xsd,xml``   (~15s parse)
- **L3 COLD**: HTTP fetch from CDN                      (~30-60s download)

Uses httpx for network fetching, msgpack for serialization, and
SHA-256 for cache key generation.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import msgpack

from src.core.constants import DEFAULT_TAXONOMY_FETCH_TIMEOUT_S
from src.core.exceptions import TaxonomyResolutionError

logger = logging.getLogger(__name__)


def _url_to_cache_key(url: str) -> str:
    """Derive a SHA-256 cache key from a URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _url_to_local_path(cache_dir: Path, url: str) -> Path:
    """Map a URL to a deterministic local path inside the cache directory.

    Preserves the URL path structure so cached files are human-browsable.
    """
    parsed = urlparse(url)
    host = parsed.hostname or "unknown"
    path = parsed.path.lstrip("/")
    return cache_dir / host / path


class TaxonomyCache:
    """3-level taxonomy cache.

    L1 HOT:  .tax_cache/_parsed/{hash}.msgpack  (~200ms load)
    L2 WARM: .tax_cache/{name}/{ver}/*.xsd,xml   (~15s parse)
    L3 COLD: HTTP fetch from CDN                  (~30-60s download)

    Parameters
    ----------
    cache_dir:
        Root directory for cached files.
    fetch_timeout:
        HTTP timeout in seconds for L3 fetches.
    """

    def __init__(
        self,
        cache_dir: str = ".tax_cache",
        fetch_timeout: int = DEFAULT_TAXONOMY_FETCH_TIMEOUT_S,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._parsed_dir = self._cache_dir / "_parsed"
        self._fetch_timeout = fetch_timeout
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._parsed_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # L2 / L3: raw content
    # ------------------------------------------------------------------

    def get_or_fetch(self, url: str) -> bytes:
        """Get content from cache or fetch from network.

        Checks L2 (warm local files) first.  Falls back to L3 (HTTP)
        and stores the result in L2 on success.

        Args:
            url: Remote or local URL to retrieve.

        Returns:
            File content as bytes.

        Raises:
            TaxonomyResolutionError: If the URL cannot be fetched.
        """
        # Try L2 cache first
        local = _url_to_local_path(self._cache_dir, url)
        if local.is_file():
            logger.debug("Cache L2 hit: %s", url)
            return local.read_bytes()

        # Local file path (not a URL)
        if not url.startswith(("http://", "https://")):
            path = Path(url)
            if path.is_file():
                return path.read_bytes()
            raise TaxonomyResolutionError(
                f"Local taxonomy file not found: {url}", url=url
            )

        # L3 cold fetch
        logger.info("Cache L3 fetch: %s", url)
        try:
            with httpx.Client(
                timeout=self._fetch_timeout,
                follow_redirects=True,
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                content = resp.content
        except httpx.HTTPError as exc:
            raise TaxonomyResolutionError(
                f"Failed to fetch taxonomy: {exc}", url=url
            ) from exc

        # Store in L2
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(content)
        logger.debug("Cache L2 stored: %s -> %s", url, local)
        return content

    # ------------------------------------------------------------------
    # L1: parsed object cache (msgpack)
    # ------------------------------------------------------------------

    def get_parsed(self, cache_key: str) -> Any | None:
        """Get parsed object from L1 cache (msgpack).

        Args:
            cache_key: Unique key identifying the parsed artefact.

        Returns:
            De-serialized object or ``None`` if not cached.
        """
        path = self._parsed_dir / f"{cache_key}.msgpack"
        if not path.is_file():
            return None
        try:
            data = path.read_bytes()
            obj = msgpack.unpackb(data, raw=False)
            logger.debug("Cache L1 hit: %s", cache_key)
            return obj
        except (msgpack.UnpackException, ValueError, OSError) as exc:
            logger.warning("L1 cache read failed for %s: %s", cache_key, exc)
            return None

    def store_parsed(self, cache_key: str, obj: Any) -> None:
        """Store parsed object in L1 cache.

        Args:
            cache_key: Unique key identifying the parsed artefact.
            obj: Object to serialize (must be msgpack-compatible).
        """
        path = self._parsed_dir / f"{cache_key}.msgpack"
        try:
            data = msgpack.packb(obj, use_bin_type=True)
            path.write_bytes(data)
            logger.debug("Cache L1 stored: %s (%d bytes)", cache_key, len(data))
        except (TypeError, ValueError, OSError) as exc:
            logger.warning("L1 cache write failed for %s: %s", cache_key, exc)

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def get_local_path(self, url: str) -> Path | None:
        """Get local path for cached URL.

        Args:
            url: The URL to look up.

        Returns:
            Local file path if cached, else ``None``.
        """
        local = _url_to_local_path(self._cache_dir, url)
        return local if local.is_file() else None

    def is_cached(self, url: str) -> bool:
        """Check if URL is in the L2 cache.

        Args:
            url: The URL to check.

        Returns:
            ``True`` if the URL content is locally cached.
        """
        local = _url_to_local_path(self._cache_dir, url)
        return local.is_file()

    def clear(self) -> None:
        """Clear all caches (L1 and L2)."""
        if self._cache_dir.exists():
            shutil.rmtree(self._cache_dir)
            logger.info("Cleared taxonomy cache: %s", self._cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._parsed_dir.mkdir(parents=True, exist_ok=True)

    def cache_key_for_url(self, url: str) -> str:
        """Return the SHA-256 cache key for a URL.

        Args:
            url: The URL to hash.

        Returns:
            Hex-encoded SHA-256 digest.
        """
        return _url_to_cache_key(url)
