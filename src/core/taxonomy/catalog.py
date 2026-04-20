"""OASIS XML Catalog 1.1 resolver for XBRL taxonomy URIs.

Maps public/system identifiers and URIs to local file paths.
Used to redirect taxonomy URLs to locally cached copies.

Spec reference: OASIS XML Catalogs 1.1
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from lxml import etree

from src.core.exceptions import TaxonomyResolutionError

logger = logging.getLogger(__name__)

# OASIS XML Catalog namespace
_NS_CATALOG = "urn:oasis:names:tc:entity:xmlns:xml:catalog"


class XMLCatalog:
    """OASIS XML Catalog 1.1 resolver.

    Maps public/system identifiers and URIs to local file paths.
    Used to redirect taxonomy URLs to locally cached copies.
    """

    def __init__(self, catalog_files: list[str] | None = None) -> None:
        self._uri_mappings: dict[str, str] = {}
        self._rewrite_mappings: list[tuple[str, str]] = []  # (prefix, rewrite_prefix)
        self._suffix_mappings: list[tuple[str, str]] = []  # (suffix, local_uri)
        if catalog_files:
            for f in catalog_files:
                self.load(f)

    def load(self, catalog_path: str) -> None:
        """Load catalog XML file.

        Parses ``<uri>``, ``<rewriteURI>``, and ``<uriSuffix>`` entries
        from an OASIS XML Catalog file.

        Args:
            catalog_path: Path to the catalog XML file.

        Raises:
            TaxonomyResolutionError: If the catalog file cannot be parsed.
        """
        try:
            parser = etree.XMLParser(
                resolve_entities=False,
                no_network=True,
                dtd_validation=False,
                load_dtd=False,
            )
            tree = etree.parse(catalog_path, parser)  # noqa: S320
            root = tree.getroot()
            catalog_dir = str(Path(catalog_path).parent)

            for elem in root.iter():
                tag = etree.QName(elem.tag).localname if isinstance(elem.tag, str) else None
                if tag is None:
                    continue

                if tag == "uri":
                    name = elem.get("name", "")
                    uri = elem.get("uri", "")
                    if name and uri:
                        resolved = self._resolve_local(uri, catalog_dir)
                        self._uri_mappings[name] = resolved
                        logger.debug("Catalog uri mapping: %s -> %s", name, resolved)

                elif tag == "rewriteURI":
                    prefix = elem.get("uriStartString", "")
                    rewrite = elem.get("rewritePrefix", "")
                    if prefix and rewrite:
                        resolved = self._resolve_local(rewrite, catalog_dir)
                        self._rewrite_mappings.append((prefix, resolved))
                        logger.debug(
                            "Catalog rewrite: %s -> %s", prefix, resolved
                        )

                elif tag == "uriSuffix":
                    suffix = elem.get("uriSuffix", "")
                    uri = elem.get("uri", "")
                    if suffix and uri:
                        resolved = self._resolve_local(uri, catalog_dir)
                        self._suffix_mappings.append((suffix, resolved))

            # Sort rewrite mappings longest-prefix-first for greedy matching
            self._rewrite_mappings.sort(key=lambda x: len(x[0]), reverse=True)
            logger.info(
                "Loaded catalog %s: %d uri, %d rewrite, %d suffix mappings",
                catalog_path,
                len(self._uri_mappings),
                len(self._rewrite_mappings),
                len(self._suffix_mappings),
            )

        except etree.XMLSyntaxError as exc:
            raise TaxonomyResolutionError(
                f"Failed to parse catalog file: {exc}", url=catalog_path
            ) from exc
        except OSError as exc:
            raise TaxonomyResolutionError(
                f"Cannot read catalog file: {exc}", url=catalog_path
            ) from exc

    def resolve(self, uri: str) -> str:
        """Resolve URI through catalog.

        Tries exact URI match first, then rewrite rules (longest-prefix),
        then suffix match.  Returns the original URI if no mapping found.

        Args:
            uri: The URI to resolve.

        Returns:
            The resolved local path or the original URI.
        """
        # 1. Exact URI match
        if uri in self._uri_mappings:
            resolved = self._uri_mappings[uri]
            logger.debug("Catalog exact match: %s -> %s", uri, resolved)
            return resolved

        # 2. Rewrite rules (already sorted longest-prefix-first)
        for prefix, rewrite_prefix in self._rewrite_mappings:
            if uri.startswith(prefix):
                resolved = rewrite_prefix + uri[len(prefix) :]
                logger.debug("Catalog rewrite match: %s -> %s", uri, resolved)
                return resolved

        # 3. Suffix match
        for suffix, local_uri in self._suffix_mappings:
            if uri.endswith(suffix):
                logger.debug("Catalog suffix match: %s -> %s", uri, local_uri)
                return local_uri

        return uri

    def add_mapping(self, uri: str, local_path: str) -> None:
        """Add a URI → local path mapping.

        Args:
            uri: The original URI.
            local_path: The local file path to map to.
        """
        self._uri_mappings[uri] = local_path

    def add_rewrite(self, prefix: str, rewrite_prefix: str) -> None:
        """Add a URI prefix rewrite rule.

        Args:
            prefix: The URI prefix to match.
            rewrite_prefix: The replacement prefix.
        """
        self._rewrite_mappings.append((prefix, rewrite_prefix))
        # Re-sort for greedy matching
        self._rewrite_mappings.sort(key=lambda x: len(x[0]), reverse=True)

    @property
    def mapping_count(self) -> int:
        """Total number of all mapping entries."""
        return (
            len(self._uri_mappings)
            + len(self._rewrite_mappings)
            + len(self._suffix_mappings)
        )

    @staticmethod
    def _resolve_local(uri: str, base_dir: str) -> str:
        """Resolve a possibly-relative URI against the catalog base directory.

        Args:
            uri: URI or relative path from the catalog.
            base_dir: Directory containing the catalog file.

        Returns:
            Absolute path if the URI is relative, otherwise the URI unchanged.
        """
        if uri.startswith(("http://", "https://", "file://")):
            return uri
        resolved = Path(base_dir) / uri
        return str(resolved.resolve())
