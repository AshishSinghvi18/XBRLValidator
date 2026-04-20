"""Table linkbase validator.

Implements 5 checks (TBL-0001 through TBL-0005) covering the
XBRL Table Linkbase 1.0 specification requirements.

Spec references:
- Table Linkbase 1.0 §2 (table structure)
- Table Linkbase 1.0 §3 (breakdown definitions)
- Table Linkbase 1.0 §4 (aspect rules)
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

# Table-related arcroles
_TABLE_BREAKDOWN = "http://xbrl.org/arcrole/2014/table-breakdown"
_BREAKDOWN_TREE = "http://xbrl.org/arcrole/2014/breakdown-tree"
_TABLE_FILTER = "http://xbrl.org/arcrole/2014/table-filter"


class TableValidator(BaseValidator):
    """Validator for XBRL Table Linkbase 1.0 specification rules.

    Implements 5 checks covering table structure, breakdowns,
    definition nodes, and aspect consistency.
    """

    def __init__(self, instance: XBRLInstance) -> None:
        super().__init__(instance)

    def validate(self) -> list[ValidationMessage]:
        """Run all 5 table linkbase checks and return messages."""
        self._messages.clear()

        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return []

        checks = [
            self._check_0001_missing_breakdown,
            self._check_0002_invalid_definition_node,
            self._check_0003_conflicting_aspect_rules,
            self._check_0004_empty_table,
            self._check_0005_circular_table_structure,
        ]
        for check in checks:
            try:
                check()
            except Exception:
                self._logger.exception("Check %s failed unexpectedly", check.__name__)
        return list(self._messages)

    def _get_table_arcs(self) -> list[ArcModel]:
        """Collect table-related arcs from the taxonomy."""
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return []
        arcs: list[ArcModel] = []
        for lb in taxonomy.definition_linkbases:
            for arc in lb.arcs:
                if "table" in arc.arcrole or "breakdown" in arc.arcrole:
                    arcs.append(arc)
        return arcs

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_0001_missing_breakdown(self) -> None:
        """TBL-0001: Table has no breakdown definitions.

        Spec: Table Linkbase 1.0 §3.1 – a table MUST have at least
        one breakdown on each axis (x, y) to be renderable.
        """
        arcs = self._get_table_arcs()
        tables: set[str] = set()
        tables_with_breakdowns: set[str] = set()

        for arc in arcs:
            if "table" in arc.arcrole.lower():
                tables.add(arc.from_concept)
            if _TABLE_BREAKDOWN in arc.arcrole:
                tables_with_breakdowns.add(arc.from_concept)

        for table in tables - tables_with_breakdowns:
            self.warning(
                "TBL-0001",
                f"Table '{table}' has no breakdown definitions",
                concept=table,
            )

    def _check_0002_invalid_definition_node(self) -> None:
        """TBL-0002: Definition node references undeclared concept.

        Spec: Table Linkbase 1.0 §3.2 – definition nodes MUST
        reference concepts that exist in the DTS.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        arcs = self._get_table_arcs()
        for arc in arcs:
            for concept in (arc.from_concept, arc.to_concept):
                if concept and concept not in taxonomy.concepts:
                    self.warning(
                        "TBL-0002",
                        f"Table definition node references undeclared "
                        f"concept '{concept}'",
                        concept=concept,
                    )

    def _check_0003_conflicting_aspect_rules(self) -> None:
        """TBL-0003: Conflicting aspect rules in table definition.

        Spec: Table Linkbase 1.0 §4.1 – aspect rules on the same
        axis MUST NOT specify conflicting values for the same aspect.
        """
        arcs = self._get_table_arcs()
        aspect_by_table: dict[str, list[str]] = defaultdict(list)

        for arc in arcs:
            if "aspect" in arc.arcrole.lower():
                aspect_by_table[arc.from_concept].append(arc.to_concept)

        for table, aspects in aspect_by_table.items():
            if len(aspects) != len(set(aspects)):
                self.warning(
                    "TBL-0003",
                    f"Table '{table}' has potentially conflicting "
                    f"aspect rules",
                    concept=table,
                )

    def _check_0004_empty_table(self) -> None:
        """TBL-0004: Table definition produces no cells.

        Spec: Table Linkbase 1.0 §2.1 – a table that resolves to
        zero cells is effectively empty and SHOULD be reviewed.
        """
        arcs = self._get_table_arcs()
        tables_with_content: set[str] = set()

        for arc in arcs:
            if _TABLE_BREAKDOWN in arc.arcrole or _BREAKDOWN_TREE in arc.arcrole:
                tables_with_content.add(arc.from_concept)

        arcs_tables = {
            arc.from_concept
            for arc in arcs
            if "table" in arc.arcrole.lower()
        }

        for table in arcs_tables - tables_with_content:
            self.info(
                "TBL-0004",
                f"Table '{table}' may produce no visible cells",
                concept=table,
            )

    def _check_0005_circular_table_structure(self) -> None:
        """TBL-0005: Circular reference in table structure.

        Spec: Table Linkbase 1.0 §2.2 – table definition networks
        MUST be acyclic.
        """
        arcs = self._get_table_arcs()
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
                    "TBL-0005",
                    f"Circular reference in table structure involving "
                    f"'{node}'",
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
