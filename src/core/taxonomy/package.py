"""XBRL Taxonomy Package (ZIP) handler.

Implements loading and extraction of taxonomy packages as defined in the
*Taxonomy Packages 1.0* specification.

Each package contains:
- ``META-INF/taxonomyPackage.xml`` – package metadata
- ``META-INF/catalog.xml``        – URI-to-file mappings
- Taxonomy files (schemas + linkbases)
"""

from __future__ import annotations

import logging
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from src.core.exceptions import TaxonomyResolutionError

logger = logging.getLogger(__name__)

# Taxonomy Package namespace
_NS_TP = "http://xbrl.org/2016/taxonomy-package"
_NS_CATALOG = "urn:oasis:names:tc:entity:xmlns:xml:catalog"


@dataclass
class TaxonomyPackage:
    """Represents an XBRL Taxonomy Package (ZIP file).

    Spec: Taxonomy Packages 1.0

    Attributes:
        path: File-system path to the ZIP.
        name: Human-readable package name.
        version: Package version string.
        publisher: Name of the publisher/issuer.
        entry_points: List of entry-point schema URLs.
        uri_mappings: URI → internal ZIP path mappings from the catalog.
    """

    path: str
    name: str
    version: str
    publisher: str
    entry_points: list[str] = field(default_factory=list)
    uri_mappings: dict[str, str] = field(default_factory=dict)


class PackageLoader:
    """Load and extract XBRL taxonomy packages."""

    def load(self, zip_path: str) -> TaxonomyPackage:
        """Load taxonomy package from ZIP file.

        Parses ``META-INF/taxonomyPackage.xml`` for metadata and
        ``META-INF/catalog.xml`` for URI mappings.

        Args:
            zip_path: Path to the taxonomy package ZIP file.

        Returns:
            Populated :class:`TaxonomyPackage` instance.

        Raises:
            TaxonomyResolutionError: If the ZIP is invalid or required
                metadata files are missing.
        """
        if not Path(zip_path).is_file():
            raise TaxonomyResolutionError(
                f"Taxonomy package not found: {zip_path}", url=zip_path
            )

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                name, version, publisher, entry_points = self._parse_metadata(zf)
                uri_mappings = self._parse_catalog(zf)
        except zipfile.BadZipFile as exc:
            raise TaxonomyResolutionError(
                f"Invalid ZIP file: {exc}", url=zip_path
            ) from exc

        return TaxonomyPackage(
            path=zip_path,
            name=name,
            version=version,
            publisher=publisher,
            entry_points=entry_points,
            uri_mappings=uri_mappings,
        )

    def extract_to_cache(
        self, package: TaxonomyPackage, cache_dir: str
    ) -> dict[str, str]:
        """Extract package contents to cache directory.

        Args:
            package: The loaded taxonomy package.
            cache_dir: Target directory for extracted files.

        Returns:
            Mapping of URIs to local extracted paths.
        """
        dest = Path(cache_dir) / f"{package.name}_{package.version}"
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(package.path, "r") as zf:
                zf.extractall(dest)  # noqa: S202
        except (zipfile.BadZipFile, OSError) as exc:
            raise TaxonomyResolutionError(
                f"Failed to extract taxonomy package: {exc}", url=package.path
            ) from exc

        # Build URI → local path mapping
        result: dict[str, str] = {}
        for uri, internal_path in package.uri_mappings.items():
            local = dest / internal_path
            if local.exists():
                result[uri] = str(local.resolve())
            else:
                logger.warning(
                    "Catalog entry %s -> %s not found in package", uri, internal_path
                )
        logger.info(
            "Extracted package %s v%s: %d files mapped",
            package.name,
            package.version,
            len(result),
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_metadata(
        zf: zipfile.ZipFile,
    ) -> tuple[str, str, str, list[str]]:
        """Parse META-INF/taxonomyPackage.xml.

        Returns:
            Tuple of (name, version, publisher, entry_points).
        """
        meta_path = "META-INF/taxonomyPackage.xml"
        if meta_path not in zf.namelist():
            raise TaxonomyResolutionError(
                f"Missing {meta_path} in taxonomy package", url=meta_path
            )

        parser = etree.XMLParser(
            resolve_entities=False, no_network=True, dtd_validation=False
        )
        data = zf.read(meta_path)
        root = etree.fromstring(data, parser)  # noqa: S320

        ns = {"tp": _NS_TP}
        name_elem = root.find(".//tp:name", ns)
        version_elem = root.find(".//tp:version", ns)
        publisher_elem = root.find(".//tp:publisher", ns)

        name = name_elem.text.strip() if name_elem is not None and name_elem.text else ""
        version = (
            version_elem.text.strip()
            if version_elem is not None and version_elem.text
            else ""
        )
        publisher = (
            publisher_elem.text.strip()
            if publisher_elem is not None and publisher_elem.text
            else ""
        )

        entry_points: list[str] = []
        for ep in root.iterfind(".//tp:entryPoint/tp:entryPointDocument", ns):
            href = ep.get("href", "")
            if href:
                entry_points.append(href)

        return name, version, publisher, entry_points

    @staticmethod
    def _parse_catalog(zf: zipfile.ZipFile) -> dict[str, str]:
        """Parse META-INF/catalog.xml for URI mappings.

        Returns:
            Dict mapping URIs to internal ZIP paths.
        """
        catalog_path = "META-INF/catalog.xml"
        if catalog_path not in zf.namelist():
            logger.debug("No catalog.xml in taxonomy package")
            return {}

        parser = etree.XMLParser(
            resolve_entities=False, no_network=True, dtd_validation=False
        )
        data = zf.read(catalog_path)
        root = etree.fromstring(data, parser)  # noqa: S320

        mappings: dict[str, str] = {}
        for elem in root.iter():
            tag = etree.QName(elem.tag).localname if isinstance(elem.tag, str) else None
            if tag == "rewriteURI":
                start = elem.get("uriStartString", "")
                rewrite = elem.get("rewritePrefix", "")
                if start and rewrite:
                    mappings[start] = rewrite
            elif tag == "uri":
                name = elem.get("name", "")
                uri = elem.get("uri", "")
                if name and uri:
                    mappings[name] = uri

        return mappings
