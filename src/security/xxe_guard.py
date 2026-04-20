"""XXE (XML External Entity) guard for safe XML parsing.

Wraps lxml's XMLParser to enforce settings that prevent XXE injection,
entity-expansion bombs, and remote DTD loading.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from lxml import etree

from src.core.exceptions import XXEError


class XXEGuard:
    """Creates safe lxml XMLParser instances hardened against XXE attacks.

    All parsers produced by this guard enforce:
    - ``resolve_entities=False`` – blocks external entity resolution.
    - ``no_network=True``        – prevents network access during parsing.
    - ``dtd_validation=False``   – skips DTD validation (avoids remote DTD fetch).
    - ``load_dtd=False``         – does not load external DTDs at all.
    """

    def create_safe_parser(self, *, huge_tree: bool = False) -> etree.XMLParser:
        """Return an lxml XMLParser with XXE-safe defaults.

        Args:
            huge_tree: Allow very deep trees / long text content.  Set to
                ``True`` only when processing known-safe large filings.

        Returns:
            A hardened :class:`lxml.etree.XMLParser`.
        """
        return etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            dtd_validation=False,
            load_dtd=False,
            huge_tree=huge_tree,
        )

    def safe_parse(
        self,
        source: Union[str, bytes, Path],
        *,
        huge_tree: bool = False,
    ) -> etree._ElementTree:
        """Parse an XML document from *source* using a safe parser.

        Args:
            source: A file path (str/Path) or raw XML bytes.
            huge_tree: Passed through to :meth:`create_safe_parser`.

        Returns:
            The parsed :class:`lxml.etree._ElementTree`.

        Raises:
            XXEError: If the parsed tree contains external entity references.
            etree.XMLSyntaxError: If the XML is malformed.
        """
        parser = self.create_safe_parser(huge_tree=huge_tree)

        if isinstance(source, (str, Path)):
            tree = etree.parse(str(source), parser)  # noqa: S320
        elif isinstance(source, bytes):
            tree = etree.ElementTree(etree.fromstring(source, parser))  # noqa: S320
        else:
            raise TypeError(
                f"source must be str, Path, or bytes, got {type(source).__name__}"
            )

        self.check_for_xxe(tree)
        return tree

    def safe_fromstring(self, data: bytes) -> etree._Element:
        """Parse raw XML bytes into an Element, blocking XXE.

        Args:
            data: Raw XML bytes.

        Returns:
            The root :class:`lxml.etree._Element`.

        Raises:
            XXEError: If external entity references are detected.
        """
        parser = self.create_safe_parser()
        root = etree.fromstring(data, parser)  # noqa: S320
        tree = etree.ElementTree(root)
        self.check_for_xxe(tree)
        return root

    def check_for_xxe(self, tree: etree._ElementTree) -> None:
        """Inspect a parsed tree for residual external entity indicators.

        Even with ``resolve_entities=False``, a document may contain
        ``<!DOCTYPE>`` declarations that reference external URIs.  This
        method walks the tree's docinfo and elements looking for:

        * SYSTEM or PUBLIC identifiers in the DOCTYPE.
        * ``<!ENTITY …>`` declarations referencing files or URLs.
        * Processing instructions that hint at entity inclusion.

        Args:
            tree: A parsed XML tree.

        Raises:
            XXEError: If any external entity artefact is found.
        """
        docinfo = tree.docinfo
        if docinfo is not None:
            if docinfo.system_url:
                raise XXEError(
                    message=(
                        "DOCTYPE SYSTEM identifier references an external "
                        f"resource: {docinfo.system_url}"
                    ),
                    context={"system_url": docinfo.system_url},
                )
            if docinfo.public_id:
                raise XXEError(
                    message=(
                        "DOCTYPE PUBLIC identifier references an external "
                        f"resource: {docinfo.public_id}"
                    ),
                    context={"public_id": docinfo.public_id},
                )

        # Walk all elements; flag any entity-reference nodes that survived.
        root = tree.getroot()
        if root is None:
            return

        for element in root.iter():
            # lxml represents unresolved entity references as
            # _Entity nodes (tag is a callable `Entity`).
            if callable(element.tag):
                raise XXEError(
                    message="Unresolved entity reference found in document",
                    context={"entity": str(element)},
                )

            # Check for processing instructions that may load entities.
            if isinstance(element, etree._ProcessingInstruction):
                pi_text = (element.text or "").lower()
                if "entity" in pi_text or "include" in pi_text:
                    raise XXEError(
                        message=(
                            f"Suspicious processing instruction detected: "
                            f"<?{element.target} {element.text}?>"
                        ),
                        context={
                            "pi_target": element.target,
                            "pi_text": element.text,
                        },
                    )
