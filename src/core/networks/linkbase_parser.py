"""Linkbase document parser — XBRL 2.1 §5.2.

Parses linkbase XML documents into :class:`Arc` objects.  Handles
calculation, presentation, definition, label, and reference linkbases.

References:
    - XBRL 2.1 §3.5.3   (Extended links)
    - XBRL 2.1 §3.5.3.9 (Arc element)
    - XBRL 2.1 §5.2      (Linkbases)
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from lxml import etree

from src.core.constants import NS_LINK, NS_XLINK
from src.core.exceptions import TaxonomyResolutionError
from src.core.networks.relationship import Arc
from src.security.xxe_guard import XXEGuard

logger = logging.getLogger(__name__)

# Pre-computed Clark-notation tag/attribute names
_XLINK_TYPE = f"{{{NS_XLINK}}}type"
_XLINK_HREF = f"{{{NS_XLINK}}}href"
_XLINK_LABEL = f"{{{NS_XLINK}}}label"
_XLINK_FROM = f"{{{NS_XLINK}}}from"
_XLINK_TO = f"{{{NS_XLINK}}}to"
_XLINK_ARCROLE = f"{{{NS_XLINK}}}arcrole"
_XLINK_ROLE = f"{{{NS_XLINK}}}role"

# Extended link element tags (all standard linkbase types)
_EXTENDED_LINK_TAGS: frozenset[str] = frozenset(
    {
        f"{{{NS_LINK}}}calculationLink",
        f"{{{NS_LINK}}}presentationLink",
        f"{{{NS_LINK}}}definitionLink",
        f"{{{NS_LINK}}}labelLink",
        f"{{{NS_LINK}}}referenceLink",
    }
)

# Arc element tags
_ARC_TAGS: frozenset[str] = frozenset(
    {
        f"{{{NS_LINK}}}calculationArc",
        f"{{{NS_LINK}}}presentationArc",
        f"{{{NS_LINK}}}definitionArc",
        f"{{{NS_LINK}}}labelArc",
        f"{{{NS_LINK}}}referenceArc",
    }
)

# Locator element tags
_LOC_TAG = f"{{{NS_LINK}}}loc"


class LinkbaseParser:
    """Parses linkbase XML documents into :class:`Arc` objects.

    Handles calculation, presentation, definition, label, and reference
    linkbases.  Uses safe XML parsing via :class:`XXEGuard`.

    Spec: XBRL 2.1 §5.2 (Linkbases)
    """

    def __init__(self) -> None:
        self._xxe_guard = XXEGuard()

    def parse(self, xml_bytes: bytes, linkbase_url: str) -> list[Arc]:
        """Parse a linkbase document and extract all arcs.

        Args:
            xml_bytes:    Raw XML content of the linkbase.
            linkbase_url: URL of the linkbase (for error reporting).

        Returns:
            List of :class:`Arc` objects extracted from the linkbase.

        Raises:
            TaxonomyResolutionError: If the XML cannot be parsed.
        """
        try:
            root = self._xxe_guard.safe_fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            raise TaxonomyResolutionError(
                code="taxonomy:linkbaseXmlError",
                message=f"Malformed linkbase XML: {exc}",
                url=linkbase_url,
            ) from exc

        arcs: list[Arc] = []
        for elem in root.iter():
            if elem.tag in _EXTENDED_LINK_TAGS:
                arcs.extend(self._parse_extended_link(elem, linkbase_url))
        return arcs

    def _parse_extended_link(
        self,
        link_elem: etree._Element,
        linkbase_url: str,
    ) -> list[Arc]:
        """Parse a single extended link element.

        Builds a label → href mapping from locator elements, then
        converts each arc element into an :class:`Arc`.

        Args:
            link_elem:    The extended link XML element (e.g.
                          ``<link:calculationLink>``).
            linkbase_url: URL of the containing linkbase (for reporting).

        Returns:
            List of :class:`Arc` objects from this extended link.
        """
        role = link_elem.get(_XLINK_ROLE, "")

        # Build label → href map from loc elements
        label_to_href: dict[str, str] = {}
        for child in link_elem:
            if child.tag == _LOC_TAG:
                label = child.get(_XLINK_LABEL, "")
                href = child.get(_XLINK_HREF, "")
                if label and href:
                    label_to_href[label] = href

        # Parse arc elements
        arcs: list[Arc] = []
        for child in link_elem:
            if child.tag not in _ARC_TAGS:
                continue

            from_label = child.get(_XLINK_FROM, "")
            to_label = child.get(_XLINK_TO, "")
            arcrole = child.get(_XLINK_ARCROLE, "")

            if not from_label or not to_label or not arcrole:
                logger.debug(
                    "Skipping arc with missing from/to/arcrole in %s",
                    linkbase_url,
                )
                continue

            from_href = label_to_href.get(from_label, from_label)
            to_href = label_to_href.get(to_label, to_label)

            # Resolve locator hrefs to concept QNames.
            # Hrefs may be in the form "schema.xsd#elementName" — extract
            # the fragment as the concept identifier.
            from_qname = self._href_to_qname(from_href)
            to_qname = self._href_to_qname(to_href)

            # Parse numeric attributes
            order = self._parse_decimal(child.get("order", "1"))
            weight_str = child.get("weight")
            weight = self._parse_decimal(weight_str) if weight_str is not None else None
            priority = int(child.get("priority", "0"))
            use = child.get("use", "optional")

            arc = Arc(
                from_qname=from_qname,
                to_qname=to_qname,
                arcrole=arcrole,
                role=role,
                order=order,
                weight=weight,
                priority=priority,
                use=use,
            )
            arcs.append(arc)

        return arcs

    @staticmethod
    def _href_to_qname(href: str) -> str:
        """Convert a locator href to a concept identifier.

        If the href contains a fragment (``#``), the fragment is used
        as the concept name.  Otherwise the full href is returned.

        Args:
            href: Locator href value (e.g. ``"schema.xsd#Assets"``).

        Returns:
            The concept identifier (fragment or full href).
        """
        if "#" in href:
            return href.rsplit("#", maxsplit=1)[1]
        return href

    @staticmethod
    def _parse_decimal(value: str) -> Decimal:
        """Parse a string as :class:`Decimal`, defaulting to ``0``.

        Args:
            value: String representation of a decimal number.

        Returns:
            Parsed :class:`Decimal` value, or ``Decimal(0)`` on failure.
        """
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError):
            return Decimal(0)
