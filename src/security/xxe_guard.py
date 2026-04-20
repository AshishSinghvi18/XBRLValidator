"""XXE (XML External Entity) prevention guard.

Provides a hardened XML parser and content scanner to prevent XXE attacks
including external entity expansion, SYSTEM/PUBLIC entity references, and
parameter entity abuse.

Spec references:
  - OWASP XXE Prevention Cheat Sheet
  - Rule 3 — Zero-Trust Parsing
  - CWE-611: Improper Restriction of XML External Entity Reference

Example::

    guard = XXEGuard()
    tree = guard.safe_parse("filing.xbrl")
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog
from lxml import etree

from src.core.exceptions import XXEError

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Patterns that indicate XXE payloads in raw XML content.
# Covers both general and parameter entity declarations with SYSTEM/PUBLIC refs.
_ENTITY_DECL_RE = re.compile(
    rb"<!ENTITY\s",
    re.IGNORECASE,
)
_SYSTEM_RE = re.compile(
    rb"<!ENTITY\s+[%\s]*\w+\s+SYSTEM\s",
    re.IGNORECASE,
)
_PUBLIC_RE = re.compile(
    rb"<!ENTITY\s+[%\s]*\w+\s+PUBLIC\s",
    re.IGNORECASE,
)
_PARAMETER_ENTITY_RE = re.compile(
    rb"<!ENTITY\s+%\s",
    re.IGNORECASE,
)
_DOCTYPE_RE = re.compile(
    rb"<!DOCTYPE\s+\w+\s+(?:SYSTEM|PUBLIC)\s",
    re.IGNORECASE,
)


class XXEGuard:
    """Wraps ``lxml.etree.XMLParser`` with XXE-safe settings.

    All parsing performed through this guard disables entity resolution,
    network access, and DTD loading to prevent XXE attacks.
    """

    def __init__(self) -> None:
        self._log = logger.bind(component="xxe_guard")

    @staticmethod
    def create_safe_parser() -> etree.XMLParser:
        """Return a hardened ``XMLParser`` with XXE-safe settings.

        Settings applied:
          - ``resolve_entities=False`` — prevents entity expansion
          - ``no_network=True`` — blocks all network access during parsing
          - ``dtd_validation=False`` — disables DTD-based validation
          - ``load_dtd=False`` — prevents loading of external DTDs
          - ``huge_tree=False`` — rejects documents with excessive depth/width
          - ``collect_ids=True`` — retains ID attribute indexing for lookups

        Returns:
            A configured ``lxml.etree.XMLParser`` instance.
        """
        return etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            dtd_validation=False,
            load_dtd=False,
            huge_tree=False,
            collect_ids=True,
        )

    def safe_parse(
        self,
        source: str | Path | bytes,
        parser: etree.XMLParser | None = None,
    ) -> etree._ElementTree:
        """Parse an XML document with XXE protections.

        The raw content is first scanned for XXE indicators before parsing.
        If *parser* is ``None``, a safe parser is created automatically.

        Args:
            source: File path (str/Path) or raw XML bytes.
            parser: Optional pre-configured parser.  If ``None``, one is
                created via :meth:`create_safe_parser`.

        Returns:
            The parsed ``ElementTree``.

        Raises:
            XXEError: If XXE indicators are detected in the content.
            lxml.etree.XMLSyntaxError: If the XML is malformed.
        """
        safe_parser = parser or self.create_safe_parser()

        if isinstance(source, bytes):
            self.check_for_xxe(source)
            self._log.debug("xxe_safe_parse_bytes", length=len(source))
            return etree.ElementTree(etree.fromstring(source, parser=safe_parser))

        path = Path(source) if isinstance(source, str) else source
        raw = path.read_bytes()
        self.check_for_xxe(raw)

        self._log.debug("xxe_safe_parse_file", path=str(path), size=len(raw))
        return etree.parse(str(path), parser=safe_parser)

    def safe_fromstring(self, text: bytes) -> etree._Element:
        """Parse XML bytes into an Element with XXE protections.

        Args:
            text: Raw XML content as bytes.

        Returns:
            The root ``Element``.

        Raises:
            XXEError: If XXE indicators are detected.
        """
        self.check_for_xxe(text)
        parser = self.create_safe_parser()
        self._log.debug("xxe_safe_fromstring", length=len(text))
        return etree.fromstring(text, parser=parser)

    def check_for_xxe(self, content: bytes) -> None:
        """Scan raw XML bytes for XXE indicators.

        Checks for:
          - ``<!ENTITY`` declarations (general and parameter entities)
          - ``SYSTEM`` references in entity or DOCTYPE declarations
          - ``PUBLIC`` references in entity or DOCTYPE declarations
          - Parameter entity declarations (``<!ENTITY % ...``)

        Args:
            content: Raw XML bytes to scan.

        Raises:
            XXEError: If any XXE indicator pattern is found.
        """
        if _SYSTEM_RE.search(content):
            self._log.warning(
                "xxe_system_entity_detected",
                snippet=content[:200].decode("utf-8", errors="replace"),
            )
            raise XXEError(
                "SYSTEM entity reference detected in XML content",
                code="SEC-0001",
                context={"pattern": "SYSTEM entity"},
            )

        if _PUBLIC_RE.search(content):
            self._log.warning(
                "xxe_public_entity_detected",
                snippet=content[:200].decode("utf-8", errors="replace"),
            )
            raise XXEError(
                "PUBLIC entity reference detected in XML content",
                code="SEC-0001",
                context={"pattern": "PUBLIC entity"},
            )

        if _PARAMETER_ENTITY_RE.search(content):
            self._log.warning(
                "xxe_parameter_entity_detected",
                snippet=content[:200].decode("utf-8", errors="replace"),
            )
            raise XXEError(
                "Parameter entity declaration detected in XML content",
                code="SEC-0001",
                context={"pattern": "parameter entity"},
            )

        if _DOCTYPE_RE.search(content):
            self._log.warning(
                "xxe_doctype_external_detected",
                snippet=content[:200].decode("utf-8", errors="replace"),
            )
            raise XXEError(
                "DOCTYPE with SYSTEM/PUBLIC reference detected",
                code="SEC-0001",
                context={"pattern": "DOCTYPE external"},
            )

        if _ENTITY_DECL_RE.search(content):
            self._log.warning(
                "xxe_entity_declaration_detected",
                snippet=content[:200].decode("utf-8", errors="replace"),
            )
            raise XXEError(
                "Entity declaration detected in XML content",
                code="SEC-0001",
                context={"pattern": "ENTITY declaration"},
            )
