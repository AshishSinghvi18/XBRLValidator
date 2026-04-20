"""Unified fact store with transparent in-memory → disk spill transition.

``FactStore`` wraps ``InMemoryFactIndex`` and ``DiskSpilledFactIndex`` behind
one stable interface.  When the in-memory index reaches its spill threshold
the store automatically creates a SQLite-backed index, transfers all existing
facts, frees the in-memory structures, and switches to disk mode for all
subsequent operations.
"""

from __future__ import annotations

import logging
from typing import Iterator, Optional

from src.core.constants import DEFAULT_FACT_INDEX_SPILL_THRESHOLD
from src.core.parser.streaming.disk_spill import DiskSpilledFactIndex
from src.core.parser.streaming.fact_index import (
    FactReference,
    InMemoryFactIndex,
)
from src.core.parser.streaming.memory_budget import MemoryBudget
from src.core.types import ContextID, QName, SpillState, UnitID

logger = logging.getLogger(__name__)


class FactStore:
    """Facade that transparently switches between in-memory and disk storage.

    Parameters
    ----------
    budget:
        Pipeline-wide memory budget for accounting.
    spill_threshold:
        Number of facts that triggers a transition to disk.
    db_path:
        Optional explicit path for the SQLite spill database.  If
        ``None`` a temporary file is used.
    """

    def __init__(
        self,
        budget: MemoryBudget,
        spill_threshold: int = DEFAULT_FACT_INDEX_SPILL_THRESHOLD,
        db_path: Optional[str] = None,
    ) -> None:
        self._budget: MemoryBudget = budget
        self._spill_threshold: int = spill_threshold
        self._db_path: Optional[str] = db_path
        self._mode: SpillState = SpillState.IN_MEMORY

        self._mem_index: Optional[InMemoryFactIndex] = InMemoryFactIndex(
            budget, spill_threshold
        )
        self._disk_index: Optional[DiskSpilledFactIndex] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def storage_mode(self) -> SpillState:
        """Current storage backend mode."""
        return self._mode

    @property
    def count(self) -> int:
        """Total number of facts stored."""
        if self._mode == SpillState.ON_DISK:
            assert self._disk_index is not None
            return self._disk_index.count
        assert self._mem_index is not None
        return self._mem_index.count

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, ref: FactReference) -> None:
        """Add a ``FactReference``, spilling to disk if necessary.

        The transition is performed once: on the first call where the
        in-memory index signals ``should_spill``, all existing facts are
        bulk-transferred to a new ``DiskSpilledFactIndex`` and the
        in-memory structures are released.
        """
        if self._mode == SpillState.IN_MEMORY:
            assert self._mem_index is not None
            ok = self._mem_index.add(ref)
            if not ok or self._mem_index.should_spill:
                self._spill_to_disk(ref if not ok else None)
            return

        # Already on disk
        assert self._disk_index is not None
        self._disk_index.add(ref)

    def _spill_to_disk(self, pending: Optional[FactReference]) -> None:
        """Transfer all in-memory facts to a new ``DiskSpilledFactIndex``."""
        assert self._mem_index is not None
        self._mode = SpillState.SPILLING
        logger.warning(
            "Spilling %s facts to disk (threshold %s)",
            self._mem_index.count,
            self._spill_threshold,
        )
        self._budget.request_spill(InMemoryFactIndex._COMPONENT_NAME)

        self._disk_index = DiskSpilledFactIndex(db_path=self._db_path)

        # Bulk transfer in batches
        for batch in self._mem_index.iter_batches(batch_size=10_000):
            self._disk_index.add_batch(batch)

        # Insert the pending fact that triggered the spill (if any)
        if pending is not None:
            self._disk_index.add(pending)

        # Free in-memory structures
        freed = self._mem_index.count
        self._budget.record_deallocation(
            InMemoryFactIndex._COMPONENT_NAME,
            sum(r.estimated_memory_bytes for r in self._mem_index.iter_all()),
        )
        self._mem_index = None
        self._mode = SpillState.ON_DISK
        logger.info("Spill complete – %s facts now on disk", freed)

    # ------------------------------------------------------------------
    # Query helpers (delegate to active backend)
    # ------------------------------------------------------------------

    def _active(self) -> InMemoryFactIndex | DiskSpilledFactIndex:
        if self._mode == SpillState.ON_DISK:
            assert self._disk_index is not None
            return self._disk_index
        assert self._mem_index is not None
        return self._mem_index

    def get_by_concept(self, concept: QName) -> list[FactReference]:
        """Return all facts matching the given *concept*."""
        return self._active().get_by_concept(concept)

    def get_by_context(self, ctx_id: ContextID) -> list[FactReference]:
        """Return all facts matching the given *context id*."""
        return self._active().get_by_context(ctx_id)

    def get_by_unit(self, unit_id: UnitID) -> list[FactReference]:
        """Return all facts matching the given *unit id*."""
        return self._active().get_by_unit(unit_id)

    def get_by_concept_and_context(
        self, concept: QName, ctx_id: ContextID
    ) -> list[FactReference]:
        """Return all facts matching both *concept* and *context id*."""
        return self._active().get_by_concept_and_context(concept, ctx_id)

    def get_duplicate_groups(self) -> dict[tuple, list[FactReference]]:
        """Return groups sharing (concept, context, unit) with >1 member."""
        return self._active().get_duplicate_groups()

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def iter_all(self) -> Iterator[FactReference]:
        """Iterate over every stored ``FactReference``."""
        yield from self._active().iter_all()

    def iter_batches(
        self, batch_size: int = 10_000
    ) -> Iterator[list[FactReference]]:
        """Yield successive batches of ``FactReference`` objects."""
        yield from self._active().iter_batches(batch_size)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release resources held by the active backend."""
        if self._disk_index is not None:
            self._disk_index.close()
            self._disk_index = None
        self._mem_index = None
