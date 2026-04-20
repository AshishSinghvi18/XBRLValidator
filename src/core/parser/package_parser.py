"""Taxonomy package and report package parser.

Handles XBRL Taxonomy Packages (META-INF/taxonomyPackage.xml + catalog.xml)
and ESEF report packages.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from src.core.exceptions import PackageParseError
from src.security import XXEGuard, ZipGuard

NS_TP = "http://xbrl.org/2016/taxonomy-package"
NS_CATALOG = "urn:oasis:names:tc:entity:xmlns:xml:catalog"


@dataclass
class CatalogEntry:
    """A single rewrite entry from catalog.xml."""
    rewrite_from: str
    rewrite_to: str


@dataclass
class TaxonomyPackage:
    """Parsed taxonomy package."""
    zip_path: str
    name: str = ""
    description: str = ""
    version: str = ""
    publisher: str = ""
    publisher_url: str = ""
    publication_date: str = ""
    entry_points: list[dict[str, str]] = field(default_factory=list)
    catalog_entries: list[CatalogEntry] = field(default_factory=list)
    contained_files: list[str] = field(default_factory=list)
    superseded_packages: list[str] = field(default_factory=list)


@dataclass
class ReportPackage:
    """Parsed ESEF report package."""
    zip_path: str
    instance_documents: list[str] = field(default_factory=list)
    taxonomy_packages: list[str] = field(default_factory=list)
    contained_files: list[str] = field(default_factory=list)
    report_dir: str = ""


@dataclass
class FilingZip:
    """Generic filing ZIP (not a formal package)."""
    zip_path: str
    xbrl_files: list[str] = field(default_factory=list)
    schema_files: list[str] = field(default_factory=list)
    linkbase_files: list[str] = field(default_factory=list)
    inline_files: list[str] = field(default_factory=list)
    other_files: list[str] = field(default_factory=list)
    contained_files: list[str] = field(default_factory=list)


class PackageParser:
    """Parser for XBRL taxonomy packages, report packages, and filing ZIPs.

    Uses ZipGuard to validate archives before extraction.
    """

    def __init__(
        self,
        xxe_guard: XXEGuard | None = None,
        zip_guard: ZipGuard | None = None,
    ) -> None:
        self._xxe = xxe_guard or XXEGuard()
        self._zip_guard = zip_guard or ZipGuard()

    def parse_taxonomy_package(self, zip_path: str) -> TaxonomyPackage:
        """Parse an XBRL Taxonomy Package ZIP.

        Expects META-INF/taxonomyPackage.xml and optionally META-INF/catalog.xml.

        Args:
            zip_path: Path to the taxonomy package ZIP file.

        Returns:
            Parsed TaxonomyPackage.

        Raises:
            PackageParseError: On structural or I/O errors.
        """
        self._validate_zip(zip_path)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                contained = list(names)

                # Find taxonomyPackage.xml
                tp_path = self._find_entry(names, "META-INF/taxonomyPackage.xml")
                if tp_path is None:
                    raise PackageParseError(
                        code="PKG-0001",
                        message="Missing META-INF/taxonomyPackage.xml",
                        file_path=zip_path,
                    )

                tp_data = zf.read(tp_path)
                package = self._parse_taxonomy_package_xml(tp_data, zip_path)
                package.zip_path = zip_path
                package.contained_files = contained

                # Parse catalog.xml if present
                cat_path = self._find_entry(names, "META-INF/catalog.xml")
                if cat_path is not None:
                    cat_data = zf.read(cat_path)
                    package.catalog_entries = self._parse_catalog_xml(cat_data, zip_path)

                return package

        except PackageParseError:
            raise
        except zipfile.BadZipFile as exc:
            raise PackageParseError(
                code="PKG-0002",
                message=f"Invalid ZIP file: {exc}",
                file_path=zip_path,
            ) from exc
        except Exception as exc:
            raise PackageParseError(
                code="PKG-0003",
                message=f"Error reading taxonomy package: {exc}",
                file_path=zip_path,
            ) from exc

    def parse_report_package(self, zip_path: str) -> ReportPackage:
        """Parse an ESEF report package ZIP.

        Looks for instance documents and taxonomy references.

        Args:
            zip_path: Path to the report package ZIP.

        Returns:
            Parsed ReportPackage.

        Raises:
            PackageParseError: On structural or I/O errors.
        """
        self._validate_zip(zip_path)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                contained = list(names)

                # Find report directory (usually the top-level dir or "reports/")
                report_dir = ""
                for name in names:
                    parts = Path(name).parts
                    if len(parts) >= 1:
                        report_dir = parts[0]
                        break

                # Find instance documents
                instance_docs: list[str] = []
                taxonomy_pkgs: list[str] = []

                for name in names:
                    lower = name.lower()
                    if lower.endswith((".xhtml", ".html", ".htm")):
                        # Check for iXBRL content
                        try:
                            content = zf.read(name)
                            text_preview = content[:4096].lower()
                            if (b"ix:" in text_preview or
                                    b"inlinexbrl" in text_preview or
                                    b"http://www.xbrl.org/2013/inlinexbrl" in text_preview):
                                instance_docs.append(name)
                        except Exception:
                            pass
                    elif lower.endswith(".xbrl"):
                        instance_docs.append(name)
                    elif lower.endswith(".zip"):
                        taxonomy_pkgs.append(name)

                return ReportPackage(
                    zip_path=zip_path,
                    instance_documents=instance_docs,
                    taxonomy_packages=taxonomy_pkgs,
                    contained_files=contained,
                    report_dir=report_dir,
                )

        except PackageParseError:
            raise
        except zipfile.BadZipFile as exc:
            raise PackageParseError(
                code="PKG-0010",
                message=f"Invalid ZIP file: {exc}",
                file_path=zip_path,
            ) from exc
        except Exception as exc:
            raise PackageParseError(
                code="PKG-0011",
                message=f"Error reading report package: {exc}",
                file_path=zip_path,
            ) from exc

    def parse_filing_zip(self, zip_path: str) -> FilingZip:
        """Parse a generic filing ZIP (non-standard package).

        Categorises contained files by extension.

        Args:
            zip_path: Path to the ZIP archive.

        Returns:
            Parsed FilingZip with categorised files.

        Raises:
            PackageParseError: On I/O errors.
        """
        self._validate_zip(zip_path)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                result = FilingZip(zip_path=zip_path, contained_files=list(names))

                for name in names:
                    lower = name.lower()
                    if lower.endswith(".xbrl"):
                        result.xbrl_files.append(name)
                    elif lower.endswith(".xsd"):
                        result.schema_files.append(name)
                    elif lower.endswith((".xml",)) and self._looks_like_linkbase(
                        name, zf
                    ):
                        result.linkbase_files.append(name)
                    elif lower.endswith((".html", ".htm", ".xhtml")):
                        result.inline_files.append(name)
                    else:
                        result.other_files.append(name)

                return result

        except zipfile.BadZipFile as exc:
            raise PackageParseError(
                code="PKG-0020",
                message=f"Invalid ZIP file: {exc}",
                file_path=zip_path,
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_zip(self, zip_path: str) -> None:
        """Validate ZIP using ZipGuard."""
        if not os.path.isfile(zip_path):
            raise PackageParseError(
                code="PKG-0030",
                message=f"File not found: {zip_path}",
                file_path=zip_path,
            )
        result = self._zip_guard.check_zip(zip_path)
        if not result.safe:
            raise PackageParseError(
                code="PKG-0031",
                message=f"ZIP safety check failed: {'; '.join(result.violations)}",
                file_path=zip_path,
                context={"violations": result.violations},
            )

    @staticmethod
    def _find_entry(names: list[str], target: str) -> str | None:
        """Find a ZIP entry case-insensitively."""
        target_lower = target.lower()
        for name in names:
            if name.lower() == target_lower:
                return name
            # Also check without leading directory
            parts = Path(name).parts
            if len(parts) >= 2:
                relative = "/".join(parts[-2:])
                if relative.lower() == target_lower:
                    return name
        return None

    def _parse_taxonomy_package_xml(
        self, data: bytes, zip_path: str
    ) -> TaxonomyPackage:
        """Parse taxonomyPackage.xml content."""
        try:
            root = self._xxe.safe_fromstring(data)
        except Exception as exc:
            raise PackageParseError(
                code="PKG-0004",
                message=f"Invalid taxonomyPackage.xml: {exc}",
                file_path=zip_path,
            ) from exc

        pkg = TaxonomyPackage(zip_path=zip_path)

        # Extract metadata
        name_el = root.find(f"{{{NS_TP}}}name")
        if name_el is not None and name_el.text:
            pkg.name = name_el.text.strip()

        desc_el = root.find(f"{{{NS_TP}}}description")
        if desc_el is not None and desc_el.text:
            pkg.description = desc_el.text.strip()

        ver_el = root.find(f"{{{NS_TP}}}version")
        if ver_el is not None and ver_el.text:
            pkg.version = ver_el.text.strip()

        pub_el = root.find(f"{{{NS_TP}}}publisher")
        if pub_el is not None and pub_el.text:
            pkg.publisher = pub_el.text.strip()

        pub_url_el = root.find(f"{{{NS_TP}}}publisherURL")
        if pub_url_el is not None and pub_url_el.text:
            pkg.publisher_url = pub_url_el.text.strip()

        pub_date_el = root.find(f"{{{NS_TP}}}publicationDate")
        if pub_date_el is not None and pub_date_el.text:
            pkg.publication_date = pub_date_el.text.strip()

        # Entry points
        eps_el = root.find(f"{{{NS_TP}}}entryPoints")
        if eps_el is not None:
            for ep_el in eps_el.findall(f"{{{NS_TP}}}entryPoint"):
                ep: dict[str, str] = {}
                ep_name = ep_el.find(f"{{{NS_TP}}}name")
                if ep_name is not None and ep_name.text:
                    ep["name"] = ep_name.text.strip()
                ep_desc = ep_el.find(f"{{{NS_TP}}}description")
                if ep_desc is not None and ep_desc.text:
                    ep["description"] = ep_desc.text.strip()
                for doc_el in ep_el.findall(f"{{{NS_TP}}}entryPointDocument"):
                    href = doc_el.get("href", "")
                    if href:
                        ep["href"] = href
                if ep:
                    pkg.entry_points.append(ep)

        # Superseded packages
        sp_el = root.find(f"{{{NS_TP}}}supersededTaxonomyPackages")
        if sp_el is not None:
            for tp_ref in sp_el.findall(f"{{{NS_TP}}}taxonomyPackageRef"):
                href = tp_ref.get("href", "")
                if href:
                    pkg.superseded_packages.append(href)

        return pkg

    def _parse_catalog_xml(self, data: bytes, zip_path: str) -> list[CatalogEntry]:
        """Parse catalog.xml for URI rewrite rules."""
        try:
            root = self._xxe.safe_fromstring(data)
        except Exception as exc:
            raise PackageParseError(
                code="PKG-0005",
                message=f"Invalid catalog.xml: {exc}",
                file_path=zip_path,
            ) from exc

        entries: list[CatalogEntry] = []
        for rewrite in root.iter(f"{{{NS_CATALOG}}}rewriteURI"):
            uri_start = rewrite.get("uriStartString", "")
            rewrite_prefix = rewrite.get("rewritePrefix", "")
            if uri_start:
                entries.append(CatalogEntry(
                    rewrite_from=uri_start,
                    rewrite_to=rewrite_prefix,
                ))

        return entries

    @staticmethod
    def _looks_like_linkbase(name: str, zf: zipfile.ZipFile) -> bool:
        """Quick check if an XML file looks like a linkbase."""
        try:
            data = zf.read(name)
            preview = data[:2048].lower()
            return b"linkbase" in preview
        except Exception:
            return False
