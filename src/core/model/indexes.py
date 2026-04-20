"""Fact indexes for efficient lookups in DOM mode.

Provides multi-key indexing over facts by concept, context, unit,
period, and dimension values. Used by validation rules that need
fast cross-referencing of facts.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import structlog

from src.core.model.xbrl_model import Context, Fact, XBRLInstance
from src.core.types import ContextID, DimensionKey, QName, UnitID

logger = structlog.get_logger(__name__)


@dataclass
class FactIndex:
    """Multi-dimensional index over facts for efficient lookups."""

    by_concept: dict[QName, list[Fact]] = field(default_factory=lambda: defaultdict(list))
    by_context: dict[ContextID, list[Fact]] = field(default_factory=lambda: defaultdict(list))
    by_unit: dict[UnitID, list[Fact]] = field(default_factory=lambda: defaultdict(list))
    by_period_instant: dict[date, list[Fact]] = field(default_factory=lambda: defaultdict(list))
    by_dimension_key: dict[DimensionKey, list[Fact]] = field(default_factory=lambda: defaultdict(list))
    by_concept_and_context: dict[tuple[QName, ContextID], list[Fact]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _total_facts: int = 0

    @property
    def total_facts(self) -> int:
        return self._total_facts


class FactIndexBuilder:
    """Build a FactIndex from an XBRLInstance."""

    def __init__(self) -> None:
        self._log = logger.bind(component="fact_index_builder")

    def build(self, instance: XBRLInstance) -> FactIndex:
        """Build a comprehensive index over all facts in the instance."""
        self._log.info("index_build_start", fact_count=len(instance.facts))
        index = FactIndex()

        for fact in instance.facts:
            index.by_concept[fact.concept_qname].append(fact)

            if fact.context_ref is not None:
                index.by_context[fact.context_ref].append(fact)
                index.by_concept_and_context[
                    (fact.concept_qname, fact.context_ref)
                ].append(fact)

                ctx = instance.contexts.get(fact.context_ref)
                if ctx is not None:
                    if ctx.period.instant is not None:
                        index.by_period_instant[ctx.period.instant].append(fact)
                    dim_key = ctx.dimension_key
                    if dim_key:
                        index.by_dimension_key[dim_key].append(fact)

            if fact.unit_ref is not None:
                index.by_unit[fact.unit_ref].append(fact)

            index._total_facts += 1

        self._log.info(
            "index_build_complete",
            total=index.total_facts,
            concepts=len(index.by_concept),
            contexts=len(index.by_context),
        )
        return index


def query_facts(
    index: FactIndex,
    *,
    concept: QName | None = None,
    context_id: ContextID | None = None,
    unit_id: UnitID | None = None,
    period_instant: date | None = None,
    dimension_key: DimensionKey | None = None,
) -> list[Fact]:
    """Query the index with optional filters. All filters are AND-combined."""
    candidates: list[set[int]] = []

    if concept is not None:
        facts = index.by_concept.get(concept, [])
        candidates.append({id(f) for f in facts})
    if context_id is not None:
        facts = index.by_context.get(context_id, [])
        candidates.append({id(f) for f in facts})
    if unit_id is not None:
        facts = index.by_unit.get(unit_id, [])
        candidates.append({id(f) for f in facts})
    if period_instant is not None:
        facts = index.by_period_instant.get(period_instant, [])
        candidates.append({id(f) for f in facts})
    if dimension_key is not None:
        facts = index.by_dimension_key.get(dimension_key, [])
        candidates.append({id(f) for f in facts})

    if not candidates:
        return []

    result_ids = candidates[0]
    for s in candidates[1:]:
        result_ids &= s

    # Collect actual fact objects by concept (most common entry point)
    all_facts: list[Fact] = []
    if concept is not None:
        all_facts = index.by_concept.get(concept, [])
    elif context_id is not None:
        all_facts = index.by_context.get(context_id, [])
    elif unit_id is not None:
        all_facts = index.by_unit.get(unit_id, [])
    elif period_instant is not None:
        all_facts = index.by_period_instant.get(period_instant, [])
    elif dimension_key is not None:
        all_facts = index.by_dimension_key.get(dimension_key, [])

    return [f for f in all_facts if id(f) in result_ids]
