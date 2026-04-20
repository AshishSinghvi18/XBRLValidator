"""XBRL file format detector.

Detects the input format (XBRL XML, iXBRL HTML, xBRL-JSON, xBRL-CSV,
taxonomy schema, linkbase) of a given file by inspecting magic bytes,
BOM markers, and content patterns.

The detector also recommends a parser strategy (DOM vs STREAMING) based
on file size relative to configurable thresholds.

Spec references:
- XBRL 2.1 §3 (instance document structure)
- Inline XBRL 1.1 §4 (iXBRL document structure)
- xBRL-JSON 1.0 §2 (document structure)
- xBRL-CSV 1.0 §2 (metadata + CSV structure)
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

from lxml import etree

from src.core.constants import (
    DEFAULT_LARGE_FILE_THRESHOLD_BYTES,
    DEFAULT_MAX_FILE_SIZE_BYTES,
    NS_IX,
    NS_LINK,
    NS_XBRLI,
    NS_XSD,
)
from src.core.exceptions import FileTooLargeError, UnsupportedFormatError
from src.core.types import InputFormat, ParserStrategy

logger = logging.getLogger(__name__)

# Thresholds for streaming strategy per format
_JSON_STREAMING_THRESHOLD = 50 * 1024 * 1024  # 50 MB
_CSV_STREAMING_THRESHOLD = 200 * 1024 * 1024  # 200 MB

# Magic bytes
_ZIP_MAGIC = b"PK\x03\x04"

# BOM markers
_BOMS: list[tuple[bytes, str]] = [
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
]

_SNIFF_SIZE = 8192

# Regex for CSV header detection (comma-separated quoted or unquoted fields)
_CSV_HEADER_RE = re.compile(
    r'^(?:"[^"]*"|[^,\r\n]+)(?:,(?:"[^"]*"|[^,\r\n]+))+',
    re.MULTILINE,
)


@dataclass
class DetectionResult:
    """Result of format detection for a single file.

    Attributes:
        format: Detected XBRL input format.
        strategy: Recommended parser strategy (DOM or STREAMING).
        encoding: Detected or assumed character encoding.
        file_path: Path to the file.
        file_size_bytes: Size of the file in bytes.
        is_compressed: Whether the file is a ZIP archive.
        mime_type: Optional MIME type hint.
    """

    format: InputFormat
    strategy: ParserStrategy
    encoding: str
    file_path: str
    file_size_bytes: int
    is_compressed: bool = False
    mime_type: Optional[str] = None


class FormatDetector:
    """Detect the XBRL format and recommended parser strategy for files.

    Parameters
    ----------
    large_file_threshold:
        Byte threshold above which the STREAMING strategy is recommended
        for XML/iXBRL formats. Defaults to 100 MB.
    max_file_size:
        Hard limit on file size. Files larger than this are rejected.
        Defaults to 10 GB.
    """

    def __init__(
        self,
        large_file_threshold: int = DEFAULT_LARGE_FILE_THRESHOLD_BYTES,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ) -> None:
        self._large_file_threshold = large_file_threshold
        self._max_file_size = max_file_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, file_path: str) -> DetectionResult:
        """Detect the format of a single file.

        Algorithm:
        1. ``os.path.getsize`` → reject if > ``max_file_size``.
        2. Read first 4 bytes → if ``PK\\x03\\x04`` → ZIP archive.
        3. Read first 8192 bytes → decode.
        4. BOM detection for encoding.
        5. Content sniffing:
           - ``<?xml`` or starts with ``<`` → XML sub-classify.
           - ``{`` → xBRL-JSON.
           - CSV header pattern → xBRL-CSV.
           - ``<!DOCTYPE html`` or ``<html`` → HTML sub-classify.
           - else → UNKNOWN → raise ``UnsupportedFormatError``.
        6. XML root tag classification.
        7. HTML body scan for ``ix:`` elements.
        8. Set strategy = STREAMING if file_size > threshold, else DOM.

        Parameters
        ----------
        file_path:
            Path to the file to detect.

        Returns
        -------
        DetectionResult

        Raises
        ------
        FileTooLargeError
            If the file exceeds ``max_file_size``.
        UnsupportedFormatError
            If the format cannot be determined.
        FileNotFoundError
            If the file does not exist.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Step 1: Size check
        file_size = os.path.getsize(file_path)
        if file_size > self._max_file_size:
            raise FileTooLargeError(
                f"File exceeds maximum allowed size",
                file_size=file_size,
                max_size=self._max_file_size,
            )

        # Step 2: Read magic bytes
        with open(file_path, "rb") as fh:
            magic = fh.read(4)

        # ZIP detection
        if magic == _ZIP_MAGIC:
            return DetectionResult(
                format=InputFormat.XBRL_XML,
                strategy=ParserStrategy.DOM,
                encoding="utf-8",
                file_path=file_path,
                file_size_bytes=file_size,
                is_compressed=True,
                mime_type="application/zip",
            )

        # Step 3: Read sniff buffer
        with open(file_path, "rb") as fh:
            raw_head = fh.read(_SNIFF_SIZE)

        # Step 4: BOM / encoding detection
        encoding = "utf-8"
        content_start = 0
        for bom_bytes, bom_encoding in _BOMS:
            if raw_head.startswith(bom_bytes):
                encoding = bom_encoding
                content_start = len(bom_bytes)
                break

        try:
            head_text = raw_head[content_start:].decode(
                encoding.replace("-sig", ""), errors="replace"
            )
        except Exception:  # noqa: BLE001
            head_text = raw_head[content_start:].decode("utf-8", errors="replace")

        head_stripped = head_text.lstrip()

        # Step 5: Content sniffing
        head_lower = head_stripped.lower()

        # Check for HTML first (may contain iXBRL)
        if head_lower.startswith("<!doctype html") or head_lower.startswith("<html"):
            fmt = self._classify_html(file_path, head_text)
            strategy = self._pick_strategy(fmt, file_size)
            mime = "text/html"
            return DetectionResult(
                format=fmt,
                strategy=strategy,
                encoding=encoding,
                file_path=file_path,
                file_size_bytes=file_size,
                mime_type=mime,
            )

        # XML-like content
        if head_stripped.startswith("<?xml") or head_stripped.startswith("<"):
            fmt = self._classify_xml(file_path, head_text)
            strategy = self._pick_strategy(fmt, file_size)
            mime = "application/xml"
            if fmt == InputFormat.IXBRL_HTML:
                mime = "text/html"
            return DetectionResult(
                format=fmt,
                strategy=strategy,
                encoding=encoding,
                file_path=file_path,
                file_size_bytes=file_size,
                mime_type=mime,
            )

        # JSON
        if head_stripped.startswith("{"):
            strategy = (
                ParserStrategy.STREAMING
                if file_size > _JSON_STREAMING_THRESHOLD
                else ParserStrategy.DOM
            )
            return DetectionResult(
                format=InputFormat.XBRL_JSON,
                strategy=strategy,
                encoding=encoding,
                file_path=file_path,
                file_size_bytes=file_size,
                mime_type="application/json",
            )

        # CSV
        if _CSV_HEADER_RE.match(head_stripped):
            strategy = (
                ParserStrategy.STREAMING
                if file_size > _CSV_STREAMING_THRESHOLD
                else ParserStrategy.DOM
            )
            return DetectionResult(
                format=InputFormat.XBRL_CSV,
                strategy=strategy,
                encoding=encoding,
                file_path=file_path,
                file_size_bytes=file_size,
                mime_type="text/csv",
            )

        # Unknown
        raise UnsupportedFormatError(
            f"Cannot determine format of file: {file_path}"
        )

    def detect_batch(self, file_paths: list[str]) -> list[DetectionResult]:
        """Detect format for multiple files.

        Processes files sequentially, collecting results. Errors for
        individual files are logged but do not prevent processing of
        subsequent files.

        Parameters
        ----------
        file_paths:
            List of file paths to detect.

        Returns
        -------
        list[DetectionResult]
            Results for files that were successfully detected.
        """
        results: list[DetectionResult] = []
        for path in file_paths:
            try:
                results.append(self.detect(path))
            except (FileTooLargeError, UnsupportedFormatError, FileNotFoundError) as exc:
                logger.error("Format detection failed for %s: %s", path, exc)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Unexpected error detecting format for %s: %s", path, exc
                )
        return results

    # ------------------------------------------------------------------
    # XML sub-classification
    # ------------------------------------------------------------------

    def _classify_xml(self, file_path: str, head_text: str) -> InputFormat:
        """Sub-classify XML content by inspecting the root element.

        Returns the appropriate ``InputFormat`` for XBRL XML, taxonomy
        schema, linkbase, or iXBRL (if an HTML root is encountered).
        """
        head_lower = head_text.lower()

        # Quick checks from text content before parsing
        if "<html" in head_lower:
            return self._classify_html(file_path, head_text)

        # Attempt to identify root tag via partial parse
        try:
            # Use iterparse to get the root tag without loading the full file
            with open(file_path, "rb") as fh:
                for event, elem in etree.iterparse(
                    fh, events=("start",), resolve_entities=False
                ):
                    root_tag = elem.tag
                    root_nsmap = dict(elem.nsmap) if elem.nsmap else {}
                    # Clean up
                    elem.clear()
                    break
                else:
                    return InputFormat.UNKNOWN

            return self._classify_root_tag(root_tag, root_nsmap)

        except etree.XMLSyntaxError:
            logger.debug("XML syntax error during classification of %s", file_path)
            # Fall back to text-based heuristics
            return self._classify_xml_text(head_lower)

    def _classify_root_tag(
        self, root_tag: str, nsmap: dict[str | None, str]
    ) -> InputFormat:
        """Classify based on the XML root element tag."""
        from src.utils.xml_utils import get_namespace, strip_namespace

        ns = get_namespace(root_tag)
        local = strip_namespace(root_tag)

        # XBRL instance: {NS_XBRLI}xbrl
        if ns == NS_XBRLI and local == "xbrl":
            return InputFormat.XBRL_XML

        # Taxonomy schema: {NS_XSD}schema
        if ns == NS_XSD and local == "schema":
            return InputFormat.TAXONOMY_SCHEMA

        # Linkbase: {NS_LINK}linkbase
        if ns == NS_LINK and local == "linkbase":
            return InputFormat.LINKBASE

        # HTML root → iXBRL check
        if local.lower() == "html":
            return InputFormat.IXBRL_HTML

        # Other XBRL namespace → assume instance
        if NS_XBRLI in (nsmap.get(None, ""), *nsmap.values()):
            return InputFormat.XBRL_XML

        return InputFormat.UNKNOWN

    @staticmethod
    def _classify_xml_text(head_lower: str) -> InputFormat:
        """Text-based fallback heuristic for XML classification."""
        if "xbrli:xbrl" in head_lower or f"{NS_XBRLI}" in head_lower:
            return InputFormat.XBRL_XML
        if "xs:schema" in head_lower or "xsd:schema" in head_lower:
            return InputFormat.TAXONOMY_SCHEMA
        if "link:linkbase" in head_lower:
            return InputFormat.LINKBASE
        return InputFormat.UNKNOWN

    # ------------------------------------------------------------------
    # HTML / iXBRL classification
    # ------------------------------------------------------------------

    def _classify_html(self, file_path: str, head_text: str) -> InputFormat:
        """Check whether an HTML file is iXBRL by scanning for ``ix:`` elements.

        An HTML document is classified as iXBRL if:
        - It contains namespace declarations for the iXBRL namespace, OR
        - It contains elements in the ``ix:`` namespace (e.g.
          ``ix:nonFraction``, ``ix:nonNumeric``, ``ix:header``).
        """
        head_lower = head_text.lower()

        # Quick text-based check
        if NS_IX in head_text:
            return InputFormat.IXBRL_HTML
        if "ix:header" in head_lower or "ix:nonfraction" in head_lower:
            return InputFormat.IXBRL_HTML
        if "ix:nonnumeric" in head_lower or "ix:references" in head_lower:
            return InputFormat.IXBRL_HTML

        # For larger files, only the head may not contain ix elements
        # Try parsing the first portion
        try:
            from lxml import html as lxml_html

            doc = lxml_html.fromstring(head_text.encode("utf-8", errors="replace"))
            # Check namespace map
            nsmap = doc.nsmap if hasattr(doc, "nsmap") else {}
            for uri in (nsmap or {}).values():
                if uri and "inlineXBRL" in uri:
                    return InputFormat.IXBRL_HTML

            # Walk for ix: prefixed elements
            for elem in doc.iter():
                if isinstance(elem.tag, str) and (
                    elem.tag.startswith(f"{{{NS_IX}}}") or "ix:" in elem.tag
                ):
                    return InputFormat.IXBRL_HTML
        except Exception:  # noqa: BLE001
            pass

        return InputFormat.IXBRL_HTML if "ix:" in head_lower else InputFormat.UNKNOWN

    # ------------------------------------------------------------------
    # Strategy selection
    # ------------------------------------------------------------------

    def _pick_strategy(
        self, fmt: InputFormat, file_size: int
    ) -> ParserStrategy:
        """Choose DOM vs STREAMING based on format and file size."""
        if fmt in (InputFormat.XBRL_XML, InputFormat.IXBRL_HTML, InputFormat.LINKBASE):
            threshold = self._large_file_threshold
        elif fmt == InputFormat.XBRL_JSON:
            threshold = _JSON_STREAMING_THRESHOLD
        elif fmt == InputFormat.XBRL_CSV:
            threshold = _CSV_STREAMING_THRESHOLD
        else:
            return ParserStrategy.DOM

        return ParserStrategy.STREAMING if file_size > threshold else ParserStrategy.DOM
