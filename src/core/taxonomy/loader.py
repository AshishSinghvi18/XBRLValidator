"""Taxonomy schema loader — resolves and loads taxonomy schemas from XML.

Uses safe XML parsing (XXE-protected).  Loads schema imports recursively
with cycle detection to prevent infinite loops on circular imports.

References:
    - XBRL 2.1 §5.1 (Schema Files)
    - XBRL 2.1 §5.1.1 (Item element declarations)
    - XBRL 2.1 §5.1.3 (roleType)
    - XBRL 2.1 §5.1.4 (arcroleType)
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urljoin

from lxml import etree

from src.core.constants import (
    NS_LINK,
    NS_XBRLDT,
    NS_XBRLI,
    NS_XLINK,
    NS_XSD,
)
from src.core.exceptions import TaxonomyNotFoundError, TaxonomyResolutionError
from src.core.model.concept import Concept
from src.core.qname import format_qname
from src.core.taxonomy.schema import ArcroleType, RoleType, TaxonomySchema
from src.core.types import BalanceType, ConceptType, PeriodType
from src.security.xxe_guard import XXEGuard

logger = logging.getLogger(__name__)

# Pre-computed Clark-notation tag names for XSD/link elements
_XS_ELEMENT = f"{{{NS_XSD}}}element"
_XS_IMPORT = f"{{{NS_XSD}}}import"
_XS_INCLUDE = f"{{{NS_XSD}}}include"
_LINK_LINKBASE_REF = f"{{{NS_LINK}}}linkbaseRef"
_LINK_ROLE_TYPE = f"{{{NS_LINK}}}roleType"
_LINK_ARCROLE_TYPE = f"{{{NS_LINK}}}arcroleType"
_LINK_DEFINITION = f"{{{NS_LINK}}}definition"
_LINK_USED_ON = f"{{{NS_LINK}}}usedOn"
_XLINK_HREF = f"{{{NS_XLINK}}}href"
_XBRLDT_TYPED_DOMAIN_REF = f"{{{NS_XBRLDT}}}typedDomainRef"

# Substitution groups that map to ConceptType values
_SUBST_GROUP_MAP: dict[str, ConceptType] = {
    "item": ConceptType.ITEM,
    "tuple": ConceptType.TUPLE,
    f"{{{NS_XBRLDT}}}hypercubeItem": ConceptType.HYPERCUBE,
    f"{{{NS_XBRLDT}}}dimensionItem": ConceptType.DIMENSION,
}


def _resolve_url(url: str, base_url: str) -> str:
    """Resolve *url* against *base_url*, handling both file paths and URIs."""
    if not base_url:
        return url

    # If url is already absolute (has scheme or is absolute path), return it
    if "://" in url or Path(url).is_absolute():
        return url

    # If base_url is a local file path, use Path-based resolution
    if "://" not in base_url:
        base_path = Path(base_url)
        if base_path.is_file():
            base_path = base_path.parent
        resolved = (base_path / url).resolve()
        return str(resolved)

    return urljoin(base_url, url)


class TaxonomyLoader:
    """Loads taxonomy schemas from XML source files.

    Uses safe XML parsing (XXE-protected).  Loads schema imports recursively
    with cycle detection.

    Spec: XBRL 2.1 §5.1 (Schema Files)

    Args:
        cache_dir: Optional directory for taxonomy cache (unused for now —
                   reserved for :class:`TaxonomyCache` integration).
    """

    def __init__(self, cache_dir: str | None = None) -> None:
        self._loaded: dict[str, TaxonomySchema] = {}
        self._cache_dir = cache_dir
        self._xxe_guard = XXEGuard()

    @property
    def loaded_schemas(self) -> dict[str, TaxonomySchema]:
        """Return all schemas loaded so far (URL → TaxonomySchema)."""
        return dict(self._loaded)

    def load_schema(self, url: str, base_url: str = "") -> TaxonomySchema:
        """Load a taxonomy schema from URL, resolving imports recursively.

        Args:
            url:      Schema URL or file path (absolute or relative).
            base_url: Base URL for resolving relative *url*.

        Returns:
            Loaded :class:`TaxonomySchema`.

        Raises:
            TaxonomyNotFoundError: If the schema file does not exist.
            TaxonomyResolutionError: On XML parse errors or other failures.
        """
        resolved = _resolve_url(url, base_url)

        # Cycle guard — return cached schema if already loaded
        if resolved in self._loaded:
            return self._loaded[resolved]

        schema_path = Path(resolved)
        if not schema_path.is_file():
            raise TaxonomyNotFoundError(url=resolved)

        try:
            xml_bytes = schema_path.read_bytes()
        except OSError as exc:
            raise TaxonomyResolutionError(
                code="taxonomy:ioError",
                message=f"Cannot read schema file: {exc}",
                url=resolved,
            ) from exc

        schema = self._parse_schema_xml(xml_bytes, resolved)

        # Recursively load imported schemas
        for import_url in list(schema.imported_schemas):
            try:
                self.load_schema(import_url, base_url=resolved)
            except TaxonomyNotFoundError:
                logger.warning(
                    "Imported schema not found: %s (referenced from %s)",
                    import_url,
                    resolved,
                )

        return schema

    def _parse_schema_xml(self, xml_bytes: bytes, url: str) -> TaxonomySchema:
        """Parse schema XML into TaxonomySchema.

        Extracts concepts, roleTypes, arcroleTypes, imports, and
        linkbase references.

        Args:
            xml_bytes: Raw XML content of the schema document.
            url:       Resolved URL of the schema (used as cache key).

        Returns:
            Populated :class:`TaxonomySchema`.

        Raises:
            TaxonomyResolutionError: If the XML cannot be parsed.
        """
        try:
            root = self._xxe_guard.safe_fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            raise TaxonomyResolutionError(
                code="taxonomy:xmlError",
                message=f"Malformed taxonomy schema XML: {exc}",
                url=url,
            ) from exc

        target_ns = root.get("targetNamespace", "")

        # Register placeholder early to break import cycles
        schema = TaxonomySchema(url=url, target_namespace=target_ns)
        self._loaded[url] = schema

        schema.concepts = self._extract_concepts(root, target_ns, url)
        schema.imported_schemas = self._extract_imports(root, url)
        schema.linkbase_refs = self._extract_linkbase_refs(root, url)
        schema.role_types = self._extract_role_types(root)
        schema.arcrole_types = self._extract_arcrole_types(root)

        return schema

    def _extract_concepts(
        self,
        root: etree._Element,
        target_ns: str,
        schema_url: str,
    ) -> dict[str, Concept]:
        """Extract concept definitions from top-level ``xs:element`` declarations.

        Only elements with a ``name`` attribute and a ``substitutionGroup``
        attribute are considered XBRL concept declarations.

        Args:
            root:       Root element of the schema document.
            target_ns:  Target namespace of the schema.
            schema_url: URL of the schema (stored in each Concept).

        Returns:
            Clark QName → :class:`Concept` mapping.
        """
        concepts: dict[str, Concept] = {}

        for elem in root.iterchildren(_XS_ELEMENT):
            name = elem.get("name")
            if not name:
                continue

            subst_group = elem.get("substitutionGroup", "")
            if not subst_group:
                continue

            qname = format_qname(target_ns, name)

            # Determine concept type from substitution group.
            # The substitutionGroup attribute may be a prefixed QName
            # (e.g. "xbrli:item") — extract the local name for lookup
            # against our known substitution groups.
            subst_local = subst_group.split(":")[-1] if ":" in subst_group else subst_group
            concept_type = _SUBST_GROUP_MAP.get(subst_local, ConceptType.ITEM)

            # Check for typed dimension
            typed_domain_ref = elem.get(_XBRLDT_TYPED_DOMAIN_REF)
            if typed_domain_ref is not None:
                concept_type = ConceptType.TYPED_DIMENSION

            # Abstract flag
            abstract = elem.get("abstract", "false").lower() == "true"
            if abstract and concept_type == ConceptType.ITEM:
                concept_type = ConceptType.ABSTRACT

            # Period type — xbrli:periodType (XBRL 2.1 §5.1.1)
            period_type_str = elem.get(
                f"{{{NS_XBRLI}}}periodType",
                elem.get("periodType", ""),
            )
            try:
                period_type = PeriodType(period_type_str) if period_type_str else PeriodType.DURATION
            except ValueError:
                period_type = PeriodType.DURATION

            # Balance type — xbrli:balance (XBRL 2.1 §5.1.1)
            balance_str = elem.get(
                f"{{{NS_XBRLI}}}balance",
                elem.get("balance", ""),
            )
            try:
                balance_type = BalanceType(balance_str) if balance_str else BalanceType.NONE
            except ValueError:
                balance_type = BalanceType.NONE

            nillable = elem.get("nillable", "false").lower() == "true"
            type_name = elem.get("type", "")

            concept = Concept(
                qname=qname,
                concept_type=concept_type,
                period_type=period_type,
                balance_type=balance_type,
                abstract=abstract,
                nillable=nillable,
                substitution_group=subst_local,
                type_name=type_name,
                schema_url=schema_url,
                typed_domain_ref=typed_domain_ref,
            )
            concepts[qname] = concept

        return concepts

    def _extract_imports(
        self,
        root: etree._Element,
        schema_url: str,
    ) -> list[str]:
        """Extract URLs from ``xs:import`` and ``xs:include`` elements.

        Args:
            root:       Root element of the schema.
            schema_url: URL of the current schema (base for resolution).

        Returns:
            List of resolved import/include URLs.
        """
        urls: list[str] = []
        for tag in (_XS_IMPORT, _XS_INCLUDE):
            for elem in root.iterchildren(tag):
                location = elem.get("schemaLocation")
                if location:
                    resolved = _resolve_url(location, schema_url)
                    urls.append(resolved)
        return urls

    def _extract_linkbase_refs(
        self,
        root: etree._Element,
        schema_url: str,
    ) -> list[str]:
        """Extract linkbase URLs from ``link:linkbaseRef`` elements.

        Searches the ``xs:annotation/xs:appinfo`` hierarchy as required by
        XBRL 2.1 §5.1.2.

        Args:
            root:       Root element of the schema.
            schema_url: URL of the current schema (base for resolution).

        Returns:
            List of resolved linkbase URLs.
        """
        urls: list[str] = []
        for elem in root.iter(_LINK_LINKBASE_REF):
            href = elem.get(_XLINK_HREF)
            if href:
                resolved = _resolve_url(href, schema_url)
                urls.append(resolved)
        return urls

    @staticmethod
    def _extract_role_types(root: etree._Element) -> dict[str, RoleType]:
        """Extract ``link:roleType`` definitions from the schema.

        Args:
            root: Root element of the schema.

        Returns:
            roleURI → :class:`RoleType` mapping.
        """
        role_types: dict[str, RoleType] = {}
        for elem in root.iter(_LINK_ROLE_TYPE):
            role_uri = elem.get("roleURI", "")
            if not role_uri:
                continue

            definition = ""
            used_on: list[str] = []

            for child in elem:
                if child.tag == _LINK_DEFINITION:
                    definition = (child.text or "").strip()
                elif child.tag == _LINK_USED_ON:
                    text = (child.text or "").strip()
                    if text:
                        used_on.append(text)

            role_types[role_uri] = RoleType(
                role_uri=role_uri,
                definition=definition,
                used_on=used_on,
            )
        return role_types

    @staticmethod
    def _extract_arcrole_types(root: etree._Element) -> dict[str, ArcroleType]:
        """Extract ``link:arcroleType`` definitions from the schema.

        Args:
            root: Root element of the schema.

        Returns:
            arcroleURI → :class:`ArcroleType` mapping.
        """
        arcrole_types: dict[str, ArcroleType] = {}
        for elem in root.iter(_LINK_ARCROLE_TYPE):
            arcrole_uri = elem.get("arcroleURI", "")
            if not arcrole_uri:
                continue

            cycles_allowed = elem.get("cyclesAllowed", "none")
            definition = ""
            used_on: list[str] = []

            for child in elem:
                if child.tag == _LINK_DEFINITION:
                    definition = (child.text or "").strip()
                elif child.tag == _LINK_USED_ON:
                    text = (child.text or "").strip()
                    if text:
                        used_on.append(text)

            arcrole_types[arcrole_uri] = ArcroleType(
                arcrole_uri=arcrole_uri,
                definition=definition,
                used_on=used_on,
                cycles_allowed=cycles_allowed,
            )
        return arcrole_types
