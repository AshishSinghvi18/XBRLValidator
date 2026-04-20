"""iXBRL continuation chain resolver.

Resolves ``ix:continuation`` elements that split fact content across
multiple HTML elements. Chains are resolved by following
``continuedAt`` attributes to reconstruct the full text content.
"""

from __future__ import annotations

import structlog
from lxml import etree

from src.core.constants import DEFAULT_MAX_CONTINUATION_DEPTH, NS_IX
from src.core.exceptions import IXBRLParseError

logger = structlog.get_logger(__name__)


class ContinuationResolver:
    """Resolves ix:continuation chains in iXBRL documents.

    iXBRL allows fact content to be split across multiple HTML elements
    using ``ix:continuation`` elements linked via ``continuedAt`` attributes.
    This class follows those chains to reconstruct the complete text.
    """

    def __init__(
        self,
        max_depth: int = DEFAULT_MAX_CONTINUATION_DEPTH,
    ) -> None:
        self._max_depth = max_depth
        self._log = logger.bind(component="continuation_resolver")

    def resolve_all(
        self,
        root: etree._Element,
    ) -> dict[str, str]:
        """Resolve all continuation chains in the document.

        Builds a mapping from the originating element's ID to the
        fully reconstructed text content.

        Args:
            root: Root element of the iXBRL document.

        Returns:
            Dict mapping element IDs to their resolved text content.
        """
        # Build index of continuation elements by ID
        continuations: dict[str, etree._Element] = {}
        for elem in root.iter(f"{{{NS_IX}}}continuation"):
            cont_id = elem.get("id", "")
            if cont_id:
                continuations[cont_id] = elem

        self._log.debug(
            "continuation_index_built",
            count=len(continuations),
        )

        # Resolve chains for each element with continuedAt
        resolved: dict[str, str] = {}
        for elem in root.iter():
            continued_at = elem.get("continuedAt")
            if continued_at is not None:
                elem_id = elem.get("id", "")
                base_text = self._get_element_text(elem)
                chain_text = self._follow_chain(
                    continued_at, continuations, set()
                )
                full_text = base_text + chain_text
                if elem_id:
                    resolved[elem_id] = full_text
                # Also store by continuedAt for lookup
                resolved[f"__chain_{continued_at}"] = full_text

        self._log.info(
            "continuation_resolve_complete",
            resolved_count=len(resolved),
        )
        return resolved

    def resolve_element(
        self,
        elem: etree._Element,
        continuations: dict[str, etree._Element],
    ) -> str:
        """Resolve the complete text for a single element.

        Args:
            elem: The element whose continuation chain to resolve.
            continuations: Index of continuation elements by ID.

        Returns:
            The fully resolved text content.
        """
        base_text = self._get_element_text(elem)
        continued_at = elem.get("continuedAt")
        if continued_at is None:
            return base_text

        chain_text = self._follow_chain(continued_at, continuations, set())
        return base_text + chain_text

    def _follow_chain(
        self,
        continuation_id: str,
        continuations: dict[str, etree._Element],
        visited: set[str],
    ) -> str:
        """Follow a continuation chain recursively.

        Guards against cycles and excessive depth.

        Args:
            continuation_id: ID of the next continuation element.
            continuations: Index of all continuation elements.
            visited: Set of already-visited IDs (cycle detection).

        Returns:
            Concatenated text from the continuation chain.

        Raises:
            IXBRLParseError: If a cycle is detected or max depth is exceeded.
        """
        if len(visited) >= self._max_depth:
            raise IXBRLParseError(
                message=f"Continuation chain depth exceeds maximum ({self._max_depth})",
                code="IXBRL-0010",
            )

        if continuation_id in visited:
            raise IXBRLParseError(
                message=f"Circular continuation chain detected at id='{continuation_id}'",
                code="IXBRL-0011",
            )

        elem = continuations.get(continuation_id)
        if elem is None:
            self._log.warning(
                "continuation_missing",
                continuation_id=continuation_id,
            )
            return ""

        visited.add(continuation_id)
        text = self._get_element_text(elem)

        # Check for further continuation
        next_id = elem.get("continuedAt")
        if next_id is not None:
            text += self._follow_chain(next_id, continuations, visited)

        return text

    def _get_element_text(self, elem: etree._Element) -> str:
        """Get text content from an element, excluding ix:continuation children."""
        parts: list[str] = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            tag = child.tag if isinstance(child.tag, str) else ""
            # Skip continuation children — they are handled separately
            if tag == f"{{{NS_IX}}}continuation":
                if child.tail:
                    parts.append(child.tail)
                continue
            # Include other children's text
            parts.append("".join(child.itertext()))
            if child.tail:
                parts.append(child.tail)
        return "".join(parts)

    def build_continuation_index(
        self,
        root: etree._Element,
    ) -> dict[str, etree._Element]:
        """Build an index of all ix:continuation elements by ID.

        Args:
            root: Root element of the document.

        Returns:
            Dict mapping continuation IDs to their elements.
        """
        index: dict[str, etree._Element] = {}
        for elem in root.iter(f"{{{NS_IX}}}continuation"):
            cont_id = elem.get("id", "")
            if cont_id:
                index[cont_id] = elem
        return index
