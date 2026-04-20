"""DOM XML parser — safe lxml-based parsing for XBRL documents.

Uses hardened XML parsing with all XXE/entity-expansion protections.
Produces a RawXBRLDocument containing the parsed DOM tree and metadata.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from lxml import etree

from src.core.constants import NS_LINK, NS_XBRLI, NS_XLINK
from src.core.exceptions import XMLParseError, XXEError
from src.utils.xml_utils import (
    namespace_map_from_element,
    safe_parse_xml,
    safe_parse_xml_string,
)

logger = structlog.get_logger(__name__)


@dataclass
class RawXBRLDocument:
    """Intermediate representation of a parsed XML document.

    This is the output of XMLParser and the input to ModelBuilder.
    It contains the raw DOM tree plus metadata extracted during parsing.
    """

    root: etree._Element
    namespaces: dict[str, str] = field(default_factory=dict)
    source_file: str = ""
    source_size: int = 0
    schema_refs: list[str] = field(default_factory=list)
    linkbase_refs: list[str] = field(default_factory=list)
    doc_encoding: str = "utf-8"


class XMLParser:
    """Safe XML parser for XBRL documents.

    All parsing uses hardened lxml settings:
    - No entity resolution (XXE protection)
    - No network access
    - No DTD loading
    - Entity expansion limits
    """

    def __init__(self, *, huge_tree: bool = False) -> None:
        """Initialize the XML parser.

        Args:
            huge_tree: Allow very deep/wide trees (for huge filings).
        """
        self._huge_tree = huge_tree
        self._log = logger.bind(component="xml_parser")

    def parse(self, file_path: str | Path) -> RawXBRLDocument:
        """Parse an XML file into a RawXBRLDocument.

        Args:
            file_path: Path to the XML file.

        Returns:
            RawXBRLDocument containing the parsed DOM tree and metadata.

        Raises:
            XMLParseError: If the document is not well-formed XML.
            XXEError: If XXE attack patterns are detected.
            FileNotFoundError: If the file does not exist.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        file_size = path.stat().st_size
        self._log.info("xml_parse_start", path=str(path), size=file_size)

        try:
            tree = safe_parse_xml(path, huge_tree=self._huge_tree)
        except (XMLParseError, XXEError):
            raise
        except Exception as exc:
            raise XMLParseError(
                message=f"Failed to parse XML: {exc}",
                code="PARSE-0001",
                file_path=str(path),
            ) from exc

        root = tree.getroot()
        nsmap = namespace_map_from_element(root)

        # Detect encoding from XML declaration
        encoding = tree.docinfo.encoding or "utf-8"

        # Extract schema references
        schema_refs = self._extract_schema_refs(root)

        # Extract linkbase references
        linkbase_refs = self._extract_linkbase_refs(root)

        doc = RawXBRLDocument(
            root=root,
            namespaces=nsmap,
            source_file=str(path),
            source_size=file_size,
            schema_refs=schema_refs,
            linkbase_refs=linkbase_refs,
            doc_encoding=encoding.lower() if isinstance(encoding, str) else "utf-8",
        )

        self._log.info(
            "xml_parse_complete",
            path=str(path),
            namespaces=len(nsmap),
            schema_refs=len(schema_refs),
            linkbase_refs=len(linkbase_refs),
        )
        return doc

    def parse_bytes(
        self,
        data: bytes,
        source_name: str = "<bytes>",
    ) -> RawXBRLDocument:
        """Parse XML from a byte string.

        Args:
            data: Raw XML bytes.
            source_name: Human-readable identifier for error messages.

        Returns:
            RawXBRLDocument containing the parsed DOM tree and metadata.

        Raises:
            XMLParseError: If the data is not well-formed XML.
            XXEError: If XXE attack patterns are detected.
        """
        self._log.info("xml_parse_bytes_start", source=source_name, size=len(data))

        try:
            root = safe_parse_xml_string(data, huge_tree=self._huge_tree)
        except (XMLParseError, XXEError):
            raise
        except Exception as exc:
            raise XMLParseError(
                message=f"Failed to parse XML bytes: {exc}",
                code="PARSE-0001",
                file_path=source_name,
            ) from exc

        nsmap = namespace_map_from_element(root)

        # Detect encoding from the raw data
        encoding = "utf-8"
        if data[:5] == b"<?xml":
            import re
            m = re.search(rb'encoding=["\']([^"\']+)["\']', data[:200])
            if m:
                encoding = m.group(1).decode("ascii", errors="replace").lower()

        schema_refs = self._extract_schema_refs(root)
        linkbase_refs = self._extract_linkbase_refs(root)

        doc = RawXBRLDocument(
            root=root,
            namespaces=nsmap,
            source_file=source_name,
            source_size=len(data),
            schema_refs=schema_refs,
            linkbase_refs=linkbase_refs,
            doc_encoding=encoding,
        )

        self._log.info(
            "xml_parse_bytes_complete",
            source=source_name,
            namespaces=len(nsmap),
        )
        return doc

    def _extract_schema_refs(self, root: etree._Element) -> list[str]:
        """Extract schemaRef hrefs from the document."""
        refs: list[str] = []
        for elem in root.iter(f"{{{NS_LINK}}}schemaRef"):
            href = elem.get(f"{{{NS_XLINK}}}href", "")
            if href:
                refs.append(href)
        return refs

    def _extract_linkbase_refs(self, root: etree._Element) -> list[str]:
        """Extract linkbaseRef hrefs from the document."""
        refs: list[str] = []
        for elem in root.iter(f"{{{NS_LINK}}}linkbaseRef"):
            href = elem.get(f"{{{NS_XLINK}}}href", "")
            if href:
                refs.append(href)
        return refs
