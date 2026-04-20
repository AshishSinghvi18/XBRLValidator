"""Calculation linkbase validator.

Implements 6 checks (CALC-0001 through CALC-0006) covering XBRL 2.1
calculation consistency and summation-item integrity.

**All arithmetic uses :class:`~decimal.Decimal`, NEVER ``float``.**

Spec references:
- XBRL 2.1 §5.2.5.2 (calculation consistency)
- XBRL 2.1 §5.2.5.1 (summation-item relationships)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Iterator

from src.core.model.xbrl_model import (
    ArcModel,
    Fact,
    LinkbaseModel,
    ValidationMessage,
    XBRLInstance,
)
from src.core.types import LinkbaseType, Severity
from src.validator.base import BaseValidator

logger = logging.getLogger(__name__)

# Summation-item arcrole
_SUMMATION_ITEM = "http://www.xbrl.org/2003/arcrole/summation-item"


class CalculationValidator(BaseValidator):
    """Validator for XBRL 2.1 calculation linkbase rules.

    All arithmetic uses :class:`~decimal.Decimal` to avoid
    floating-point rounding issues.

    Implements 6 checks covering calculation consistency, circular
    references, and weight constraints.
    """

    def __init__(self, instance: XBRLInstance) -> None:
        super().__init__(instance)

    def validate(self) -> list[ValidationMessage]:
        """Run all 6 calculation checks and return messages."""
        self._messages.clear()
        checks = [
            self._check_0001_calculation_inconsistency,
            self._check_0002_missing_contributing_fact,
            self._check_0003_circular_calculation,
            self._check_0004_zero_weight,
            self._check_0005_duplicate_arc,
            self._check_0006_invalid_weight,
        ]
        for check in checks:
            try:
                check()
            except Exception:
                self._logger.exception("Check %s failed unexpectedly", check.__name__)
        return list(self._messages)

    def _iter_facts(self) -> Iterator[Fact]:
        """Iterate facts in both memory and large-file mode."""
        if self._instance.is_large_file_mode and self._instance.fact_store is not None:
            yield from self._instance.fact_store.iter_batches()
        else:
            yield from self._instance.facts

    def _get_calculation_arcs(self) -> list[ArcModel]:
        """Collect all summation-item arcs from calculation linkbases."""
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return []
        arcs: list[ArcModel] = []
        for lb in taxonomy.calculation_linkbases:
            for arc in lb.arcs:
                if arc.arcrole == _SUMMATION_ITEM:
                    arcs.append(arc)
        return arcs

    def _build_summation_map(
        self,
    ) -> dict[str, list[tuple[str, Decimal]]]:
        """Build parent → [(child, weight)] map from summation-item arcs.

        Returns:
            Mapping from parent concept QName to list of
            (child concept QName, weight) tuples.
        """
        result: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
        for arc in self._get_calculation_arcs():
            weight = arc.weight if arc.weight is not None else Decimal(1)
            result[arc.from_concept].append((arc.to_concept, weight))
        return result

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_0001_calculation_inconsistency(self) -> None:
        """CALC-0001: Calculation summation inconsistency.

        Spec: XBRL 2.1 §5.2.5.2 – for each summation-item parent,
        the rounded value of the parent MUST equal the sum of the
        rounded contributing items (within tolerance).

        Tolerance: the difference between the reported total and the
        calculated total must be within 10^(-decimals) of each
        contributing fact (per §5.2.5.2).
        """
        summation_map = self._build_summation_map()
        if not summation_map:
            return

        # Group facts by context+unit for comparison
        facts_by_concept: dict[str, list[Fact]] = defaultdict(list)
        for fact in self._iter_facts():
            if fact.is_numeric and not fact.is_nil:
                facts_by_concept[fact.concept].append(fact)

        for parent_concept, children in summation_map.items():
            parent_facts = facts_by_concept.get(parent_concept, [])
            for parent_fact in parent_facts:
                if parent_fact.rounded_value is None:
                    continue
                ctx_ref = parent_fact.context_ref
                unit_ref = parent_fact.unit_ref

                calculated_total = Decimal(0)
                all_present = True
                for child_concept, weight in children:
                    child_facts = facts_by_concept.get(child_concept, [])
                    child_match = None
                    for cf in child_facts:
                        if cf.context_ref == ctx_ref and cf.unit_ref == unit_ref:
                            child_match = cf
                            break
                    if child_match is None or child_match.rounded_value is None:
                        all_present = False
                        continue
                    calculated_total += weight * child_match.rounded_value

                if not all_present:
                    continue

                # Compute tolerance per §5.2.5.2
                tolerance = self._compute_tolerance(parent_fact)
                diff = abs(parent_fact.rounded_value - calculated_total)

                if diff > tolerance:
                    self.inconsistency(
                        "CALC-0001",
                        f"Calculation inconsistency for '{parent_concept}' "
                        f"in context '{ctx_ref}': reported "
                        f"{parent_fact.rounded_value}, calculated "
                        f"{calculated_total} (diff={diff}, "
                        f"tolerance={tolerance})",
                        concept=parent_concept,
                        context_id=ctx_ref,
                        fact_id=parent_fact.id,
                        source_line=parent_fact.source_line,
                    )

    def _check_0002_missing_contributing_fact(self) -> None:
        """CALC-0002: Contributing fact is missing from the instance.

        Spec: XBRL 2.1 §5.2.5.2 – when a summation-item parent is
        reported but one or more contributing items are absent, the
        calculation cannot be verified.
        """
        summation_map = self._build_summation_map()
        if not summation_map:
            return

        facts_by_concept: dict[str, list[Fact]] = defaultdict(list)
        for fact in self._iter_facts():
            if fact.is_numeric and not fact.is_nil:
                facts_by_concept[fact.concept].append(fact)

        for parent_concept, children in summation_map.items():
            parent_facts = facts_by_concept.get(parent_concept, [])
            for parent_fact in parent_facts:
                ctx_ref = parent_fact.context_ref
                unit_ref = parent_fact.unit_ref
                for child_concept, _weight in children:
                    child_facts = facts_by_concept.get(child_concept, [])
                    match = any(
                        cf.context_ref == ctx_ref and cf.unit_ref == unit_ref
                        for cf in child_facts
                    )
                    if not match:
                        self.info(
                            "CALC-0002",
                            f"Contributing fact '{child_concept}' missing "
                            f"for calculation parent '{parent_concept}' in "
                            f"context '{ctx_ref}'",
                            concept=parent_concept,
                            context_id=ctx_ref,
                        )

    def _check_0003_circular_calculation(self) -> None:
        """CALC-0003: Circular reference in calculation linkbase.

        Spec: XBRL 2.1 §5.2.5.1 – summation-item networks MUST NOT
        contain cycles.
        """
        summation_map = self._build_summation_map()
        if not summation_map:
            return

        visited: set[str] = set()
        in_stack: set[str] = set()
        cycles_reported: set[str] = set()

        def dfs(node: str) -> None:
            if node in in_stack and node not in cycles_reported:
                self.error(
                    "CALC-0003",
                    f"Circular calculation reference detected "
                    f"involving concept '{node}'",
                    concept=node,
                )
                cycles_reported.add(node)
                return
            if node in visited:
                return
            visited.add(node)
            in_stack.add(node)
            for child, _w in summation_map.get(node, []):
                dfs(child)
            in_stack.discard(node)

        for parent in summation_map:
            dfs(parent)

    def _check_0004_zero_weight(self) -> None:
        """CALC-0004: Summation-item arc has zero weight.

        Spec: XBRL 2.1 §5.2.5.1 – a weight of zero is meaningless
        in a summation relationship and is likely an error.
        """
        for arc in self._get_calculation_arcs():
            if arc.weight is not None and arc.weight == Decimal(0):
                self.warning(
                    "CALC-0004",
                    f"Summation-item arc from '{arc.from_concept}' to "
                    f"'{arc.to_concept}' has zero weight",
                    concept=arc.from_concept,
                )

    def _check_0005_duplicate_arc(self) -> None:
        """CALC-0005: Duplicate summation-item arcs.

        Spec: XBRL 2.1 §3.5.3.9.6 – duplicate arcs with the same
        from, to, and equivalent attributes are redundant.
        """
        seen: set[tuple[str, str]] = set()
        for arc in self._get_calculation_arcs():
            key = (arc.from_concept, arc.to_concept)
            if key in seen:
                self.warning(
                    "CALC-0005",
                    f"Duplicate summation-item arc from "
                    f"'{arc.from_concept}' to '{arc.to_concept}'",
                    concept=arc.from_concept,
                )
            seen.add(key)

    def _check_0006_invalid_weight(self) -> None:
        """CALC-0006: Invalid weight value on summation-item arc.

        Spec: XBRL 2.1 §5.2.5.1 – the ``weight`` attribute MUST be
        a valid decimal number.
        """
        for arc in self._get_calculation_arcs():
            if arc.weight is None:
                self.warning(
                    "CALC-0006",
                    f"Summation-item arc from '{arc.from_concept}' to "
                    f"'{arc.to_concept}' has no weight attribute",
                    concept=arc.from_concept,
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_tolerance(fact: Fact) -> Decimal:
        """Compute rounding tolerance per XBRL 2.1 §5.2.5.2.

        The tolerance is ``0.5 × 10^(-decimals)`` for each fact.
        If ``decimals="INF"`` the tolerance is zero.

        Args:
            fact: The numeric fact.

        Returns:
            Tolerance as a :class:`Decimal`.
        """
        if fact.decimals is None or fact.decimals.upper() == "INF":
            return Decimal(0)
        try:
            dec = int(fact.decimals)
            return Decimal(5) * Decimal(10) ** (-(dec + 1))
        except (ValueError, InvalidOperation):
            return Decimal(0)
