"""In-memory fact index for streaming XBRL parser.

``FactReference`` is a lightweight descriptor that records where a fact lives
inside the source file (byte offset + length) together with just enough
metadata to drive validation lookups.  ``InMemoryFactIndex`` maintains
secondary indices so that common access patterns (by concept, by context,
duplicates) are O(1) dict lookups rather than full scans.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterator, Optional

from src.core.constants import DEFAULT_FACT_INDEX_SPILL_THRESHOLD
from src.core.parser.streaming.memory_budget import MemoryBudget
from src.core.types import (
    BalanceType,
    ByteOffset,
    ContextID,
    FactID,
    PeriodType,
    QName,
    UnitID,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FactReference:
    """Lightweight reference to a parsed XBRL fact.

    Rather than materialising the full fact value in memory, we store
    the byte offset and length so the value can be read on demand via
    ``MMapReader`` or ``ChunkedReader``.
    """

    index: int
    concept: QName
    context_ref: ContextID
    unit_ref: Optional[UnitID]
    byte_offset: ByteOffset
    value_length: int
    is_numeric: bool
    is_nil: bool
    decimals: Optional[str] = None
    precision: Optional[str] = None
    id: Optional[FactID] = None
    source_line: int = 0
    period_type: Optional[PeriodType] = None
    balance_type: Optional[BalanceType] = None

    @property
    def estimated_memory_bytes(self) -> int:
        """Rough estimate of how many bytes this reference occupies in memory.

        ~200 bytes for the object header + slots overhead, plus the
        lengths of the variable-size string fields.
        """
        return 200 + sum(
            len(s)
            for s in (
                self.concept,
                self.context_ref,
                self.unit_ref or "",
                self.decimals or "",
                self.precision or "",
                self.id or "",
            )
        )


class InMemoryFactIndex:
    """Fast in-memory index over ``FactReference`` objects.

    Secondary indices map concept / context / unit identifiers to
    integer positions in the master ``_facts`` list so that no object
    is duplicated.

    Parameters
    ----------
    budget:
        The pipeline-wide memory budget to report allocations to.
    spill_threshold:
        Maximum number of facts before the index signals a spill.
    """

    _COMPONENT_NAME = "fact_index"

    def __init__(
        self,
        budget: MemoryBudget,
        spill_threshold: int = DEFAULT_FACT_INDEX_SPILL_THRESHOLD,
    ) -> None:
        self._budget: MemoryBudget = budget
        self._spill_threshold: int = spill_threshold

        self._facts: list[FactReference] = []
        self._by_concept: dict[QName, list[int]] = defaultdict(list)
        self._by_context: dict[ContextID, list[int]] = defaultdict(list)
        self._by_unit: dict[UnitID, list[int]] = defaultdict(list)
        self._by_cc: dict[tuple[QName, ContextID], list[int]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, ref: FactReference) -> bool:
        """Add a ``FactReference`` to the index.

        Returns ``False`` if the index has reached *spill_threshold* and
        the caller should transition to a disk-backed store.
        """
        if len(self._facts) >= self._spill_threshold:
            return False

        idx = len(self._facts)
        self._facts.append(ref)

        self._by_concept[ref.concept].append(idx)
        self._by_context[ref.context_ref].append(idx)
        if ref.unit_ref:
            self._by_unit[ref.unit_ref].append(idx)
        self._by_cc[(ref.concept, ref.context_ref)].append(idx)

        mem = ref.estimated_memory_bytes
        self._budget.record_allocation(self._COMPONENT_NAME, mem)

        return True

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        """Number of facts currently stored."""
        return len(self._facts)

    @property
    def should_spill(self) -> bool:
        """``True`` when the number of facts has reached *spill_threshold*."""
        return len(self._facts) >= self._spill_threshold

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def get_by_concept(self, concept: QName) -> list[FactReference]:
        """Return all facts that match the given *concept*."""
        return [self._facts[i] for i in self._by_concept.get(concept, [])]

    def get_by_context(self, ctx_id: ContextID) -> list[FactReference]:
        """Return all facts that match the given *context id*."""
        return [self._facts[i] for i in self._by_context.get(ctx_id, [])]

    def get_by_unit(self, unit_id: UnitID) -> list[FactReference]:
        """Return all facts that match the given *unit id*."""
        return [self._facts[i] for i in self._by_unit.get(unit_id, [])]

    def get_by_concept_and_context(
        self, concept: QName, ctx_id: ContextID
    ) -> list[FactReference]:
        """Return all facts that match both *concept* and *context id*."""
        return [
            self._facts[i] for i in self._by_cc.get((concept, ctx_id), [])
        ]

    def get_duplicate_groups(self) -> dict[tuple, list[FactReference]]:
        """Return groups of facts that share the same (concept, context, unit).

        Only groups with more than one member are returned – i.e. actual
        duplicates.
        """
        groups: dict[tuple, list[FactReference]] = {}
        seen: dict[tuple, list[int]] = defaultdict(list)
        for idx, ref in enumerate(self._facts):
            key = (ref.concept, ref.context_ref, ref.unit_ref or "")
            seen[key].append(idx)
        for key, indices in seen.items():
            if len(indices) > 1:
                groups[key] = [self._facts[i] for i in indices]
        return groups

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def iter_all(self) -> Iterator[FactReference]:
        """Iterate over every stored ``FactReference``."""
        yield from self._facts

    def iter_batches(
        self, batch_size: int = 10_000
    ) -> Iterator[list[FactReference]]:
        """Yield successive batches of ``FactReference`` objects."""
        for start in range(0, len(self._facts), batch_size):
            yield self._facts[start : start + batch_size]
