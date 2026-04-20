"""Fact reference and in-memory fact index for streaming XBRL parsing.

Spec: XBRL 2.1 - streaming fact indexing for large files.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from decimal import Decimal
from typing import Dict, Iterator, List, Optional, Tuple

from src.core.types import BalanceType, PeriodType, QName, ContextID, UnitID, FactID, ByteOffset


@dataclasses.dataclass(frozen=True, slots=True)
class FactReference:
    """Lightweight reference to a fact in a source document.

    Designed for memory efficiency in streaming mode. Stores metadata
    and byte offset for on-demand value loading.
    """

    index: int
    concept: QName
    context_ref: ContextID
    unit_ref: Optional[UnitID] = None
    byte_offset: ByteOffset = 0
    value_length: int = 0
    value_preview: Optional[bytes] = None
    is_numeric: bool = False
    is_nil: bool = False
    is_tuple: bool = False
    decimals: Optional[str] = None
    precision: Optional[str] = None
    id: Optional[FactID] = None
    source_line: int = 0
    source_column: int = 0
    period_type: Optional[PeriodType] = None
    balance_type: Optional[BalanceType] = None
    language: Optional[str] = None
    parent_tuple_ref: Optional[int] = None

    @property
    def estimated_memory_bytes(self) -> int:
        """Estimate memory used by this reference (~240 bytes average)."""
        base = 160
        base += len(self.concept) if self.concept else 0
        base += len(self.context_ref) if self.context_ref else 0
        base += len(self.unit_ref) if self.unit_ref else 0
        base += len(self.id) if self.id else 0
        base += len(self.value_preview) if self.value_preview else 0
        return base


class InMemoryFactIndex:
    """In-memory index of FactReferences with multi-key lookup.

    Stores indices into the _facts list rather than duplicating references.
    Spills to DiskSpilledFactIndex when threshold is reached.
    """

    def __init__(self, spill_threshold: int = 5_000_000, spill_bytes: int = 500 * 1024 * 1024) -> None:
        self._facts: List[FactReference] = []
        self._by_concept: Dict[QName, List[int]] = defaultdict(list)
        self._by_context: Dict[ContextID, List[int]] = defaultdict(list)
        self._by_unit: Dict[UnitID, List[int]] = defaultdict(list)
        self._by_cc: Dict[Tuple[QName, ContextID], List[int]] = defaultdict(list)
        self._spill_threshold = spill_threshold
        self._spill_bytes = spill_bytes
        self._estimated_bytes = 0
        self._duplicate_groups_cache: Optional[Dict[Tuple[str, ...], List[int]]] = None

    @property
    def count(self) -> int:
        """Number of facts indexed."""
        return len(self._facts)

    @property
    def should_spill(self) -> bool:
        """Whether the index should spill to disk."""
        return self.count >= self._spill_threshold or self._estimated_bytes >= self._spill_bytes

    @property
    def estimated_bytes(self) -> int:
        """Estimated memory usage in bytes."""
        return self._estimated_bytes

    def add(self, ref: FactReference) -> bool:
        """Add a fact reference. Returns False if at spill threshold."""
        idx = len(self._facts)
        self._facts.append(ref)
        self._by_concept[ref.concept].append(idx)
        self._by_context[ref.context_ref].append(idx)
        if ref.unit_ref:
            self._by_unit[ref.unit_ref].append(idx)
        self._by_cc[(ref.concept, ref.context_ref)].append(idx)
        self._estimated_bytes += ref.estimated_memory_bytes + 80  # index overhead
        self._duplicate_groups_cache = None
        return not self.should_spill

    def add_batch(self, refs: List[FactReference]) -> int:
        """Add a batch of fact references. Returns count added."""
        for ref in refs:
            self.add(ref)
        return len(refs)

    def get(self, idx: int) -> FactReference:
        """Get fact reference by ordinal index."""
        return self._facts[idx]

    def get_by_concept(self, concept: QName) -> List[FactReference]:
        """Get all fact references for a concept."""
        return [self._facts[i] for i in self._by_concept.get(concept, [])]

    def get_by_context(self, ctx_id: ContextID) -> List[FactReference]:
        """Get all fact references for a context."""
        return [self._facts[i] for i in self._by_context.get(ctx_id, [])]

    def get_by_unit(self, unit_id: UnitID) -> List[FactReference]:
        """Get all fact references for a unit."""
        return [self._facts[i] for i in self._by_unit.get(unit_id, [])]

    def get_by_concept_and_context(self, concept: QName, ctx_id: ContextID) -> List[FactReference]:
        """Get fact references matching both concept and context."""
        return [self._facts[i] for i in self._by_cc.get((concept, ctx_id), [])]

    def get_duplicate_groups(self) -> Dict[Tuple[str, ...], List[FactReference]]:
        """Get groups of duplicate facts (same concept+context+unit+language)."""
        if self._duplicate_groups_cache is not None:
            return {k: [self._facts[i] for i in v] for k, v in self._duplicate_groups_cache.items()}

        groups: Dict[Tuple[str, ...], List[int]] = defaultdict(list)
        for idx, ref in enumerate(self._facts):
            key = (ref.concept, ref.context_ref, ref.unit_ref or "", ref.language or "")
            groups[key].append(idx)

        self._duplicate_groups_cache = {k: v for k, v in groups.items() if len(v) > 1}
        return {k: [self._facts[i] for i in v] for k, v in self._duplicate_groups_cache.items()}

    def get_tuple_children(self, parent_idx: int) -> List[FactReference]:
        """Get child facts of a tuple."""
        return [ref for ref in self._facts if ref.parent_tuple_ref == parent_idx]

    def iter_all(self) -> Iterator[FactReference]:
        """Iterate over all fact references."""
        return iter(self._facts)

    def iter_batches(self, batch_size: int = 10_000) -> Iterator[List[FactReference]]:
        """Iterate in batches of given size."""
        for i in range(0, len(self._facts), batch_size):
            yield self._facts[i : i + batch_size]

    def iter_by_concept(self) -> Iterator[Tuple[QName, List[FactReference]]]:
        """Iterate grouped by concept."""
        for concept, indices in self._by_concept.items():
            yield concept, [self._facts[i] for i in indices]
