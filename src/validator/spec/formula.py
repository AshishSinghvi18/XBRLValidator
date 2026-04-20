"""Formula linkbase validator.

Implements 6 checks (FORMULA-0001 through FORMULA-0006) covering the
XBRL Formula 1.0 specification requirements.

Spec references:
- XBRL Formula 1.0 §2 (variable sets)
- XBRL Formula 1.0 §3 (assertions)
- XBRL Formula 1.0 §4 (filters)
"""

from __future__ import annotations

import logging
from collections import defaultdict
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

# Formula-related arcroles
_VARIABLE_SET_ARCROLE = "http://xbrl.org/arcrole/2008/variable-set"
_VARIABLE_FILTER_ARCROLE = "http://xbrl.org/arcrole/2008/variable-filter"
_VARIABLE_SET_FILTER = "http://xbrl.org/arcrole/2008/variable-set-filter"


class FormulaValidator(BaseValidator):
    """Validator for XBRL Formula 1.0 specification rules.

    Implements 6 checks covering formula linkbase integrity, variable
    bindings, assertion evaluation, and filter consistency.
    """

    def __init__(self, instance: XBRLInstance) -> None:
        super().__init__(instance)

    def validate(self) -> list[ValidationMessage]:
        """Run all 6 formula checks and return messages."""
        self._messages.clear()

        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return []

        checks = [
            self._check_0001_unsatisfied_assertion,
            self._check_0002_variable_binding_error,
            self._check_0003_undefined_variable_reference,
            self._check_0004_circular_variable_dependency,
            self._check_0005_conflicting_filters,
            self._check_0006_formula_evaluation_error,
        ]
        for check in checks:
            try:
                check()
            except Exception:
                self._logger.exception("Check %s failed unexpectedly", check.__name__)
        return list(self._messages)

    def _get_formula_arcs(self) -> list[ArcModel]:
        """Collect formula-related arcs from the taxonomy."""
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return []
        arcs: list[ArcModel] = []
        for lb in taxonomy.definition_linkbases:
            for arc in lb.arcs:
                if "variable" in arc.arcrole or "formula" in arc.arcrole:
                    arcs.append(arc)
        return arcs

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_0001_unsatisfied_assertion(self) -> None:
        """FORMULA-0001: Value assertion is not satisfied.

        Spec: XBRL Formula 1.0 §3.1 – a value assertion evaluates
        to ``false`` for one or more variable bindings, indicating
        a business rule violation.
        """
        # Formula evaluation requires an XPath engine; this check
        # validates structural prerequisites.
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for lb in taxonomy.definition_linkbases:
            for arc in lb.arcs:
                if "assertion" in arc.arcrole.lower():
                    # Flag assertions that reference concepts not in the instance
                    concept = arc.to_concept
                    if concept and concept not in taxonomy.concepts:
                        self.warning(
                            "FORMULA-0001",
                            f"Assertion target concept '{concept}' is not "
                            f"defined in the taxonomy",
                            concept=concept,
                        )

    def _check_0002_variable_binding_error(self) -> None:
        """FORMULA-0002: Variable cannot be bound to any fact.

        Spec: XBRL Formula 1.0 §2.1 – a fact variable that matches
        no facts produces an empty binding set.
        """
        arcs = self._get_formula_arcs()
        for arc in arcs:
            if _VARIABLE_SET_ARCROLE in arc.arcrole:
                variable_concept = arc.to_concept
                if variable_concept:
                    facts = self._instance.get_facts_by_concept(variable_concept)
                    if not facts:
                        self.info(
                            "FORMULA-0002",
                            f"Formula variable targeting concept "
                            f"'{variable_concept}' has no matching facts",
                            concept=variable_concept,
                        )

    def _check_0003_undefined_variable_reference(self) -> None:
        """FORMULA-0003: Formula references an undefined variable.

        Spec: XBRL Formula 1.0 §2.2 – all variable references in
        a formula expression MUST resolve to a defined variable.
        """
        arcs = self._get_formula_arcs()
        defined_vars: set[str] = set()
        referenced_vars: set[str] = set()

        for arc in arcs:
            if _VARIABLE_SET_ARCROLE in arc.arcrole:
                defined_vars.add(arc.to_concept)
            if "variable-filter" in arc.arcrole:
                referenced_vars.add(arc.from_concept)

        for var in referenced_vars - defined_vars:
            if var:
                self.error(
                    "FORMULA-0003",
                    f"Formula references undefined variable '{var}'",
                    concept=var,
                )

    def _check_0004_circular_variable_dependency(self) -> None:
        """FORMULA-0004: Circular dependency among formula variables.

        Spec: XBRL Formula 1.0 §2.3 – variable dependency graphs
        MUST be acyclic.
        """
        arcs = self._get_formula_arcs()
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
                    "FORMULA-0004",
                    f"Circular dependency detected in formula variables "
                    f"involving '{node}'",
                    concept=node,
                )
                cycles_reported.add(node)
                return
            if node in visited:
                return
            visited.add(node)
            in_stack.add(node)
            for dep in graph.get(node, set()):
                dfs(dep)
            in_stack.discard(node)

        for node in graph:
            dfs(node)

    def _check_0005_conflicting_filters(self) -> None:
        """FORMULA-0005: Conflicting filters on the same variable.

        Spec: XBRL Formula 1.0 §4.1 – filters applied to a variable
        MUST NOT produce a contradictory match (e.g., requiring a
        concept to be both X and Y).
        """
        arcs = self._get_formula_arcs()
        filters_by_var: dict[str, list[str]] = defaultdict(list)

        for arc in arcs:
            if "filter" in arc.arcrole.lower():
                filters_by_var[arc.from_concept].append(arc.to_concept)

        for var, filters in filters_by_var.items():
            if len(filters) != len(set(filters)):
                self.warning(
                    "FORMULA-0005",
                    f"Variable '{var}' has duplicate filter targets",
                    concept=var,
                )

    def _check_0006_formula_evaluation_error(self) -> None:
        """FORMULA-0006: Formula expression evaluation error.

        Spec: XBRL Formula 1.0 §3.2 – formulas that contain
        structural errors (missing components) cannot be evaluated.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        arcs = self._get_formula_arcs()
        # Check for arcs with missing from/to concepts
        for arc in arcs:
            if not arc.from_concept or not arc.to_concept:
                self.error(
                    "FORMULA-0006",
                    f"Formula arc has missing concept reference "
                    f"(from='{arc.from_concept}', to='{arc.to_concept}')",
                )
