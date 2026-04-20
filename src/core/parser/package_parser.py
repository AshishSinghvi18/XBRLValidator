"""Taxonomy package parser.

Parses XBRL taxonomy packages (ZIP archives with META-INF/taxonomyPackage.xml)
and report packages per the Taxonomy Packages 1.0 specification.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from lxml import etree

from src.core.constants import NS_XLINK
from src.core.exceptions import PackageParseError
from src.security.zip_guard import ZipGuard

logger = structlog.get_logger(__name__)

# Taxonomy Package namespace
NS_TP: str = "http://xbrl.org/2016/taxonomy-package"
NS_CATALOG: str = "urn:oasis:names:tc:entity:xmlns:xml:catalog"


@dataclass
class TaxonomyPackageInfo:
    """Metadata from a taxonomy package."""

    identifier: str = ""
    name: str = ""
    description: str = ""
    version: str = ""
    publisher: str = ""
    publisher_url: str = ""
    publisher_country: str = ""
    publication_date: str = ""
    entry_points: list[EntryPoint] = field(default_factory=list)
    redirects: dict[str, str] = field(default_factory=dict)
    source_path: str = ""
    superseded_packages: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)


@dataclass
class EntryPoint:
    """An entry point within a taxonomy package."""

    name: str = ""
    description: str = ""
    urls: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)


class PackageParser:
    """Parse XBRL taxonomy packages and report packages."""

    def __init__(self) -> None:
        self._log = logger.bind(component="package_parser")
        self._zip_guard = ZipGuard()

    def parse(self, file_path: str | Path) -> TaxonomyPackageInfo:
        """Parse a taxonomy package ZIP file.

        Args:
            file_path: Path to the ZIP archive.

        Returns:
            TaxonomyPackageInfo with metadata and entry points.

        Raises:
            PackageParseError: If the package is malformed.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        self._log.info("package_parse_start", path=str(path))

        # Validate ZIP safety
        validation = self._zip_guard.validate_zip(str(path))
        if not validation.is_safe:
            raise PackageParseError(
                message=f"Unsafe ZIP archive: {validation.reason}",
                code="PARSE-0080",
                file_path=str(path),
            )

        try:
            with zipfile.ZipFile(str(path), "r") as zf:
                return self._parse_zip(zf, str(path))
        except zipfile.BadZipFile as exc:
            raise PackageParseError(
                message=f"Invalid ZIP file: {exc}",
                code="PARSE-0081",
                file_path=str(path),
            ) from exc

    def _parse_zip(
        self, zf: zipfile.ZipFile, source_path: str
    ) -> TaxonomyPackageInfo:
        """Parse the contents of a taxonomy package ZIP."""
        info = TaxonomyPackageInfo(source_path=source_path)

        # Look for META-INF/taxonomyPackage.xml
        tp_path = "META-INF/taxonomyPackage.xml"
        if tp_path not in zf.namelist():
            # Try case-insensitive search
            for name in zf.namelist():
                if name.lower() == tp_path.lower():
                    tp_path = name
                    break
            else:
                self._log.warning("no_taxonomy_package_xml", path=source_path)
                return info

        try:
            tp_data = zf.read(tp_path)
            self._parse_taxonomy_package_xml(tp_data, info)
        except Exception as exc:
            raise PackageParseError(
                message=f"Failed to parse taxonomyPackage.xml: {exc}",
                code="PARSE-0082",
                file_path=source_path,
            ) from exc

        # Look for META-INF/catalog.xml for URL redirects
        catalog_path = "META-INF/catalog.xml"
        for name in zf.namelist():
            if name.lower() == catalog_path.lower():
                try:
                    cat_data = zf.read(name)
                    self._parse_catalog(cat_data, info)
                except Exception:
                    self._log.warning("catalog_parse_failed", path=source_path)
                break

        self._log.info(
            "package_parse_complete",
            entry_points=len(info.entry_points),
            redirects=len(info.redirects),
        )
        return info

    def _parse_taxonomy_package_xml(
        self, data: bytes, info: TaxonomyPackageInfo
    ) -> None:
        """Parse the taxonomyPackage.xml file."""
        root = etree.fromstring(data)

        # Package identity
        ident = root.find(f"{{{NS_TP}}}identifier")
        if ident is not None and ident.text:
            info.identifier = ident.text.strip()

        # Name (may be multi-language)
        for name_elem in root.iter(f"{{{NS_TP}}}name"):
            if name_elem.text:
                info.name = name_elem.text.strip()
                lang = name_elem.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                if lang and lang not in info.languages:
                    info.languages.append(lang)

        # Description
        desc = root.find(f"{{{NS_TP}}}description")
        if desc is not None and desc.text:
            info.description = desc.text.strip()

        # Version
        ver = root.find(f"{{{NS_TP}}}version")
        if ver is not None and ver.text:
            info.version = ver.text.strip()

        # Publisher
        pub = root.find(f"{{{NS_TP}}}publisher")
        if pub is not None:
            if pub.text:
                info.publisher = pub.text.strip()
            info.publisher_url = pub.get("url", "")
            info.publisher_country = pub.get("country", "")

        # Publication date
        pub_date = root.find(f"{{{NS_TP}}}publicationDate")
        if pub_date is not None and pub_date.text:
            info.publication_date = pub_date.text.strip()

        # Entry points
        ep_container = root.find(f"{{{NS_TP}}}entryPoints")
        if ep_container is not None:
            for ep_elem in ep_container.iter(f"{{{NS_TP}}}entryPoint"):
                ep = self._parse_entry_point(ep_elem)
                info.entry_points.append(ep)

        # Superseded packages
        for sp in root.iter(f"{{{NS_TP}}}supersededTaxonomyPackages"):
            for pkg in sp.iter(f"{{{NS_TP}}}taxonomyPackageRef"):
                href = pkg.text
                if href:
                    info.superseded_packages.append(href.strip())

    def _parse_entry_point(self, elem: etree._Element) -> EntryPoint:
        """Parse a single entry point element."""
        ep = EntryPoint()

        name = elem.find(f"{{{NS_TP}}}name")
        if name is not None and name.text:
            ep.name = name.text.strip()

        desc = elem.find(f"{{{NS_TP}}}description")
        if desc is not None and desc.text:
            ep.description = desc.text.strip()

        for doc in elem.iter(f"{{{NS_TP}}}entryPointDocument"):
            href = doc.get("href", "")
            if href:
                ep.urls.append(href)

        for lang in elem.iter(f"{{{NS_TP}}}language"):
            if lang.text:
                ep.languages.append(lang.text.strip())

        return ep

    def _parse_catalog(self, data: bytes, info: TaxonomyPackageInfo) -> None:
        """Parse the catalog.xml for URL remappings."""
        root = etree.fromstring(data)

        for rewrite in root.iter(f"{{{NS_CATALOG}}}rewriteURI"):
            prefix = rewrite.get("uriStartString", "")
            rewrite_prefix = rewrite.get("rewritePrefix", "")
            if prefix and rewrite_prefix:
                info.redirects[prefix] = rewrite_prefix

        for uri in root.iter(f"{{{NS_CATALOG}}}uri"):
            name_attr = uri.get("name", "")
            target = uri.get("uri", "")
            if name_attr and target:
                info.redirects[name_attr] = target
