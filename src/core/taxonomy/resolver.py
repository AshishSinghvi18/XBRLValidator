"""DTS (Discoverable Taxonomy Set) resolver.

Implements the DTS discovery algorithm per XBRL 2.1 §3.  Starting from
one or more entry-point URLs the resolver follows ``import``, ``include``,
and ``linkbaseRef`` references to build a complete :class:`TaxonomyModel`.

Spec references:
- XBRL 2.1 §3 (DTS discovery)
- XBRL 2.1 §5 (linkbases)
- XBRL Dimensions 1.0 (dimension relationships)
"""

from __future__ import annotations

import logging
from collections import deque
from decimal import Decimal
from typing import Any, Optional

from lxml import etree

from src.core.constants import (
    ARCROLE_CONCEPT_LABEL,
    ARCROLE_CONCEPT_REF,
    ARCROLE_DIMENSION_DEFAULT,
    ARCROLE_PARENT_CHILD,
    ARCROLE_SUMMATION_ITEM,
    DEFAULT_TAXONOMY_FETCH_TIMEOUT_S,
    NS_LINK,
    NS_XBRLI,
    NS_XLINK,
    NS_XSD,
)
from src.core.exceptions import TaxonomyResolutionError
from src.core.taxonomy.cache import TaxonomyCache
from src.core.taxonomy.catalog import XMLCatalog
from src.core.taxonomy.package import PackageLoader, TaxonomyPackage
from src.core.types import BalanceType, LinkbaseType, PeriodType, QName

logger = logging.getLogger(__name__)

# Linkbase arcrole → LinkbaseType mapping
_ARCROLE_TO_TYPE: dict[str, LinkbaseType] = {
    ARCROLE_SUMMATION_ITEM: LinkbaseType.CALCULATION,
    ARCROLE_PARENT_CHILD: LinkbaseType.PRESENTATION,
    ARCROLE_CONCEPT_LABEL: LinkbaseType.LABEL,
    ARCROLE_CONCEPT_REF: LinkbaseType.REFERENCE,
}

# Linkbase role-hint → LinkbaseType mapping
_ROLE_HINT_TO_TYPE: dict[str, LinkbaseType] = {
    "calculationLink": LinkbaseType.CALCULATION,
    "presentationLink": LinkbaseType.PRESENTATION,
    "definitionLink": LinkbaseType.DEFINITION,
    "labelLink": LinkbaseType.LABEL,
    "referenceLink": LinkbaseType.REFERENCE,
}

# Numeric XSD base types
_NUMERIC_TYPES: frozenset[str] = frozenset(
    {
        "decimal",
        "float",
        "double",
        "integer",
        "nonPositiveInteger",
        "negativeInteger",
        "long",
        "int",
        "short",
        "byte",
        "nonNegativeInteger",
        "unsignedLong",
        "unsignedInt",
        "unsignedShort",
        "unsignedByte",
        "positiveInteger",
        "monetaryItemType",
        "sharesItemType",
        "pureItemType",
        "decimalItemType",
        "floatItemType",
        "doubleItemType",
        "integerItemType",
    }
)


class TaxonomyResolver:
    """Resolve taxonomy entry points into a complete TaxonomyModel.

    Implements the DTS discovery algorithm per XBRL 2.1 §3.

    Parameters
    ----------
    cache:
        Optional taxonomy cache.  A default is created if not supplied.
    catalog:
        Optional XML catalog for URI rewriting.
    fetch_timeout:
        HTTP fetch timeout in seconds.
    """

    def __init__(
        self,
        cache: TaxonomyCache | None = None,
        catalog: XMLCatalog | None = None,
        fetch_timeout: int = DEFAULT_TAXONOMY_FETCH_TIMEOUT_S,
    ) -> None:
        self._cache = cache or TaxonomyCache(fetch_timeout=fetch_timeout)
        self._catalog = catalog or XMLCatalog()
        self._package_loader = PackageLoader()

    def resolve(self, entry_points: list[str]) -> "TaxonomyModel":
        """Resolve entry points into a :class:`TaxonomyModel`.

        DTS Algorithm (XBRL 2.1 §3):
        1. Initialise *visited* set and queue with entry points.
        2. While the queue is non-empty, dequeue a URL.
        3. Skip if already visited.
        4. Resolve through the catalog, fetch via cache.
        5. If ``.xsd`` → parse schema, extract concepts and follow
           ``import``, ``include``, and ``linkbaseRef`` references.
        6. If ``.xml`` → parse as linkbase.

        Args:
            entry_points: List of schema/linkbase URLs.

        Returns:
            A fully-populated :class:`TaxonomyModel`.
        """
        from src.core.model.xbrl_model import (
            ArcModel,
            ConceptDefinition,
            LinkbaseModel,
            TaxonomyModel,
        )

        taxonomy = TaxonomyModel()
        visited: set[str] = set()
        queue: deque[str] = deque(entry_points)

        while queue:
            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            resolved_url = self._catalog.resolve(url)
            try:
                content = self._cache.get_or_fetch(resolved_url)
            except TaxonomyResolutionError:
                logger.warning("Cannot fetch taxonomy resource: %s", url)
                continue

            lower_url = url.lower()
            try:
                if lower_url.endswith(".xsd"):
                    concepts, refs = self._parse_schema(content, url)
                    for concept in concepts:
                        taxonomy.concepts[concept.qname] = concept
                    for ref_url in refs:
                        if ref_url not in visited:
                            queue.append(ref_url)
                elif lower_url.endswith(".xml"):
                    self._parse_linkbase(content, url, taxonomy)
                else:
                    # Try as schema first, then linkbase
                    concepts, refs = self._parse_schema(content, url)
                    for concept in concepts:
                        taxonomy.concepts[concept.qname] = concept
                    for ref_url in refs:
                        if ref_url not in visited:
                            queue.append(ref_url)
            except etree.XMLSyntaxError as exc:
                logger.warning("XML parse error in %s: %s", url, exc)

        logger.info(
            "DTS resolved: %d concepts, %d calc linkbases, "
            "%d pres linkbases, %d def linkbases",
            len(taxonomy.concepts),
            len(taxonomy.calculation_linkbases),
            len(taxonomy.presentation_linkbases),
            len(taxonomy.definition_linkbases),
        )
        return taxonomy

    def load_package(self, zip_path: str) -> TaxonomyPackage:
        """Load taxonomy from package ZIP.

        Args:
            zip_path: Path to the taxonomy package ZIP file.

        Returns:
            The loaded :class:`TaxonomyPackage`.
        """
        package = self._package_loader.load(zip_path)
        # Register URI mappings in the catalog
        for uri, internal in package.uri_mappings.items():
            self._catalog.add_mapping(uri, internal)
        return package

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    def _parse_schema(
        self, content: bytes, url: str
    ) -> tuple[list[Any], list[str]]:
        """Parse XSD schema, extract concepts and references to follow.

        Args:
            content: Raw XML bytes of the schema.
            url: Source URL (used for resolving relative references).

        Returns:
            Tuple of (list of ConceptDefinition, list of URLs to follow).
        """
        from src.core.model.xbrl_model import ConceptDefinition

        parser = etree.XMLParser(
            resolve_entities=False, no_network=True, dtd_validation=False
        )
        root = etree.fromstring(content, parser)  # noqa: S320

        target_ns = root.get("targetNamespace", "")
        concepts: list[ConceptDefinition] = []
        refs_to_follow: list[str] = []

        base_url = url.rsplit("/", 1)[0] + "/" if "/" in url else ""

        # Collect namespace prefixes
        for prefix, ns_uri in (root.nsmap or {}).items():
            if prefix and ns_uri:
                pass  # taxonomy.namespaces populated at caller level

        for elem in root.iter():
            tag = etree.QName(elem.tag).localname if isinstance(elem.tag, str) else None
            ns = etree.QName(elem.tag).namespace if isinstance(elem.tag, str) else None
            if tag is None:
                continue

            # Extract concepts from xs:element declarations
            if tag == "element" and ns == NS_XSD:
                concept = self._extract_concept(elem, target_ns)
                if concept is not None:
                    concepts.append(concept)

            # Follow xs:import
            elif tag == "import" and ns == NS_XSD:
                schema_loc = elem.get("schemaLocation", "")
                if schema_loc:
                    refs_to_follow.append(self._resolve_href(schema_loc, base_url))

            # Follow xs:include
            elif tag == "include" and ns == NS_XSD:
                schema_loc = elem.get("schemaLocation", "")
                if schema_loc:
                    refs_to_follow.append(self._resolve_href(schema_loc, base_url))

            # Follow link:linkbaseRef
            elif tag == "linkbaseRef":
                href = elem.get(f"{{{NS_XLINK}}}href", "")
                if href:
                    refs_to_follow.append(self._resolve_href(href, base_url))

            # Follow appinfo linkbaseRef
            elif tag == "linkbaseRef" or (
                tag == "linkbaseRef"
                and ns == NS_LINK
            ):
                href = elem.get(f"{{{NS_XLINK}}}href", elem.get("href", ""))
                if href:
                    refs_to_follow.append(self._resolve_href(href, base_url))

        return concepts, refs_to_follow

    def _parse_linkbase(
        self,
        content: bytes,
        url: str,
        taxonomy: Optional[Any] = None,
    ) -> None:
        """Parse linkbase XML, extract arcs and store in taxonomy model.

        Args:
            content: Raw XML bytes of the linkbase.
            url: Source URL of the linkbase.
            taxonomy: TaxonomyModel to populate (if provided).
        """
        from src.core.model.xbrl_model import ArcModel, LinkbaseModel

        if taxonomy is None:
            return

        parser = etree.XMLParser(
            resolve_entities=False, no_network=True, dtd_validation=False
        )
        root = etree.fromstring(content, parser)  # noqa: S320

        for extended_link in root.iter():
            el_tag = (
                etree.QName(extended_link.tag).localname
                if isinstance(extended_link.tag, str)
                else None
            )
            if el_tag is None:
                continue

            # Determine linkbase type from extended link element name
            lb_type: LinkbaseType | None = _ROLE_HINT_TO_TYPE.get(el_tag)
            if lb_type is None:
                continue

            role_uri = extended_link.get(f"{{{NS_XLINK}}}role", "")

            # Build locator map: label → href
            locators: dict[str, str] = {}
            for loc in extended_link.iter():
                loc_tag = (
                    etree.QName(loc.tag).localname
                    if isinstance(loc.tag, str)
                    else None
                )
                if loc_tag == "loc":
                    label = loc.get(f"{{{NS_XLINK}}}label", "")
                    href = loc.get(f"{{{NS_XLINK}}}href", "")
                    if label and href:
                        # Extract concept QName from href fragment
                        if "#" in href:
                            locators[label] = href.split("#", 1)[1]
                        else:
                            locators[label] = href

            # Extract arcs
            arcs: list[ArcModel] = []
            for arc_elem in extended_link.iter():
                arc_tag = (
                    etree.QName(arc_elem.tag).localname
                    if isinstance(arc_elem.tag, str)
                    else None
                )
                if arc_tag is None or "Arc" not in arc_tag:
                    continue

                arcrole = arc_elem.get(f"{{{NS_XLINK}}}arcrole", "")
                from_label = arc_elem.get(f"{{{NS_XLINK}}}from", "")
                to_label = arc_elem.get(f"{{{NS_XLINK}}}to", "")
                order_str = arc_elem.get("order", "1.0")
                weight_str = arc_elem.get("weight")
                priority_str = arc_elem.get("priority", "0")
                use = arc_elem.get("use", "optional")
                pref_label = arc_elem.get("preferredLabel")

                from_concept = locators.get(from_label, from_label)
                to_concept = locators.get(to_label, to_label)

                try:
                    order = float(order_str)
                except (ValueError, TypeError):
                    order = 1.0

                weight: Decimal | None = None
                if weight_str is not None:
                    try:
                        weight = Decimal(weight_str)
                    except Exception:
                        weight = None

                try:
                    priority = int(priority_str)
                except (ValueError, TypeError):
                    priority = 0

                arcs.append(
                    ArcModel(
                        arc_type=arc_tag,
                        arcrole=arcrole,
                        from_concept=from_concept,
                        to_concept=to_concept,
                        order=order,
                        weight=weight,
                        priority=priority,
                        use=use,
                        preferred_label=pref_label,
                    )
                )

                # Detect dimension defaults
                if arcrole == ARCROLE_DIMENSION_DEFAULT:
                    taxonomy.dimension_defaults[from_concept] = to_concept

            if arcs:
                linkbase = LinkbaseModel(
                    linkbase_type=lb_type,
                    role_uri=role_uri,
                    arcs=arcs,
                )
                if lb_type == LinkbaseType.CALCULATION:
                    taxonomy.calculation_linkbases.append(linkbase)
                elif lb_type == LinkbaseType.PRESENTATION:
                    taxonomy.presentation_linkbases.append(linkbase)
                elif lb_type == LinkbaseType.DEFINITION:
                    taxonomy.definition_linkbases.append(linkbase)
                elif lb_type == LinkbaseType.LABEL:
                    taxonomy.label_linkbases.append(linkbase)
                elif lb_type == LinkbaseType.REFERENCE:
                    taxonomy.reference_linkbases.append(linkbase)

    def _extract_concept(
        self, element: Any, target_ns: str
    ) -> Optional[Any]:
        """Extract concept definition from an ``<xs:element>`` tag.

        Args:
            element: lxml element representing ``<xs:element>``.
            target_ns: Target namespace of the containing schema.

        Returns:
            A :class:`ConceptDefinition` or ``None`` if the element
            is not a concept declaration.
        """
        from src.core.model.xbrl_model import ConceptDefinition

        name = element.get("name")
        if not name:
            return None

        subst_group = element.get("substitutionGroup", "")
        # Only elements with a substitution group in the XBRL family
        # are concepts (items or tuples).
        if not subst_group:
            return None

        qname = f"{{{target_ns}}}{name}" if target_ns else name
        data_type = element.get("type", "")
        abstract = element.get("abstract", "false").lower() == "true"
        nillable = element.get("nillable", "false").lower() == "true"

        period_type_str = element.get(
            f"{{{NS_XBRLI}}}periodType",
            element.get("periodType", ""),
        )
        period_type: PeriodType | None = None
        if period_type_str:
            try:
                period_type = PeriodType(period_type_str.lower())
            except ValueError:
                pass

        balance_type_str = element.get(
            f"{{{NS_XBRLI}}}balance",
            element.get("balance", ""),
        )
        balance_type: BalanceType | None = None
        if balance_type_str:
            try:
                balance_type = BalanceType(balance_type_str.lower())
            except ValueError:
                pass

        # Determine if numeric
        type_local = data_type.split(":")[-1] if ":" in data_type else data_type
        type_is_numeric = type_local in _NUMERIC_TYPES
        type_is_textblock = "textBlock" in data_type
        type_is_enum = "enum" in data_type.lower()

        return ConceptDefinition(
            qname=qname,
            namespace=target_ns,
            local_name=name,
            data_type=data_type,
            period_type=period_type,
            balance_type=balance_type,
            abstract=abstract,
            nillable=nillable,
            substitution_group=subst_group,
            type_is_numeric=type_is_numeric,
            type_is_textblock=type_is_textblock,
            type_is_enum=type_is_enum,
        )

    @staticmethod
    def _resolve_href(href: str, base_url: str) -> str:
        """Resolve a possibly-relative href against a base URL.

        Args:
            href: The href attribute value.
            base_url: Base URL (directory portion of the parent document).

        Returns:
            Absolute URL.
        """
        if href.startswith(("http://", "https://", "file://")):
            return href
        # Strip fragment identifier for resolution
        href_no_frag = href.split("#", 1)[0] if "#" in href else href
        if not href_no_frag:
            return base_url
        return base_url + href_no_frag
