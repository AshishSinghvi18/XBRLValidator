"""Fast concept lookup index for taxonomy concepts.

Provides O(1) lookups by QName, namespace, and type so that validation
rules can quickly locate and classify concepts without scanning the
full concept dictionary.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.model.xbrl_model import ConceptDefinition

from src.core.types import QName

logger = logging.getLogger(__name__)


class ConceptIndex:
    """Fast lookup index for taxonomy concepts.

    Provides O(1) lookups by QName, namespace, and type.

    The index is populated incrementally via :meth:`add` and supports
    bulk loading from a ``TaxonomyModel.concepts`` dictionary.
    """

    def __init__(self) -> None:
        self._by_qname: dict[QName, ConceptDefinition] = {}
        self._by_namespace: dict[str, list[ConceptDefinition]] = defaultdict(list)
        self._by_type: dict[str, list[ConceptDefinition]] = defaultdict(list)
        self._numeric_concepts: set[QName] = set()

    def add(self, concept: "ConceptDefinition") -> None:
        """Add a concept to the index.

        Args:
            concept: The concept definition to index.
        """
        self._by_qname[concept.qname] = concept
        self._by_namespace[concept.namespace].append(concept)
        if concept.data_type:
            self._by_type[concept.data_type].append(concept)
        if concept.type_is_numeric:
            self._numeric_concepts.add(concept.qname)

    def get(self, qname: QName) -> "ConceptDefinition | None":
        """Look up a concept by its QName.

        Args:
            qname: Qualified name in Clark notation or prefix:local form.

        Returns:
            The concept definition or ``None`` if not found.
        """
        return self._by_qname.get(qname)

    def get_by_namespace(self, namespace: str) -> list["ConceptDefinition"]:
        """Get all concepts in a namespace.

        Args:
            namespace: Namespace URI.

        Returns:
            List of concept definitions (may be empty).
        """
        return list(self._by_namespace.get(namespace, []))

    def get_by_type(self, data_type: str) -> list["ConceptDefinition"]:
        """Get all concepts with a given data type.

        Args:
            data_type: XSD type name.

        Returns:
            List of concept definitions (may be empty).
        """
        return list(self._by_type.get(data_type, []))

    def is_numeric(self, qname: QName) -> bool:
        """Check whether a concept is numeric.

        Args:
            qname: Concept QName.

        Returns:
            ``True`` if the concept has a numeric type.
        """
        return qname in self._numeric_concepts

    def is_known(self, qname: QName) -> bool:
        """Check whether a concept exists in the index.

        Args:
            qname: Concept QName.

        Returns:
            ``True`` if the concept is indexed.
        """
        return qname in self._by_qname

    def count(self) -> int:
        """Return the total number of indexed concepts."""
        return len(self._by_qname)

    def all_concepts(self) -> list["ConceptDefinition"]:
        """Return all indexed concepts.

        Returns:
            List of all concept definitions.
        """
        return list(self._by_qname.values())

    def build_from_taxonomy(self, concepts: dict[QName, "ConceptDefinition"]) -> None:
        """Bulk-load concepts from a taxonomy concepts dictionary.

        Args:
            concepts: Mapping of QName → ConceptDefinition.
        """
        for concept in concepts.values():
            self.add(concept)
        logger.info("ConceptIndex built: %d concepts indexed", self.count())
