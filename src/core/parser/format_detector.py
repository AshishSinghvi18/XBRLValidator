"""Automatic XBRL format detection, parser-strategy selection, and package
introspection.

Examines magic bytes, BOMs, XML root elements, namespace declarations,
JSON structure, and ZIP contents to classify input files into the correct
:class:`~src.core.types.InputFormat` and choose an optimal
:class:`~src.core.types.ParserStrategy`.

References:
    - XBRL 2.1 §3 (instance namespace)
    - Inline XBRL 1.1 §2 (iXBRL namespace)
    - Taxonomy Packages 1.0
    - ESEF Report Package (META-INF/reportPackage.xml)
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

from lxml import etree

from src.core.constants import NS_IX, NS_LINK, NS_OIM, NS_XBRLI, NS_XSD
from src.core.exceptions import UnsupportedFormatError
from src.core.types import InputFormat, ParserStrategy, StorageType
from src.security import XXEGuard, ZipGuard

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Magic-byte / BOM constants
# ---------------------------------------------------------------------------
_BOM_UTF8 = b"\xef\xbb\xbf"
_BOM_UTF16_LE = b"\xff\xfe"
_BOM_UTF16_BE = b"\xfe\xff"
_MAGIC_ZIP = b"PK"
_MAGIC_GZIP = b"\x1f\x8b"

_SNIFF_SIZE = 8192

# Well-known iXBRL namespace prefixes used in HTML/XHTML documents.
_IX_NS_PATTERN = re.compile(
    rb"""xmlns(?::\w+)?=["']http://www\.xbrl\.org/\d{4}/inlineXBRL["']""",
    re.IGNORECASE,
)

# HTML doctype (case-insensitive)
_HTML_DOCTYPE_PATTERN = re.compile(rb"<!DOCTYPE\s+html", re.IGNORECASE)
_HTML_TAG_PATTERN = re.compile(rb"<html[\s>]", re.IGNORECASE)

# JSON-LD / xBRL-JSON marker
_JSON_DOC_INFO_PATTERN = re.compile(rb'"documentInfo"')

# ---------------------------------------------------------------------------
# Taxonomy / Report Package well-known paths
# ---------------------------------------------------------------------------
_TAXONOMY_PACKAGE_META = "META-INF/taxonomyPackage.xml"
_CATALOG_META = "META-INF/catalog.xml"
_REPORT_PACKAGE_META = "META-INF/reportPackage.xml"

# File extensions recognised as XBRL instance documents inside packages.
_INSTANCE_EXTENSIONS = frozenset({".xbrl", ".xml", ".xhtml", ".htm", ".html", ".json"})


# ===========================================================================
# Result data-classes
# ===========================================================================


@dataclass
class DetectionResult:
    """Outcome of single-file format detection.

    Attributes:
        format:               Detected :class:`InputFormat`.
        strategy:             Recommended :class:`ParserStrategy`.
        encoding:             Detected or assumed character encoding.
        file_path:            Absolute path to the inspected file.
        file_size_bytes:      Size of the file on disk.
        is_compressed:        ``True`` when the file is gzip-compressed.
        mime_type:            Best-guess MIME type string.
        declared_namespaces:  Namespace URIs found in an XML root element.
        root_qname:           Clark-notation QName of the XML root element.
        entry_points:         Schema/linkbase entry-point references found.
        storage_type:         Detected underlying storage medium.
        detection_confidence: 0.0–1.0 confidence score for the detection.
    """

    format: InputFormat
    strategy: ParserStrategy
    encoding: str
    file_path: str
    file_size_bytes: int
    is_compressed: bool
    mime_type: str
    declared_namespaces: list[str] = field(default_factory=list)
    root_qname: str = ""
    entry_points: list[str] = field(default_factory=list)
    storage_type: StorageType = StorageType.UNKNOWN
    detection_confidence: float = 0.0


@dataclass
class PackageDetectionResult:
    """Outcome of ZIP package introspection.

    Attributes:
        package_format:     :class:`InputFormat` for the package type.
        catalog_path:       Path to ``META-INF/catalog.xml`` (if present).
        metadata_path:      Path to the package metadata XML.
        entry_points:       Schema entry points declared in the catalog.
        instance_documents: Instance-document paths found inside the ZIP.
        contained_files:    Every file path found inside the archive.
    """

    package_format: InputFormat
    catalog_path: str = ""
    metadata_path: str = ""
    entry_points: list[str] = field(default_factory=list)
    instance_documents: list[str] = field(default_factory=list)
    contained_files: list[str] = field(default_factory=list)


# ===========================================================================
# FormatDetector
# ===========================================================================


class FormatDetector:
    """Detect XBRL input format and recommend a parser strategy.

    Args:
        streaming_threshold: File size (bytes) above which
            :attr:`ParserStrategy.STREAMING` is selected instead of DOM.
            Defaults to 50 MiB.
    """

    def __init__(self, streaming_threshold: int = 50 * 1024 * 1024) -> None:
        self._streaming_threshold = streaming_threshold
        self._xxe_guard = XXEGuard()
        self._zip_guard = ZipGuard()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, file_path: str) -> DetectionResult:
        """Detect the format of *file_path*.

        Args:
            file_path: Path to the file to inspect.

        Returns:
            A :class:`DetectionResult` describing the file.

        Raises:
            FileNotFoundError: If *file_path* does not exist.
            UnsupportedFormatError: If the format cannot be determined.
        """
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        file_size = path.stat().st_size
        abs_path = str(path)

        # Read first bytes for sniffing
        head = self._read_head(path)

        # Detect encoding via BOM
        encoding = self._detect_encoding(head)

        # Check for gzip compression
        is_compressed = head[:2] == _MAGIC_GZIP
        if is_compressed:
            head = self._read_gzip_head(path)

        # Detect storage type
        storage_type = self._detect_storage_type(path)

        # Strategy: DOM vs STREAMING
        strategy = (
            ParserStrategy.STREAMING
            if file_size >= self._streaming_threshold
            else ParserStrategy.DOM
        )

        # --- Classification pipeline ---
        if head[:2] == _MAGIC_ZIP and not is_compressed:
            return self._classify_zip(
                abs_path, file_size, encoding, is_compressed, storage_type, strategy
            )

        if self._looks_like_json(head):
            return self._classify_json(
                abs_path, head, path, file_size, encoding, is_compressed,
                storage_type, strategy,
            )

        if self._looks_like_xml(head):
            return self._classify_xml(
                abs_path, head, path, file_size, encoding, is_compressed,
                storage_type, strategy,
            )

        if self._looks_like_csv(path):
            return self._classify_csv(
                abs_path, file_size, encoding, is_compressed, storage_type, strategy
            )

        # If we still have HTML-like content, try HTML classification
        if self._looks_like_html(head):
            return self._classify_html(
                abs_path, head, file_size, encoding, is_compressed,
                storage_type, strategy,
            )

        raise UnsupportedFormatError(
            path.suffix or "unknown",
            context={"file_path": abs_path},
        )

    def detect_batch(self, file_paths: list[str]) -> list[DetectionResult]:
        """Detect formats for multiple files.

        Args:
            file_paths: Iterable of file paths.

        Returns:
            List of :class:`DetectionResult` in the same order as input.
            Files that cannot be detected produce a result with
            :attr:`InputFormat.UNKNOWN`.
        """
        results: list[DetectionResult] = []
        for fp in file_paths:
            try:
                results.append(self.detect(fp))
            except (FileNotFoundError, UnsupportedFormatError) as exc:
                logger.warning("Detection failed for %s: %s", fp, exc)
                results.append(
                    DetectionResult(
                        format=InputFormat.UNKNOWN,
                        strategy=ParserStrategy.DOM,
                        encoding="utf-8",
                        file_path=fp,
                        file_size_bytes=0,
                        is_compressed=False,
                        mime_type="application/octet-stream",
                        detection_confidence=0.0,
                    )
                )
        return results

    def detect_package(self, zip_path: str) -> PackageDetectionResult:
        """Inspect a ZIP archive as a taxonomy or report package.

        Args:
            zip_path: Path to the ZIP file.

        Returns:
            A :class:`PackageDetectionResult`.

        Raises:
            FileNotFoundError: If *zip_path* does not exist.
            zipfile.BadZipFile: If the file is not a valid ZIP.
        """
        path = Path(zip_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        # Safety check
        check = self._zip_guard.check_zip(str(path))
        if not check.safe:
            logger.warning(
                "ZIP safety violations in %s: %s", zip_path, check.violations
            )

        contained_files: list[str] = []
        instance_documents: list[str] = []
        catalog_path = ""
        metadata_path = ""
        entry_points: list[str] = []
        package_format = InputFormat.UNKNOWN

        with zipfile.ZipFile(str(path), "r") as zf:
            names = zf.namelist()
            contained_files = list(names)

            # Normalise for case-insensitive lookup
            name_set_lower = {n.lower(): n for n in names}

            # Taxonomy package detection
            has_taxonomy_meta = _TAXONOMY_PACKAGE_META.lower() in name_set_lower
            has_report_meta = _REPORT_PACKAGE_META.lower() in name_set_lower
            has_reports_dir = any(
                n.lower().startswith("reports/") for n in names
            )

            if has_taxonomy_meta:
                package_format = InputFormat.TAXONOMY_PACKAGE
                metadata_path = name_set_lower.get(
                    _TAXONOMY_PACKAGE_META.lower(), _TAXONOMY_PACKAGE_META
                )
            elif has_report_meta or has_reports_dir:
                package_format = InputFormat.REPORT_PACKAGE
                if has_report_meta:
                    metadata_path = name_set_lower.get(
                        _REPORT_PACKAGE_META.lower(), _REPORT_PACKAGE_META
                    )

            # Catalog
            if _CATALOG_META.lower() in name_set_lower:
                actual_catalog = name_set_lower[_CATALOG_META.lower()]
                catalog_path = actual_catalog
                entry_points = self._parse_catalog_entries(zf, actual_catalog)

            # Instance documents
            for name in names:
                ext = os.path.splitext(name)[1].lower()
                if ext in _INSTANCE_EXTENSIONS and not name.startswith("META-INF/"):
                    instance_documents.append(name)

        return PackageDetectionResult(
            package_format=package_format,
            catalog_path=catalog_path,
            metadata_path=metadata_path,
            entry_points=entry_points,
            instance_documents=instance_documents,
            contained_files=contained_files,
        )

    # ------------------------------------------------------------------
    # Head / encoding helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_head(path: Path, size: int = _SNIFF_SIZE) -> bytes:
        """Read the first *size* bytes of a file."""
        with open(path, "rb") as fh:
            return fh.read(size)

    @staticmethod
    def _read_gzip_head(path: Path, size: int = _SNIFF_SIZE) -> bytes:
        """Decompress the first *size* bytes of a gzip file."""
        try:
            with gzip.open(path, "rb") as fh:
                return fh.read(size)
        except (gzip.BadGzipFile, OSError):
            return b""

    @staticmethod
    def _detect_encoding(head: bytes) -> str:
        """Infer character encoding from BOM or XML declaration."""
        if head[:3] == _BOM_UTF8:
            return "utf-8-sig"
        if head[:2] == _BOM_UTF16_LE:
            return "utf-16-le"
        if head[:2] == _BOM_UTF16_BE:
            return "utf-16-be"

        # Try XML declaration: <?xml ... encoding="..."?>
        match = re.search(
            rb"""encoding=["']([^"']+)["']""", head[:512], re.IGNORECASE
        )
        if match:
            return match.group(1).decode("ascii", errors="replace").lower()

        return "utf-8"

    # ------------------------------------------------------------------
    # Content-type heuristics
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_xml(head: bytes) -> bool:
        """Return ``True`` if *head* begins with XML markers."""
        stripped = head.lstrip()
        if stripped[:5] == b"<?xml":
            return True
        if stripped[:1] == b"<":
            # Could be an XML document without declaration
            return True
        return False

    @staticmethod
    def _looks_like_json(head: bytes) -> bool:
        """Return ``True`` if *head* starts with ``{`` or ``[`` (JSON)."""
        stripped = head.lstrip()
        return stripped[:1] in (b"{", b"[")

    @staticmethod
    def _looks_like_html(head: bytes) -> bool:
        """Return ``True`` if *head* appears to be HTML."""
        if _HTML_DOCTYPE_PATTERN.search(head):
            return True
        if _HTML_TAG_PATTERN.search(head):
            return True
        return False

    @staticmethod
    def _looks_like_csv(path: Path) -> bool:
        """Return ``True`` if the file extension is ``.csv``."""
        return path.suffix.lower() == ".csv"

    # ------------------------------------------------------------------
    # Classification helpers
    # ------------------------------------------------------------------

    def _classify_xml(
        self,
        abs_path: str,
        head: bytes,
        path: Path,
        file_size: int,
        encoding: str,
        is_compressed: bool,
        storage_type: StorageType,
        strategy: ParserStrategy,
    ) -> DetectionResult:
        """Classify an XML-based file by parsing its root element."""
        root_qname = ""
        declared_namespaces: list[str] = []
        entry_points: list[str] = []
        fmt = InputFormat.UNKNOWN
        mime_type = "application/xml"
        confidence = 0.3  # baseline: we know it is XML

        try:
            tree = self._xxe_guard.safe_parse(str(path))
            root = tree.getroot()
            root_qname = root.tag  # Clark notation: {ns}local
            declared_namespaces = list(
                {v for v in root.nsmap.values() if v}
            )

            # Collect schemaRef / linkbaseRef entry points
            entry_points = self._extract_entry_points(root)

            fmt, mime_type, confidence = self._classify_xml_root(
                root, root_qname, declared_namespaces, head
            )
        except etree.XMLSyntaxError:
            # If full parse fails, fall back to sniffing head bytes
            fmt, mime_type, confidence = self._classify_xml_head(head)
        except Exception:  # noqa: BLE001
            logger.debug("XML parse failed for %s; falling back to sniffing", abs_path)
            fmt, mime_type, confidence = self._classify_xml_head(head)

        # An XML file that looks like HTML with iXBRL namespaces
        if fmt == InputFormat.UNKNOWN and self._looks_like_html(head):
            if _IX_NS_PATTERN.search(head):
                fmt = InputFormat.IXBRL_HTML
                mime_type = "text/html"
                confidence = 0.7

        return DetectionResult(
            format=fmt,
            strategy=strategy,
            encoding=encoding,
            file_path=abs_path,
            file_size_bytes=file_size,
            is_compressed=is_compressed,
            mime_type=mime_type,
            declared_namespaces=declared_namespaces,
            root_qname=root_qname,
            entry_points=entry_points,
            storage_type=storage_type,
            detection_confidence=confidence,
        )

    def _classify_xml_root(
        self,
        root: etree._Element,
        root_qname: str,
        namespaces: list[str],
        head: bytes,
    ) -> tuple[InputFormat, str, float]:
        """Sub-classify based on the XML root element and namespaces."""
        # {NS_XBRLI}xbrl
        if root_qname == f"{{{NS_XBRLI}}}xbrl":
            return InputFormat.XBRL_XML, "application/xbrl+xml", 1.0

        # {NS_XSD}schema -> taxonomy schema
        if root_qname == f"{{{NS_XSD}}}schema":
            return InputFormat.TAXONOMY_SCHEMA, "application/xml", 0.95

        # {NS_LINK}linkbase -> standalone linkbase
        if root_qname == f"{{{NS_LINK}}}linkbase":
            return InputFormat.LINKBASE, "application/xml", 0.95

        # Inline XBRL: root is html/xhtml and contains ix namespace
        local = etree.QName(root_qname).localname.lower() if root_qname else ""
        ns = etree.QName(root_qname).namespace if root_qname else ""

        if local == "html":
            has_ix = NS_IX in namespaces or self._tree_has_ix_namespace(root)
            if has_ix:
                if ns == "http://www.w3.org/1999/xhtml":
                    return InputFormat.IXBRL_XHTML, "application/xhtml+xml", 0.95
                return InputFormat.IXBRL_HTML, "text/html", 0.85

        # Check if any descendant uses ix namespace (shallow scan)
        if NS_IX in namespaces:
            if ns == "http://www.w3.org/1999/xhtml" or local == "html":
                return InputFormat.IXBRL_XHTML, "application/xhtml+xml", 0.9
            return InputFormat.IXBRL_HTML, "text/html", 0.7

        return InputFormat.UNKNOWN, "application/xml", 0.3

    @staticmethod
    def _classify_xml_head(head: bytes) -> tuple[InputFormat, str, float]:
        """Fallback classification from raw XML head bytes."""
        # Check for namespace URIs in the raw bytes
        if NS_XBRLI.encode() in head:
            return InputFormat.XBRL_XML, "application/xbrl+xml", 0.6

        if NS_XSD.encode() in head:
            return InputFormat.TAXONOMY_SCHEMA, "application/xml", 0.5

        if NS_LINK.encode() in head:
            return InputFormat.LINKBASE, "application/xml", 0.5

        if _IX_NS_PATTERN.search(head):
            return InputFormat.IXBRL_XHTML, "application/xhtml+xml", 0.5

        return InputFormat.UNKNOWN, "application/xml", 0.2

    @staticmethod
    def _tree_has_ix_namespace(root: etree._Element) -> bool:
        """Check whether the iXBRL namespace appears anywhere in the tree.

        Performs a shallow scan (root + first-level children) to avoid
        traversing very large documents.
        """
        # Root nsmap
        if NS_IX in (root.nsmap or {}).values():
            return True
        # First-level children
        for child in root:
            if isinstance(child.tag, str) and NS_IX in (child.nsmap or {}).values():
                return True
            # Second-level (e.g. <body>)
            for grandchild in child:
                if isinstance(grandchild.tag, str) and NS_IX in (
                    grandchild.nsmap or {}
                ).values():
                    return True
        return False

    @staticmethod
    def _extract_entry_points(root: etree._Element) -> list[str]:
        """Extract schemaRef and linkbaseRef hrefs from an XBRL root."""
        points: list[str] = []
        ns_xlink = "http://www.w3.org/1999/xlink"
        for tag_local in ("schemaRef", "linkbaseRef"):
            for el in root.iter(f"{{{NS_LINK}}}{tag_local}"):
                href = el.get(f"{{{ns_xlink}}}href")
                if href:
                    points.append(href)
        return points

    def _classify_html(
        self,
        abs_path: str,
        head: bytes,
        file_size: int,
        encoding: str,
        is_compressed: bool,
        storage_type: StorageType,
        strategy: ParserStrategy,
    ) -> DetectionResult:
        """Classify an HTML file (possibly Inline XBRL)."""
        fmt = InputFormat.UNKNOWN
        mime_type = "text/html"
        confidence = 0.3

        if _IX_NS_PATTERN.search(head):
            fmt = InputFormat.IXBRL_HTML
            confidence = 0.8
        elif b"inlineXBRL" in head.lower():
            fmt = InputFormat.IXBRL_HTML
            confidence = 0.6

        return DetectionResult(
            format=fmt,
            strategy=strategy,
            encoding=encoding,
            file_path=abs_path,
            file_size_bytes=file_size,
            is_compressed=is_compressed,
            mime_type=mime_type,
            storage_type=storage_type,
            detection_confidence=confidence,
        )

    def _classify_json(
        self,
        abs_path: str,
        head: bytes,
        path: Path,
        file_size: int,
        encoding: str,
        is_compressed: bool,
        storage_type: StorageType,
        strategy: ParserStrategy,
    ) -> DetectionResult:
        """Classify a JSON file (possibly xBRL-JSON)."""
        fmt = InputFormat.UNKNOWN
        mime_type = "application/json"
        confidence = 0.3

        # Quick regex check on head bytes
        if _JSON_DOC_INFO_PATTERN.search(head):
            fmt = InputFormat.XBRL_JSON
            mime_type = "application/xbrl+json"
            confidence = 0.8

        # If the quick check didn't match, try full parse for smaller files
        if fmt == InputFormat.UNKNOWN and file_size < self._streaming_threshold:
            try:
                with open(path, "r", encoding=encoding, errors="replace") as fh:
                    data = json.load(fh)
                if isinstance(data, dict) and "documentInfo" in data:
                    fmt = InputFormat.XBRL_JSON
                    mime_type = "application/xbrl+json"
                    confidence = 1.0
                elif isinstance(data, dict) and (
                    "documentType" in data
                    or any(k.startswith("http") for k in data)
                ):
                    # OIM-style document
                    fmt = InputFormat.XBRL_JSON
                    mime_type = "application/xbrl+json"
                    confidence = 0.6
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                logger.debug("JSON parse failed for %s", abs_path)

        return DetectionResult(
            format=fmt,
            strategy=strategy,
            encoding=encoding,
            file_path=abs_path,
            file_size_bytes=file_size,
            is_compressed=is_compressed,
            mime_type=mime_type,
            storage_type=storage_type,
            detection_confidence=confidence,
        )

    def _classify_csv(
        self,
        abs_path: str,
        file_size: int,
        encoding: str,
        is_compressed: bool,
        storage_type: StorageType,
        strategy: ParserStrategy,
    ) -> DetectionResult:
        """Classify a CSV file (possibly xBRL-CSV).

        xBRL-CSV requires a companion ``*-metadata.json`` file in the same
        directory.
        """
        fmt = InputFormat.UNKNOWN
        mime_type = "text/csv"
        confidence = 0.2

        csv_path = Path(abs_path)
        stem = csv_path.stem
        parent = csv_path.parent

        # Look for a companion metadata JSON file
        metadata_candidates = [
            parent / f"{stem}-metadata.json",
            parent / "metadata.json",
            parent / f"{stem}.json",
        ]
        for candidate in metadata_candidates:
            if candidate.is_file():
                try:
                    with open(candidate, "r", encoding="utf-8") as fh:
                        meta = json.load(fh)
                    if isinstance(meta, dict) and (
                        "documentInfo" in meta
                        or "tables" in meta
                        or "documentType" in meta
                    ):
                        fmt = InputFormat.XBRL_CSV
                        mime_type = "text/csv"
                        confidence = 0.85
                        break
                except (json.JSONDecodeError, OSError):
                    continue

        return DetectionResult(
            format=fmt,
            strategy=strategy,
            encoding=encoding,
            file_path=abs_path,
            file_size_bytes=file_size,
            is_compressed=is_compressed,
            mime_type=mime_type,
            storage_type=storage_type,
            detection_confidence=confidence,
        )

    def _classify_zip(
        self,
        abs_path: str,
        file_size: int,
        encoding: str,
        is_compressed: bool,
        storage_type: StorageType,
        strategy: ParserStrategy,
    ) -> DetectionResult:
        """Classify a ZIP archive as a taxonomy or report package."""
        fmt = InputFormat.UNKNOWN
        mime_type = "application/zip"
        confidence = 0.3

        try:
            pkg = self.detect_package(abs_path)
            fmt = pkg.package_format
            if fmt == InputFormat.TAXONOMY_PACKAGE:
                mime_type = "application/zip"
                confidence = 0.95
            elif fmt == InputFormat.REPORT_PACKAGE:
                mime_type = "application/zip"
                confidence = 0.95
        except (zipfile.BadZipFile, OSError) as exc:
            logger.debug("ZIP inspection failed for %s: %s", abs_path, exc)

        return DetectionResult(
            format=fmt,
            strategy=strategy,
            encoding=encoding,
            file_path=abs_path,
            file_size_bytes=file_size,
            is_compressed=is_compressed,
            mime_type=mime_type,
            storage_type=storage_type,
            detection_confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Package helpers
    # ------------------------------------------------------------------

    def _parse_catalog_entries(
        self, zf: zipfile.ZipFile, catalog_name: str
    ) -> list[str]:
        """Parse ``catalog.xml`` inside a ZIP and return entry-point URIs."""
        entries: list[str] = []
        try:
            with zf.open(catalog_name) as cat_fh:
                data = cat_fh.read()
            root = self._xxe_guard.safe_fromstring(data)
            # Catalog entries use <uri> or <rewriteURI> elements
            for uri_el in root.iter():
                tag_local = etree.QName(uri_el.tag).localname if isinstance(
                    uri_el.tag, str
                ) else ""
                if tag_local in ("uri", "rewriteURI"):
                    name_attr = uri_el.get("name") or uri_el.get("uri") or ""
                    if name_attr:
                        entries.append(name_attr)
                    rewrite = uri_el.get("rewritePrefix") or ""
                    if rewrite and rewrite not in entries:
                        entries.append(rewrite)
        except Exception:  # noqa: BLE001
            logger.debug("Failed to parse catalog %s", catalog_name)
        return entries

    # ------------------------------------------------------------------
    # Storage-type detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_storage_type(path: Path) -> StorageType:
        """Best-effort detection of the underlying storage medium.

        Uses ``psutil`` when available; falls back to :attr:`StorageType.UNKNOWN`.
        """
        try:
            import psutil  # type: ignore[import-untyped]
        except ImportError:
            return StorageType.UNKNOWN

        try:
            resolved = str(path.resolve())
            partitions = psutil.disk_partitions(all=True)
            best_match = ""
            best_partition = None
            for part in partitions:
                mp = part.mountpoint
                if resolved.startswith(mp) and len(mp) > len(best_match):
                    best_match = mp
                    best_partition = part

            if best_partition is None:
                return StorageType.UNKNOWN

            # Network filesystems
            fstype = (best_partition.fstype or "").lower()
            opts = (best_partition.opts or "").lower()
            if fstype in ("nfs", "cifs", "smbfs", "nfs4", "fuse.sshfs"):
                return StorageType.NETWORK
            if "network" in opts:
                return StorageType.NETWORK

            # Try to identify SSD vs HDD via device name
            device = best_partition.device
            dev_basename = os.path.basename(device)
            # Strip partition numbers (e.g. sda1 -> sda)
            dev_name = re.sub(r"\d+$", "", dev_basename)
            rotational_path = f"/sys/block/{dev_name}/queue/rotational"
            if os.path.isfile(rotational_path):
                with open(rotational_path) as fh:
                    val = fh.read().strip()
                if val == "0":
                    return StorageType.SSD
                if val == "1":
                    return StorageType.HDD
        except Exception:  # noqa: BLE001
            pass

        return StorageType.UNKNOWN
