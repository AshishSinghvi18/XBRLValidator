"""Low-level XML parser for XBRL instance and taxonomy documents.

Wraps :class:`~src.security.xxe_guard.XXEGuard` to provide safe XML
parsing and produces a :class:`RawXBRLDocument` containing the parsed
element tree together with extracted namespace mappings, schema
references, and linkbase references.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from lxml import etree

from src.core.constants import NS_LINK, NS_XLINK
from src.core.exceptions import XMLParseError
from src.security.xxe_guard import XXEGuard

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Data container returned by the parser
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawXBRLDocument:
    """Immutable container for a parsed XBRL XML document.

    Attributes:
        root: The root :class:`lxml.etree._Element` of the document.
        namespaces: Prefix → URI namespace map collected from the root element.
        source_file: File path or symbolic source name (e.g. ``"<bytes>"``).
        source_size: Size of the source in bytes.
        declared_schema_refs: ``xlink:href`` values from ``link:schemaRef``
            elements found directly under the root.
        declared_linkbase_refs: ``xlink:href`` values from ``link:linkbaseRef``
            elements found directly under the root.
        doc_encoding: Character encoding declared in the XML declaration,
            defaulting to ``"utf-8"`` when absent.
    """

    root: etree._Element
    namespaces: dict[str, str]
    source_file: str
    source_size: int
    declared_schema_refs: list[str] = field(default_factory=list)
    declared_linkbase_refs: list[str] = field(default_factory=list)
    doc_encoding: str = "utf-8"


# ---------------------------------------------------------------------------
# Qualified element / attribute names (precomputed for performance)
# ---------------------------------------------------------------------------

_SCHEMA_REF_TAG = f"{{{NS_LINK}}}schemaRef"
_LINKBASE_REF_TAG = f"{{{NS_LINK}}}linkbaseRef"
_XLINK_HREF = f"{{{NS_XLINK}}}href"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class XMLParser:
    """Parse XML files or byte strings into :class:`RawXBRLDocument` objects.

    All parsing is performed through an :class:`XXEGuard` to prevent XXE
    injection and entity-expansion attacks.

    Args:
        xxe_guard: An existing :class:`XXEGuard` instance.  When *None*,
            a new guard is created automatically.
        huge_tree: If ``True``, allow lxml to handle very deep trees and
            long text content.  Only enable for known-safe large filings.
    """

    def __init__(
        self,
        xxe_guard: XXEGuard | None = None,
        huge_tree: bool = False,
    ) -> None:
        self._xxe_guard: XXEGuard = xxe_guard or XXEGuard()
        self._huge_tree: bool = huge_tree

    # -- public API ---------------------------------------------------------

    def parse(self, file_path: str) -> RawXBRLDocument:
        """Parse an XML file on disk and return a :class:`RawXBRLDocument`.

        Args:
            file_path: Absolute or relative path to the XML file.

        Returns:
            A :class:`RawXBRLDocument` populated with the parsed tree and
            extracted metadata.

        Raises:
            XMLParseError: If the file does not exist or the XML is malformed.
        """
        if not os.path.isfile(file_path):
            raise XMLParseError(
                code="xml:fileNotFound",
                message=f"File not found: {file_path}",
                file_path=file_path,
            )

        try:
            tree = self._xxe_guard.safe_parse(
                file_path, huge_tree=self._huge_tree
            )
        except etree.XMLSyntaxError as exc:
            raise XMLParseError(
                code="xml:syntaxError",
                message=str(exc),
                file_path=file_path,
                line=getattr(exc, "lineno", None),
                column=getattr(exc, "offset", None),
            ) from exc

        root = tree.getroot()
        namespaces = self._collect_namespaces(root)
        schema_refs = self._extract_refs(root, _SCHEMA_REF_TAG)
        linkbase_refs = self._extract_refs(root, _LINKBASE_REF_TAG)
        encoding = self._detect_encoding(tree)
        source_size = os.path.getsize(file_path)

        return RawXBRLDocument(
            root=root,
            namespaces=namespaces,
            source_file=file_path,
            source_size=source_size,
            declared_schema_refs=schema_refs,
            declared_linkbase_refs=linkbase_refs,
            doc_encoding=encoding,
        )

    def parse_bytes(
        self,
        data: bytes,
        source_name: str = "<bytes>",
    ) -> RawXBRLDocument:
        """Parse raw XML bytes and return a :class:`RawXBRLDocument`.

        Args:
            data: Raw XML content as bytes.
            source_name: A symbolic name recorded as the source
                (e.g. a URL or ``"<bytes>"``).

        Returns:
            A :class:`RawXBRLDocument` populated with the parsed tree and
            extracted metadata.

        Raises:
            XMLParseError: If the XML is malformed.
        """
        try:
            root = self._xxe_guard.safe_fromstring(data)
        except etree.XMLSyntaxError as exc:
            raise XMLParseError(
                code="xml:syntaxError",
                message=str(exc),
                file_path=source_name,
                line=getattr(exc, "lineno", None),
                column=getattr(exc, "offset", None),
            ) from exc

        tree = etree.ElementTree(root)
        namespaces = self._collect_namespaces(root)
        schema_refs = self._extract_refs(root, _SCHEMA_REF_TAG)
        linkbase_refs = self._extract_refs(root, _LINKBASE_REF_TAG)
        encoding = self._detect_encoding(tree)

        return RawXBRLDocument(
            root=root,
            namespaces=namespaces,
            source_file=source_name,
            source_size=len(data),
            declared_schema_refs=schema_refs,
            declared_linkbase_refs=linkbase_refs,
            doc_encoding=encoding,
        )

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _collect_namespaces(root: etree._Element) -> dict[str, str]:
        """Return a prefix → URI mapping from the root element's *nsmap*.

        The ``None`` key produced by lxml for the default namespace is
        replaced with the empty string ``""`` so that the mapping contains
        only ``str`` keys.
        """
        ns: dict[str, str] = {}
        for prefix, uri in root.nsmap.items():
            ns[prefix if prefix is not None else ""] = uri
        return ns

    @staticmethod
    def _extract_refs(root: etree._Element, tag: str) -> list[str]:
        """Extract ``xlink:href`` values from child elements matching *tag*."""
        refs: list[str] = []
        for elem in root.iter(tag):
            href = elem.get(_XLINK_HREF)
            if href is not None:
                refs.append(href)
        return refs

    @staticmethod
    def _detect_encoding(tree: etree._ElementTree) -> str:
        """Return the encoding declared in the XML declaration, or ``utf-8``."""
        doc_info = tree.docinfo
        return doc_info.encoding.lower() if doc_info.encoding else "utf-8"
