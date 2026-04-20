"""OIM fact equivalence — determines if two facts are equivalent per the OIM spec.

Two facts are "equal" (duplicate) in OIM when they have the same:
  - concept
  - entity
  - period
  - all dimensions
  - unit
  - language (for string facts)
  - value (after rounding for numeric facts)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

import structlog

from src.core.model.xbrl_model import Context, Fact, Unit, XBRLInstance

logger = structlog.get_logger(__name__)


class FactEquivalence:
    """Compare facts for OIM-compliant equivalence."""

    def __init__(self) -> None:
        self._log = logger.bind(component="fact_equivalence")

    def are_facts_equal(
        self,
        fact_a: Fact,
        fact_b: Fact,
        instance: XBRLInstance,
    ) -> bool:
        """Test if two facts are OIM-equivalent within the given instance."""
        if fact_a.concept_qname != fact_b.concept_qname:
            return False
        if fact_a.is_nil != fact_b.is_nil:
            return False
        if fact_a.language != fact_b.language:
            return False

        # Context equivalence
        if not self._contexts_equivalent(fact_a, fact_b, instance):
            return False

        # Unit equivalence
        if not self._units_equivalent(fact_a, fact_b, instance):
            return False

        # Value equivalence
        return self._values_equivalent(fact_a, fact_b)

    def _contexts_equivalent(
        self, fact_a: Fact, fact_b: Fact, instance: XBRLInstance
    ) -> bool:
        if fact_a.context_ref is None and fact_b.context_ref is None:
            return True
        if fact_a.context_ref is None or fact_b.context_ref is None:
            return False
        ctx_a = instance.contexts.get(fact_a.context_ref)
        ctx_b = instance.contexts.get(fact_b.context_ref)
        if ctx_a is None or ctx_b is None:
            return fact_a.context_ref == fact_b.context_ref
        return ctx_a.is_dimensional_equivalent(ctx_b)

    def _units_equivalent(
        self, fact_a: Fact, fact_b: Fact, instance: XBRLInstance
    ) -> bool:
        if fact_a.unit_ref is None and fact_b.unit_ref is None:
            return True
        if fact_a.unit_ref is None or fact_b.unit_ref is None:
            return False
        unit_a = instance.units.get(fact_a.unit_ref)
        unit_b = instance.units.get(fact_b.unit_ref)
        if unit_a is None or unit_b is None:
            return fact_a.unit_ref == fact_b.unit_ref
        return unit_a.is_equal(unit_b)

    def _values_equivalent(self, fact_a: Fact, fact_b: Fact) -> bool:
        if fact_a.is_nil and fact_b.is_nil:
            return True
        if fact_a.is_numeric and fact_b.is_numeric:
            return self._numeric_values_equal(fact_a, fact_b)
        return fact_a.raw_value == fact_b.raw_value

    def _numeric_values_equal(self, fact_a: Fact, fact_b: Fact) -> bool:
        val_a = fact_a.rounded_value
        val_b = fact_b.rounded_value
        if val_a is None or val_b is None:
            return fact_a.raw_value == fact_b.raw_value
        return val_a == val_b

    def find_duplicates(self, instance: XBRLInstance) -> list[tuple[Fact, Fact]]:
        """Find all pairs of duplicate facts in the instance."""
        self._log.info("find_duplicates_start", fact_count=len(instance.facts))
        duplicates: list[tuple[Fact, Fact]] = []
        groups: dict[tuple[str, ...], list[Fact]] = {}

        for fact in instance.facts:
            key = fact.duplicate_key
            str_key = tuple(str(k) for k in key)
            groups.setdefault(str_key, []).append(fact)

        for group_facts in groups.values():
            if len(group_facts) < 2:
                continue
            for i in range(len(group_facts)):
                for j in range(i + 1, len(group_facts)):
                    if self.are_facts_equal(group_facts[i], group_facts[j], instance):
                        duplicates.append((group_facts[i], group_facts[j]))

        self._log.info("find_duplicates_complete", duplicate_pairs=len(duplicates))
        return duplicates
