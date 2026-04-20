"""Additional indexing utilities for the XBRL model.

Provides secondary indexes on top of :class:`XBRLInstance` for efficient
queries such as dimensional fact lookup, duplicate detection, and
orphaned context/unit identification.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from src.core.types import ContextID, DimensionKey, UnitID

if TYPE_CHECKING:
    from src.core.model.xbrl_model import Fact, XBRLInstance

logger = logging.getLogger(__name__)


class ModelIndexes:
    """Additional indexes for efficient model queries.

    Built on top of a fully-populated :class:`XBRLInstance`.

    Attributes:
        _instance: The instance being indexed.
        _dimensional_facts: Dimension key → facts mapping.
        _duplicate_groups: Duplicate key → facts mapping.
    """

    def __init__(self, instance: "XBRLInstance") -> None:
        self._instance = instance
        self._dimensional_facts: dict[DimensionKey, list["Fact"]] = defaultdict(list)
        self._duplicate_groups: dict[tuple, list["Fact"]] = defaultdict(list)

    def build(self) -> None:
        """Build all secondary indexes.

        Iterates over all facts and their associated contexts to
        populate dimensional and duplicate-detection indexes.
        """
        self._dimensional_facts.clear()
        self._duplicate_groups.clear()

        for fact in self._instance.facts:
            # Duplicate detection index
            self._duplicate_groups[fact.duplicate_key].append(fact)

            # Dimensional index
            ctx = fact.context
            if ctx is None:
                ctx = self._instance.contexts.get(fact.context_ref)
            if ctx is not None:
                dim_key = ctx.dimension_key
                if dim_key:
                    self._dimensional_facts[dim_key].append(fact)

        logger.debug(
            "Secondary indexes built: %d dimensional keys, %d duplicate groups",
            len(self._dimensional_facts),
            len(self._duplicate_groups),
        )

    def get_dimensional_facts(self, dim_key: DimensionKey) -> list["Fact"]:
        """Get all facts sharing a dimensional combination.

        Args:
            dim_key: The dimension key tuple.

        Returns:
            List of facts with matching dimensions (may be empty).
        """
        return list(self._dimensional_facts.get(dim_key, []))

    def get_duplicate_groups(self) -> dict[tuple, list["Fact"]]:
        """Get all groups of potentially duplicate facts.

        A group contains two or more facts with the same
        ``(concept, context_ref, unit_ref, language)`` key.

        Returns:
            Dict mapping duplicate keys to lists of facts.
            Only groups with ≥ 2 facts are returned.
        """
        return {
            key: facts
            for key, facts in self._duplicate_groups.items()
            if len(facts) >= 2
        }

    def get_orphaned_contexts(self) -> list[ContextID]:
        """Find context IDs not referenced by any fact.

        Returns:
            List of orphaned context IDs.
        """
        referenced: set[ContextID] = {f.context_ref for f in self._instance.facts}
        return [
            cid for cid in self._instance.contexts if cid not in referenced
        ]

    def get_orphaned_units(self) -> list[UnitID]:
        """Find unit IDs not referenced by any fact.

        Returns:
            List of orphaned unit IDs.
        """
        referenced: set[UnitID] = set()
        for f in self._instance.facts:
            if f.unit_ref:
                referenced.add(f.unit_ref)
        return [
            uid for uid in self._instance.units if uid not in referenced
        ]
