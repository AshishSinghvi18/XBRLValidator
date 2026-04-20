"""Definition linkbase validator.

Implements 5 checks (DEF-0001 through DEF-0005) covering the
XBRL 2.1 definition linkbase specification requirements.

Spec references:
- XBRL 2.1 §5.2.6.1 (general-special relationships)
- XBRL 2.1 §5.2.6.2 (essence-alias relationships)
- XBRL 2.1 §5.2.6.3 (similar-tuples / requires-element)
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

# Standard definition arcroles
_GENERAL_SPECIAL = "http://www.xbrl.org/2003/arcrole/general-special"
_ESSENCE_ALIAS = "http://www.xbrl.org/2003/arcrole/essence-alias"
_SIMILAR_TUPLES = "http://www.xbrl.org/2003/arcrole/similar-tuples"
_REQUIRES_ELEMENT = "http://www.xbrl.org/2003/arcrole/requires-element"


class DefinitionValidator(BaseValidator):
    """Validator for XBRL 2.1 definition linkbase rules.

    Implements 5 checks covering relationship integrity, circular
    references, concept existence, and relationship semantics.
    """

    def __init__(self, instance: XBRLInstance) -> None:
        super().__init__(instance)

    def validate(self) -> list[ValidationMessage]:
        """Run all 5 definition linkbase checks and return messages."""
        self._messages.clear()

        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return []

        checks = [
            self._check_0001_undeclared_concept,
            self._check_0002_circular_definition,
            self._check_0003_invalid_arcrole,
            self._check_0004_essence_alias_type_mismatch,
            self._check_0005_duplicate_definition_arc,
        ]
        for check in checks:
            try:
                check()
            except Exception:
                self._logger.exception("Check %s failed unexpectedly", check.__name__)
        return list(self._messages)

    def _get_definition_arcs(self) -> list[ArcModel]:
        """Collect all arcs from definition linkbases."""
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return []
        arcs: list[ArcModel] = []
        for lb in taxonomy.definition_linkbases:
            arcs.extend(lb.arcs)
        return arcs

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_0001_undeclared_concept(self) -> None:
        """DEF-0001: Definition arc references undeclared concept.

        Spec: XBRL 2.1 §5.2.6 – both ends of a definition arc MUST
        reference concepts declared in the DTS.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for arc in self._get_definition_arcs():
            for concept in (arc.from_concept, arc.to_concept):
                if concept and concept not in taxonomy.concepts:
                    self.warning(
                        "DEF-0001",
                        f"Definition arc references undeclared concept "
                        f"'{concept}'",
                        concept=concept,
                    )

    def _check_0002_circular_definition(self) -> None:
        """DEF-0002: Circular reference in definition linkbase.

        Spec: XBRL 2.1 §5.2.6.1 – general-special networks MUST
        form a directed acyclic graph.
        """
        arcs = self._get_definition_arcs()
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
                    "DEF-0002",
                    f"Circular reference in definition linkbase "
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

    def _check_0003_invalid_arcrole(self) -> None:
        """DEF-0003: Definition arc uses undeclared arcrole.

        Spec: XBRL 2.1 §5.2.6 – arcroles used in definition linkbases
        MUST be declared in the DTS or be standard XBRL arcroles.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        standard_arcroles = {
            _GENERAL_SPECIAL, _ESSENCE_ALIAS, _SIMILAR_TUPLES,
            _REQUIRES_ELEMENT,
            "http://xbrl.org/arcrole/2008/variable-set",
            "http://xbrl.org/arcrole/2008/variable-filter",
            "http://xbrl.org/arcrole/2014/table-breakdown",
            "http://xbrl.org/arcrole/2014/breakdown-tree",
            "http://xbrl.org/int/dim/arcrole/all",
            "http://xbrl.org/int/dim/arcrole/notAll",
            "http://xbrl.org/int/dim/arcrole/hypercube-dimension",
            "http://xbrl.org/int/dim/arcrole/dimension-domain",
            "http://xbrl.org/int/dim/arcrole/domain-member",
            "http://xbrl.org/int/dim/arcrole/dimension-default",
        }
        for arc in self._get_definition_arcs():
            if (
                arc.arcrole
                and arc.arcrole not in standard_arcroles
                and arc.arcrole not in taxonomy.arcrole_types
            ):
                self.warning(
                    "DEF-0003",
                    f"Definition arc uses undeclared arcrole "
                    f"'{arc.arcrole}'",
                )

    def _check_0004_essence_alias_type_mismatch(self) -> None:
        """DEF-0004: Essence-alias relationship type mismatch.

        Spec: XBRL 2.1 §5.2.6.2 – concepts linked by an
        essence-alias arc MUST have compatible data types.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for arc in self._get_definition_arcs():
            if arc.arcrole != _ESSENCE_ALIAS:
                continue
            from_cdef = taxonomy.concepts.get(arc.from_concept)
            to_cdef = taxonomy.concepts.get(arc.to_concept)
            if from_cdef is None or to_cdef is None:
                continue
            if from_cdef.data_type and to_cdef.data_type:
                if from_cdef.data_type != to_cdef.data_type:
                    self.warning(
                        "DEF-0004",
                        f"Essence-alias relationship between "
                        f"'{arc.from_concept}' ({from_cdef.data_type}) "
                        f"and '{arc.to_concept}' ({to_cdef.data_type}) "
                        f"have different data types",
                        concept=arc.from_concept,
                    )

    def _check_0005_duplicate_definition_arc(self) -> None:
        """DEF-0005: Duplicate definition arc.

        Spec: XBRL 2.1 §3.5.3.9.6 – equivalent arcs (same from/to,
        arcrole, and attributes) are redundant.
        """
        seen: set[tuple[str, str, str]] = set()
        for arc in self._get_definition_arcs():
            key = (arc.from_concept, arc.to_concept, arc.arcrole)
            if key in seen:
                self.warning(
                    "DEF-0005",
                    f"Duplicate definition arc from '{arc.from_concept}' "
                    f"to '{arc.to_concept}' with arcrole "
                    f"'{arc.arcrole}'",
                    concept=arc.from_concept,
                )
            seen.add(key)
