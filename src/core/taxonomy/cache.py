"""Taxonomy caching layer using diskcache.

Provides a thread-safe disk-backed cache for parsed taxonomy schemas
to avoid repeated parsing of the same taxonomy files.

References:
    - XBRL 2.1 §5 (Taxonomy Structure)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.core.exceptions import TaxonomyCacheError

if TYPE_CHECKING:
    from src.core.taxonomy.schema import TaxonomySchema

logger = logging.getLogger(__name__)

_CACHE_KEY_PREFIX = "taxonomy:schema:"


class TaxonomyCache:
    """Thread-safe taxonomy cache backed by diskcache.

    Stores parsed :class:`TaxonomySchema` instances to avoid repeated
    XML parsing of the same taxonomy documents.

    Args:
        cache_dir:    Directory path for the on-disk cache store.
        ttl_seconds:  Time-to-live for cache entries in seconds
                      (default: 86 400 = 24 hours).
    """

    def __init__(self, cache_dir: str, ttl_seconds: int = 86400) -> None:
        try:
            import diskcache  # noqa: WPS433 — lazy import
        except ImportError as exc:
            raise TaxonomyCacheError(
                message=(
                    "diskcache is required for taxonomy caching. "
                    "Install it with: pip install diskcache"
                ),
            ) from exc

        self._ttl = ttl_seconds
        try:
            self._cache: diskcache.Cache = diskcache.Cache(cache_dir)
        except Exception as exc:
            raise TaxonomyCacheError(
                message=f"Failed to open taxonomy cache at {cache_dir!r}: {exc}",
            ) from exc

    def _key(self, url: str) -> str:
        """Return the internal cache key for a taxonomy URL."""
        return f"{_CACHE_KEY_PREFIX}{url}"

    def get(self, url: str) -> TaxonomySchema | None:
        """Retrieve a cached taxonomy schema.

        Args:
            url: The resolved URL / path of the taxonomy schema.

        Returns:
            The cached :class:`TaxonomySchema`, or ``None`` on miss.
        """
        try:
            value = self._cache.get(self._key(url))
        except Exception:
            logger.debug("Cache read error for %s", url, exc_info=True)
            return None
        return value  # type: ignore[return-value]

    def put(self, url: str, schema: TaxonomySchema) -> None:
        """Store a taxonomy schema in the cache.

        Args:
            url:    The resolved URL / path used as cache key.
            schema: The parsed :class:`TaxonomySchema` to cache.
        """
        try:
            self._cache.set(self._key(url), schema, expire=self._ttl)
        except Exception:
            logger.debug("Cache write error for %s", url, exc_info=True)

    def invalidate(self, url: str) -> None:
        """Remove a specific schema from the cache.

        Args:
            url: The resolved URL / path to invalidate.
        """
        try:
            self._cache.delete(self._key(url))
        except Exception:
            logger.debug("Cache invalidation error for %s", url, exc_info=True)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        try:
            self._cache.clear()
        except Exception:
            logger.debug("Cache clear error", exc_info=True)

    def close(self) -> None:
        """Close the underlying diskcache store."""
        try:
            self._cache.close()
        except Exception:
            logger.debug("Cache close error", exc_info=True)
