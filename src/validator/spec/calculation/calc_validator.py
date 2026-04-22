"""Calculation linkbase consistency — XBRL 2.1 §5.2.5.2.

Validates that reported numeric fact values are consistent with the
weighted sums defined by summation-item arcs in the calculation linkbase.

References:
    - XBRL 2.1 §5.2.5.2 (Calculation Linkbase Validation)
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from src.core.constants import DEFAULT_CALC_TOLERANCE
from src.core.model.fact import Fact
from src.core.model.instance import ValidationMessage, XBRLInstance
from src.core.networks.relationship import Arc, RelationshipNetwork
from src.core.types import FactType, Severity


class CalculationValidator:
    """Validates calculation linkbase consistency.

    For each summation-item relationship in the calculation network,
    verifies that the reported total equals the weighted sum of the
    contributing items, after rounding to the precision indicated by the
    ``decimals`` attribute.

    Spec: XBRL 2.1 §5.2.5.2 (Calculation Linkbase)
    """

    def __init__(
        self, tolerance: Decimal = DEFAULT_CALC_TOLERANCE
    ) -> None:
        """Initialise the calculation validator.

        Args:
            tolerance: Maximum acceptable difference between the reported
                total and the computed sum. Defaults to
                :data:`~src.core.constants.DEFAULT_CALC_TOLERANCE`.
        """
        self._tolerance: Decimal = tolerance

    def validate(
        self,
        instance: XBRLInstance,
        calc_network: RelationshipNetwork,
    ) -> list[ValidationMessage]:
        """Validate calculation consistency for all summation-item relationships.

        For each total concept in the calculation network, checks that the
        reported value equals the weighted sum of its contributing items.

        Per XBRL 2.1 §5.2.5.2, calculation validation is performed
        per-context: the total fact and all contributing facts must share
        the same context.

        Spec: XBRL 2.1 §5.2.5.2 | Emits: CALC-0001, CALC-0002

        Args:
            instance: The XBRL instance containing facts to validate.
            calc_network: A :class:`RelationshipNetwork` containing
                summation-item arcs.

        Returns:
            List of validation messages for calculation inconsistencies
            and missing contributing items.
        """
        messages: list[ValidationMessage] = []

        # Pre-index facts by concept QName for efficient lookups
        facts_by_concept: dict[str, list[Fact]] = defaultdict(list)
        for fact in instance.facts:
            facts_by_concept[fact.concept_qname].append(fact)

        # Find all total concepts (those that appear as ``from`` in arcs)
        total_qnames: set[str] = set()
        for root in calc_network.roots():
            total_qnames.add(root)
            # Also consider intermediate totals
            self._collect_parents(calc_network, root, total_qnames)

        for total_qname in sorted(total_qnames):
            contributing_arcs: list[Arc] = calc_network.children(total_qname)
            if not contributing_arcs:
                continue

            # Validate for each total fact reported
            for total_fact in facts_by_concept.get(total_qname, []):
                result = self._check_summation(
                    total_fact,
                    contributing_arcs,
                    facts_by_concept,
                    instance,
                )
                if result is not None:
                    messages.append(result)

        return messages

    def _collect_parents(
        self,
        network: RelationshipNetwork,
        qname: str,
        parents: set[str],
    ) -> None:
        """Recursively collect all concepts that are parents (totals).

        Args:
            network: The calculation relationship network.
            qname: Starting concept QName.
            parents: Accumulator set of parent QNames.
        """
        for arc in network.children(qname):
            child_children = network.children(arc.to_qname)
            if child_children:
                parents.add(arc.to_qname)
                if arc.to_qname not in parents:
                    self._collect_parents(network, arc.to_qname, parents)

    def _check_summation(
        self,
        total_fact: Fact,
        contributing_arcs: list[Arc],
        facts_by_concept: dict[str, list[Fact]],
        instance: XBRLInstance,
    ) -> ValidationMessage | None:
        """Check one summation-item calculation.

        Matches contributing facts to the same context as the total
        fact.  Uses Decimal arithmetic only.  Applies rounding per
        §5.2.5.2: when the total has a ``decimals`` attribute, both the
        computed sum and the reported total are rounded to that number
        of decimal places before comparison.

        Spec: XBRL 2.1 §5.2.5.2 | Emits: CALC-0001, CALC-0002

        Args:
            total_fact: The fact representing the total/summation concept.
            contributing_arcs: Arcs from the total to its contributing items.
            facts_by_concept: Pre-indexed mapping of concept QName → facts.
            instance: The XBRL instance (for context lookups).

        Returns:
            A :class:`ValidationMessage` if inconsistency is found,
            otherwise ``None``.
        """
        # Total must be numeric with a Decimal value
        if not total_fact.is_numeric or total_fact.is_nil:
            return None
        if not isinstance(total_fact.value, Decimal):
            return None

        context_ref: str = total_fact.context_ref
        unit_ref: str | None = total_fact.unit_ref

        computed_sum: Decimal = Decimal(0)
        any_contributor_found: bool = False
        missing_items: list[str] = []

        for arc in contributing_arcs:
            weight: Decimal = arc.weight if arc.weight is not None else Decimal(1)

            # Find matching contributor in same context and unit
            matching_facts: list[Fact] = [
                f
                for f in facts_by_concept.get(arc.to_qname, [])
                if f.context_ref == context_ref
                and f.unit_ref == unit_ref
                and f.is_numeric
                and not f.is_nil
                and isinstance(f.value, Decimal)
            ]

            if not matching_facts:
                missing_items.append(arc.to_qname)
                continue

            # Per §5.2.5.2, if multiple facts for the same concept exist
            # in the same context, use the first one (duplicate facts are
            # a separate validation concern)
            contributor: Fact = matching_facts[0]
            any_contributor_found = True
            computed_sum += weight * contributor.value  # type: ignore[operator]

        # If no contributing items were found at all, emit CALC-0002
        if not any_contributor_found:
            if missing_items:
                return ValidationMessage(
                    code="CALC-0002",
                    severity=Severity.WARNING,
                    message=(
                        f"Calculation for total '{total_fact.concept_qname}' "
                        f"in context '{context_ref}': none of the "
                        f"{len(missing_items)} contributing item(s) have "
                        f"reported facts."
                    ),
                    spec_ref="XBRL 2.1 §5.2.5.2",
                    file_path=total_fact.source_file,
                    line=total_fact.source_line,
                )
            return None

        # Apply rounding per §5.2.5.2
        reported_total: Decimal = total_fact.value  # type: ignore[assignment]
        rounded_sum: Decimal = computed_sum
        rounded_total: Decimal = reported_total

        if total_fact.decimals is not None:
            try:
                quant: Decimal = Decimal(10) ** (-total_fact.decimals)
                rounded_sum = computed_sum.quantize(quant, rounding=ROUND_HALF_UP)
                rounded_total = reported_total.quantize(
                    quant, rounding=ROUND_HALF_UP
                )
            except InvalidOperation:
                # If quantize fails (e.g. INF decimals), compare unrounded
                pass

        difference: Decimal = abs(rounded_total - rounded_sum)

        if difference > self._tolerance:
            return ValidationMessage(
                code="CALC-0001",
                severity=Severity.INCONSISTENCY,
                message=(
                    f"Calculation inconsistency for "
                    f"'{total_fact.concept_qname}' in context "
                    f"'{context_ref}': reported {reported_total}, "
                    f"computed sum {computed_sum} "
                    f"(difference: {difference})."
                ),
                spec_ref="XBRL 2.1 §5.2.5.2",
                file_path=total_fact.source_file,
                line=total_fact.source_line,
                fix_suggestion=(
                    "Verify the reported total matches the sum of "
                    "contributing items."
                ),
            )

        return None
