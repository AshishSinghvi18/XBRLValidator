"""Format detector — identifies XBRL document format and selects parsing strategy.

Implements a multi-stage detection algorithm:
1. File size check
2. Magic-number / header analysis (PK for ZIP, gzip header)
3. Content sniffing (XML, JSON, CSV, HTML)
4. Sub-classification (xbrl vs schema vs linkbase vs ixbrl)
5. Strategy selection (DOM vs STREAMING based on size thresholds)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from src.core.constants import (
    DEFAULT_LARGE_FILE_THRESHOLD_BYTES,
    NS_IX,
    NS_LINK,
    NS_XBRLI,
    NS_XSD,
)
from src.core.exceptions import UnsupportedFormatError
from src.core.types import InputFormat, ParserStrategy, QName

logger = structlog.get_logger(__name__)

# Size of the header read for sniffing (4 KB is sufficient for most cases)
_SNIFF_SIZE: int = 4096

# Magic bytes
_PK_MAGIC: bytes = b"PK\x03\x04"
_GZIP_MAGIC: bytes = b"\x1f\x8b"

# Regex patterns for content sniffing
_XML_DECL_RE: re.Pattern[bytes] = re.compile(rb"<\?xml\s", re.IGNORECASE)
_HTML_DOCTYPE_RE: re.Pattern[bytes] = re.compile(rb"<!DOCTYPE\s+html", re.IGNORECASE)
_HTML_TAG_RE: re.Pattern[bytes] = re.compile(rb"<html[\s>]", re.IGNORECASE)
_JSON_START_RE: re.Pattern[bytes] = re.compile(rb"^\s*[\[{]")
_IX_NS_RE: re.Pattern[bytes] = re.compile(
    rb'xmlns(?::\w+)?=["\']http://www\.xbrl\.org/\d{4}/inlineXBRL["\']',
    re.IGNORECASE,
)
_XBRLI_NS_RE: re.Pattern[bytes] = re.compile(
    rb'xmlns(?::\w+)?=["\']http://www\.xbrl\.org/2003/instance["\']',
    re.IGNORECASE,
)
_XSD_NS_RE: re.Pattern[bytes] = re.compile(
    rb"<(?:\w+:)?schema[\s>]", re.IGNORECASE,
)
_LINKBASE_RE: re.Pattern[bytes] = re.compile(
    rb"<(?:\w+:)?linkbase[\s>]", re.IGNORECASE,
)
_ROOT_TAG_RE: re.Pattern[bytes] = re.compile(
    rb"<([a-zA-Z_][\w.-]*(?::[a-zA-Z_][\w.-]*)?)",
)
_NS_DECL_RE: re.Pattern[bytes] = re.compile(
    rb'xmlns(?::(\w+))?=["\']([^"\']+)["\']',
)
_ENCODING_RE: re.Pattern[bytes] = re.compile(
    rb'<\?xml[^?]*encoding=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


@dataclass
class DetectionResult:
    """Result of format detection."""

    format: InputFormat
    strategy: ParserStrategy
    encoding: str = "utf-8"
    file_path: str = ""
    file_size_bytes: int = 0
    is_compressed: bool = False
    declared_namespaces: dict[str, str] = field(default_factory=dict)
    root_qname: QName = ""
    detection_confidence: float = 1.0


class FormatDetector:
    """Detect the format of an XBRL document and select the parsing strategy."""

    def __init__(
        self,
        large_file_threshold: int = DEFAULT_LARGE_FILE_THRESHOLD_BYTES,
    ) -> None:
        self._large_threshold = large_file_threshold
        self._log = logger.bind(component="format_detector")

    def detect(self, file_path: str | Path) -> DetectionResult:
        """Run the full format detection algorithm on a file.

        Args:
            file_path: Path to the file to detect.

        Returns:
            DetectionResult with format, strategy, and metadata.

        Raises:
            UnsupportedFormatError: If the format cannot be determined.
            FileNotFoundError: If the file does not exist.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        file_size = path.stat().st_size
        self._log.debug("detection_start", path=str(path), size=file_size)

        # Step 1: Read header bytes for sniffing
        header = self._read_header(path)

        # Step 2: Check for compression (ZIP / gzip)
        is_compressed = False
        if header[:4] == _PK_MAGIC:
            is_compressed = True
            result = self._detect_package(path, file_size)
            result.is_compressed = True
            return result

        if header[:2] == _GZIP_MAGIC:
            is_compressed = True
            # For gzip, we'd need to decompress to sniff, but we can
            # still make a reasonable guess from the file extension
            result = self._detect_from_extension(path, file_size)
            result.is_compressed = True
            return result

        # Step 3: Detect encoding from XML declaration
        encoding = self._detect_encoding(header)

        # Step 4: Extract declared namespaces
        namespaces = self._extract_namespaces(header)

        # Step 5: Detect root QName
        root_qname = self._detect_root_qname(header)

        # Step 6: Content-based format detection
        fmt, confidence = self._detect_format(header, namespaces, root_qname, path)

        # Step 7: Select parsing strategy based on size
        strategy = self._select_strategy(file_size, fmt)

        result = DetectionResult(
            format=fmt,
            strategy=strategy,
            encoding=encoding,
            file_path=str(path),
            file_size_bytes=file_size,
            is_compressed=is_compressed,
            declared_namespaces=namespaces,
            root_qname=root_qname,
            detection_confidence=confidence,
        )

        self._log.info(
            "detection_complete",
            format=fmt.value,
            strategy=strategy.value,
            confidence=confidence,
            size=file_size,
        )
        return result

    def _read_header(self, path: Path) -> bytes:
        """Read the first _SNIFF_SIZE bytes of a file."""
        with open(path, "rb") as f:
            return f.read(_SNIFF_SIZE)

    def _detect_encoding(self, header: bytes) -> str:
        """Detect encoding from XML declaration."""
        m = _ENCODING_RE.search(header)
        if m:
            return m.group(1).decode("ascii", errors="replace").lower()
        return "utf-8"

    def _extract_namespaces(self, header: bytes) -> dict[str, str]:
        """Extract namespace declarations from the header."""
        nsmap: dict[str, str] = {}
        for match in _NS_DECL_RE.finditer(header):
            prefix = match.group(1)
            uri = match.group(2).decode("utf-8", errors="replace")
            key = prefix.decode("utf-8", errors="replace") if prefix else ""
            nsmap[key] = uri
        return nsmap

    def _detect_root_qname(self, header: bytes) -> QName:
        """Detect the root element QName from the header."""
        # Strip XML declaration and comments before finding the first element
        stripped = header
        stripped = re.sub(rb"<\?xml[^?]*\?>", b"", stripped, count=1)
        stripped = re.sub(rb"<!--[\s\S]*?-->", b"", stripped)
        stripped = stripped.lstrip()
        m = _ROOT_TAG_RE.search(stripped)
        if m:
            tag = m.group(1).decode("utf-8", errors="replace")
            return tag
        return ""

    def _detect_format(
        self,
        header: bytes,
        namespaces: dict[str, str],
        root_qname: str,
        path: Path,
    ) -> tuple[InputFormat, float]:
        """Determine the document format from content analysis."""
        ns_uris = set(namespaces.values())
        suffix = path.suffix.lower()

        # Check for HTML/iXBRL
        if _HTML_DOCTYPE_RE.search(header) or _HTML_TAG_RE.search(header):
            if _IX_NS_RE.search(header) or NS_IX in ns_uris:
                return InputFormat.IXBRL_HTML, 0.95
            if suffix in (".htm", ".html", ".xhtml"):
                # Could still be iXBRL — check deeper
                if _IX_NS_RE.search(header):
                    return InputFormat.IXBRL_HTML, 0.9
                return InputFormat.IXBRL_HTML, 0.5  # might need full-file scan
            return InputFormat.UNKNOWN, 0.3

        # Check for XML-based formats
        if _XML_DECL_RE.search(header) or header.lstrip()[:1] == b"<":
            return self._classify_xml(header, namespaces, root_qname, suffix)

        # Check for JSON
        if _JSON_START_RE.match(header):
            return InputFormat.XBRL_JSON, 0.8

        # Check for CSV
        if suffix == ".csv" or (b"," in header[:200] and b"\n" in header[:500]):
            return InputFormat.XBRL_CSV, 0.7

        # Extension-based fallback
        return self._format_from_extension(suffix)

    def _classify_xml(
        self,
        header: bytes,
        namespaces: dict[str, str],
        root_qname: str,
        suffix: str,
    ) -> tuple[InputFormat, float]:
        """Sub-classify an XML document."""
        ns_uris = set(namespaces.values())
        root_local = root_qname.split(":")[-1] if ":" in root_qname else root_qname

        # iXBRL in XHTML
        if _IX_NS_RE.search(header) or NS_IX in ns_uris:
            if suffix == ".xhtml":
                return InputFormat.IXBRL_XHTML, 0.95
            return InputFormat.IXBRL_HTML, 0.95

        # XML Schema
        if root_local == "schema" or _XSD_NS_RE.search(header):
            return InputFormat.TAXONOMY_SCHEMA, 0.9

        # Linkbase
        if root_local == "linkbase" or _LINKBASE_RE.search(header):
            return InputFormat.LINKBASE, 0.9

        # XBRL instance
        if NS_XBRLI in ns_uris or root_local == "xbrl":
            return InputFormat.XBRL_XML, 0.95

        # Fallback based on extension
        ext_map: dict[str, InputFormat] = {
            ".xbrl": InputFormat.XBRL_XML,
            ".xml": InputFormat.XBRL_XML,
            ".xsd": InputFormat.TAXONOMY_SCHEMA,
        }
        if suffix in ext_map:
            return ext_map[suffix], 0.6

        return InputFormat.XBRL_XML, 0.4

    def _detect_package(self, path: Path, file_size: int) -> DetectionResult:
        """Detect taxonomy or report package from a ZIP file."""
        suffix = path.suffix.lower()
        name_lower = path.name.lower()

        if "taxonomy" in name_lower or suffix == ".zip":
            fmt = InputFormat.TAXONOMY_PACKAGE
        else:
            fmt = InputFormat.REPORT_PACKAGE

        return DetectionResult(
            format=fmt,
            strategy=ParserStrategy.DOM,
            file_path=str(path),
            file_size_bytes=file_size,
            detection_confidence=0.7,
        )

    def _detect_from_extension(
        self, path: Path, file_size: int
    ) -> DetectionResult:
        """Fallback detection from file extension (for compressed files)."""
        fmt, confidence = self._format_from_extension(path.suffix.lower())
        strategy = self._select_strategy(file_size, fmt)
        return DetectionResult(
            format=fmt,
            strategy=strategy,
            file_path=str(path),
            file_size_bytes=file_size,
            detection_confidence=confidence * 0.8,
        )

    def _format_from_extension(self, suffix: str) -> tuple[InputFormat, float]:
        """Guess format from file extension alone."""
        ext_map: dict[str, tuple[InputFormat, float]] = {
            ".xbrl": (InputFormat.XBRL_XML, 0.7),
            ".xml": (InputFormat.XBRL_XML, 0.5),
            ".xsd": (InputFormat.TAXONOMY_SCHEMA, 0.8),
            ".htm": (InputFormat.IXBRL_HTML, 0.6),
            ".html": (InputFormat.IXBRL_HTML, 0.6),
            ".xhtml": (InputFormat.IXBRL_XHTML, 0.7),
            ".json": (InputFormat.XBRL_JSON, 0.6),
            ".csv": (InputFormat.XBRL_CSV, 0.6),
            ".zip": (InputFormat.TAXONOMY_PACKAGE, 0.5),
        }
        return ext_map.get(suffix, (InputFormat.UNKNOWN, 0.1))

    def _select_strategy(
        self, file_size: int, fmt: InputFormat
    ) -> ParserStrategy:
        """Select DOM vs STREAMING based on file size and format."""
        # JSON and CSV always use DOM (streaming handled differently)
        if fmt in (InputFormat.XBRL_JSON, InputFormat.XBRL_CSV):
            if file_size > self._large_threshold:
                return ParserStrategy.STREAMING
            return ParserStrategy.DOM

        # Taxonomy packages always DOM
        if fmt in (InputFormat.TAXONOMY_PACKAGE, InputFormat.REPORT_PACKAGE):
            return ParserStrategy.DOM

        # XML/iXBRL: stream if large
        if file_size > self._large_threshold:
            return ParserStrategy.STREAMING

        return ParserStrategy.DOM
