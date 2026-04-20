"""Unified fact store with transparent in-memory to disk-spill transition.

Spec: XBRL 2.1 streaming validation - automatic spill management.
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional, Tuple

import structlog

from src.core.parser.streaming.disk_spill import DiskSpilledFactIndex
from src.core.parser.streaming.fact_index import FactReference, InMemoryFactIndex
from src.core.parser.streaming.memory_budget import MemoryBudget
from src.core.types import SpillState, QName, ContextID, UnitID

logger = structlog.get_logger(__name__)


class FactStore:
    """Unified fact storage interface. Transparently switches from in-memory to disk-spilled.

    Auto-spill triggers when:
    - Fact count reaches spill_threshold (default 5M)
    - Memory budget pressure_ratio >= 0.85 (checked every 10K facts)
    """

    def __init__(
        self,
        budget: Optional[MemoryBudget] = None,
        spill_threshold: int = 5_000_000,
        spill_bytes: int = 500 * 1024 * 1024,
        force_mode: Optional[SpillState] = None,
    ) -> None:
        self._budget = budget
        self._mode = force_mode or SpillState.IN_MEMORY
        self._spill_threshold = spill_threshold
        self._spill_bytes = spill_bytes

        if self._mode == SpillState.ON_DISK:
            self._backend: InMemoryFactIndex | DiskSpilledFactIndex = DiskSpilledFactIndex()
        else:
            self._backend = InMemoryFactIndex(
                spill_threshold=spill_threshold, spill_bytes=spill_bytes
            )

    @property
    def storage_mode(self) -> SpillState:
        """Current storage mode."""
        return self._mode

    @property
    def count(self) -> int:
        """Number of facts stored."""
        return self._backend.count

    def add(self, ref: FactReference) -> None:
        """Add a fact reference, auto-spilling if needed."""
        self._backend.add(ref)

        if self._mode == SpillState.IN_MEMORY:
            count = self._backend.count
            if count >= self._spill_threshold:
                self._spill()
            elif count % 10_000 == 0 and self._budget is not None:
                if self._budget.pressure_ratio() >= 0.85:
                    self._spill()

    def _spill(self) -> None:
        """Transfer all in-memory facts to disk-backed SQLite store."""
        if self._mode != SpillState.IN_MEMORY:
            return
        if not isinstance(self._backend, InMemoryFactIndex):
            return

        logger.info("fact_store.spilling", fact_count=self._backend.count)
        self._mode = SpillState.SPILLING

        disk_index = DiskSpilledFactIndex()
        for batch in self._backend.iter_batches(10_000):
            disk_index.add_batch(batch)

        self._backend = disk_index
        self._mode = SpillState.ON_DISK
        logger.info("fact_store.spilled", fact_count=disk_index.count)

    def get(self, idx: int) -> FactReference:
        """Get fact reference by ordinal index."""
        return self._backend.get(idx)

    def get_by_concept(self, concept: QName) -> List[FactReference]:
        """Get all fact references for a concept."""
        return self._backend.get_by_concept(concept)

    def get_by_context(self, ctx_id: ContextID) -> List[FactReference]:
        """Get all fact references for a context."""
        return self._backend.get_by_context(ctx_id)

    def get_by_unit(self, unit_id: UnitID) -> List[FactReference]:
        """Get all fact references for a unit."""
        return self._backend.get_by_unit(unit_id)

    def get_by_concept_and_context(self, concept: QName, ctx_id: ContextID) -> List[FactReference]:
        """Get fact references matching both concept and context."""
        return self._backend.get_by_concept_and_context(concept, ctx_id)

    def get_duplicate_groups(self) -> Dict[Tuple[str, ...], List[FactReference]]:
        """Get groups of duplicate facts."""
        return self._backend.get_duplicate_groups()

    def get_tuple_children(self, parent_idx: int) -> List[FactReference]:
        """Get child facts of a tuple."""
        return self._backend.get_tuple_children(parent_idx)

    def iter_all(self) -> Iterator[FactReference]:
        """Iterate over all fact references."""
        return self._backend.iter_all()

    def iter_batches(self, batch_size: int = 10_000) -> Iterator[List[FactReference]]:
        """Iterate in batches."""
        return self._backend.iter_batches(batch_size)

    def iter_by_concept(self) -> Iterator[Tuple[QName, List[FactReference]]]:
        """Iterate grouped by concept."""
        return self._backend.iter_by_concept()

    def close(self) -> None:
        """Close and clean up resources."""
        if isinstance(self._backend, DiskSpilledFactIndex):
            self._backend.close()
