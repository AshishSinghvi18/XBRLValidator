"""Presentation linkbase validator.

Implements 5 checks (PRES-0001 through PRES-0005) covering the
XBRL 2.1 presentation linkbase specification requirements.

Spec references:
- XBRL 2.1 §5.2.4.1 (parent-child relationships)
- XBRL 2.1 §5.2.4.2 (preferred labels)
- XBRL 2.1 §5.2.4.3 (ordering)
"""

from __future__ import annotations

import logging
from collections import defaultdict

from src.core.model.xbrl_model import (
    ArcModel,
    ValidationMessage,
    XBRLInstance,
)
from src.core.types import Severity
from src.validator.base import BaseValidator

logger = logging.getLogger(__name__)

_PARENT_CHILD = "http://www.xbrl.org/2003/arcrole/parent-child"


class PresentationValidator(BaseValidator):
    """Validator for XBRL 2.1 presentation linkbase rules.

    Implements 5 checks covering parent-child relationships, preferred
    labels, ordering, circular references, and concept existence.
    """

    def __init__(self, instance: XBRLInstance) -> None:
        super().__init__(instance)

    def validate(self) -> list[ValidationMessage]:
        """Run all 5 presentation linkbase checks and return messages."""
        self._messages.clear()

        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return []

        checks = [
            self._check_0001_undeclared_concept,
            self._check_0002_circular_presentation,
            self._check_0003_duplicate_presentation_arc,
            self._check_0004_invalid_preferred_label,
            self._check_0005_ordering_gap,
        ]
        for check in checks:
            try:
                check()
            except Exception:
                self._logger.exception("Check %s failed unexpectedly", check.__name__)
        return list(self._messages)

    def _get_presentation_arcs(self) -> list[ArcModel]:
        """Collect parent-child arcs from presentation linkbases."""
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return []
        arcs: list[ArcModel] = []
        for lb in taxonomy.presentation_linkbases:
            for arc in lb.arcs:
                if arc.arcrole == _PARENT_CHILD:
                    arcs.append(arc)
        return arcs

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_0001_undeclared_concept(self) -> None:
        """PRES-0001: Presentation arc references undeclared concept.

        Spec: XBRL 2.1 §5.2.4.1 – both ends of a parent-child arc
        MUST reference concepts declared in the DTS.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for arc in self._get_presentation_arcs():
            for concept in (arc.from_concept, arc.to_concept):
                if concept and concept not in taxonomy.concepts:
                    self.warning(
                        "PRES-0001",
                        f"Presentation arc references undeclared concept "
                        f"'{concept}'",
                        concept=concept,
                    )

    def _check_0002_circular_presentation(self) -> None:
        """PRES-0002: Circular reference in presentation hierarchy.

        Spec: XBRL 2.1 §5.2.4.1 – parent-child networks MUST form
        a directed acyclic graph.
        """
        arcs = self._get_presentation_arcs()
        graph: dict[str, set[str]] = defaultdict(set)

        for arc in arcs:
            if arc.from_concept and arc.to_concept:
                graph[arc.from_concept].add(arc.to_concept)

        visited: set[str] = set()
        in_stack: set[str] = set()
        cycles_reported: set[str] = set()

        def dfs(node: str) -> None:
            if node in in_stack and node not in cycles_reported:
                self.error(
                    "PRES-0002",
                    f"Circular reference in presentation hierarchy "
                    f"involving '{node}'",
                    concept=node,
                )
                cycles_reported.add(node)
                return
            if node in visited:
                return
            visited.add(node)
            in_stack.add(node)
            for child in graph.get(node, set()):
                dfs(child)
            in_stack.discard(node)

        for node in graph:
            dfs(node)

    def _check_0003_duplicate_presentation_arc(self) -> None:
        """PRES-0003: Duplicate parent-child arc.

        Spec: XBRL 2.1 §3.5.3.9.6 – equivalent arcs (same from/to
        and attributes) are redundant.
        """
        seen: set[tuple[str, str]] = set()
        for arc in self._get_presentation_arcs():
            key = (arc.from_concept, arc.to_concept)
            if key in seen:
                self.warning(
                    "PRES-0003",
                    f"Duplicate presentation arc from "
                    f"'{arc.from_concept}' to '{arc.to_concept}'",
                    concept=arc.from_concept,
                )
            seen.add(key)

    def _check_0004_invalid_preferred_label(self) -> None:
        """PRES-0004: Preferred label role is not valid.

        Spec: XBRL 2.1 §5.2.4.2 – the ``preferredLabel`` attribute
        MUST reference a role that is declared in the DTS or is a
        standard XBRL label role.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        standard_roles = {
            "http://www.xbrl.org/2003/role/label",
            "http://www.xbrl.org/2003/role/terseLabel",
            "http://www.xbrl.org/2003/role/verboseLabel",
            "http://www.xbrl.org/2003/role/totalLabel",
            "http://www.xbrl.org/2003/role/periodStartLabel",
            "http://www.xbrl.org/2003/role/periodEndLabel",
            "http://www.xbrl.org/2003/role/negatedLabel",
            "http://www.xbrl.org/2003/role/negatedTerseLabel",
            "http://www.xbrl.org/2003/role/negatedTotalLabel",
        }
        for arc in self._get_presentation_arcs():
            if arc.preferred_label:
                if (
                    arc.preferred_label not in standard_roles
                    and arc.preferred_label not in taxonomy.role_types
                ):
                    self.warning(
                        "PRES-0004",
                        f"Presentation arc from '{arc.from_concept}' to "
                        f"'{arc.to_concept}' uses undeclared preferred "
                        f"label role '{arc.preferred_label}'",
                        concept=arc.from_concept,
                    )

    def _check_0005_ordering_gap(self) -> None:
        """PRES-0005: Ordering gaps in sibling presentation arcs.

        Spec: XBRL 2.1 §5.2.4.3 – while not strictly an error,
        significant gaps in ordering values among siblings may
        indicate missing elements.
        """
        arcs = self._get_presentation_arcs()
        children_by_parent: dict[str, list[float]] = defaultdict(list)

        for arc in arcs:
            if arc.from_concept:
                children_by_parent[arc.from_concept].append(arc.order)

        for parent, orders in children_by_parent.items():
            if len(orders) < 2:
                continue
            sorted_orders = sorted(orders)
            for i in range(1, len(sorted_orders)):
                gap = sorted_orders[i] - sorted_orders[i - 1]
                if gap > 100:
                    self.info(
                        "PRES-0005",
                        f"Large ordering gap ({gap}) among children of "
                        f"'{parent}' in presentation linkbase",
                        concept=parent,
                    )
                    break
