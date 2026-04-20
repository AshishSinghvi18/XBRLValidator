"""XBRL Dimensions 1.0 validator.

Implements 10 checks (DIM-0001 through DIM-0010) covering the
XBRL Dimensions 1.0 specification requirements.

Spec references:
- XBRL Dimensions 1.0 §2 (dimensional qualifiers)
- XBRL Dimensions 1.0 §3 (hypercubes)
- XBRL Dimensions 1.0 §4 (valid combinations)
"""

from __future__ import annotations

import logging
from typing import Iterator

from src.core.model.xbrl_model import (
    Context,
    DimensionMember,
    Fact,
    HypercubeModel,
    ValidationMessage,
    XBRLInstance,
)
from src.core.types import Severity
from src.validator.base import BaseValidator

logger = logging.getLogger(__name__)


class DimensionsValidator(BaseValidator):
    """Validator for XBRL Dimensions 1.0 specification rules.

    Implements 10 checks covering dimensional qualifiers, hypercubes,
    default dimensions, and valid dimensional combinations.
    """

    def __init__(self, instance: XBRLInstance) -> None:
        super().__init__(instance)

    def validate(self) -> list[ValidationMessage]:
        """Run all 10 dimension checks and return messages."""
        self._messages.clear()
        checks = [
            self._check_0001_invalid_dimension,
            self._check_0002_invalid_member,
            self._check_0003_default_member_in_context,
            self._check_0004_typed_dimension_empty,
            self._check_0005_duplicate_dimension_in_context,
            self._check_0006_context_not_valid_for_hypercube,
            self._check_0007_closed_hypercube_extra_dimension,
            self._check_0008_missing_required_dimension,
            self._check_0009_dimension_in_wrong_container,
            self._check_0010_orphan_dimension_member,
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

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_0001_invalid_dimension(self) -> None:
        """DIM-0001: Dimension used in context is not declared in taxonomy.

        Spec: Dimensions 1.0 §2.1 – a dimension used in a context
        segment or scenario MUST be declared as a dimension item in
        the DTS.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for ctx_id, ctx in self._instance.contexts.items():
            for dm in ctx.all_dimensions:
                if dm.dimension not in taxonomy.concepts:
                    self.error(
                        "DIM-0001",
                        f"Context '{ctx_id}' uses undeclared dimension "
                        f"'{dm.dimension}'",
                        context_id=ctx_id,
                    )

    def _check_0002_invalid_member(self) -> None:
        """DIM-0002: Member used for explicit dimension is not valid.

        Spec: Dimensions 1.0 §2.3 – explicit dimension members MUST be
        in the domain of the dimension as defined by the DTS.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for ctx_id, ctx in self._instance.contexts.items():
            for dm in ctx.all_dimensions:
                if dm.is_typed:
                    continue
                if dm.member and dm.member not in taxonomy.concepts:
                    self.error(
                        "DIM-0002",
                        f"Context '{ctx_id}': member '{dm.member}' for "
                        f"dimension '{dm.dimension}' is not in the taxonomy",
                        context_id=ctx_id,
                    )

    def _check_0003_default_member_in_context(self) -> None:
        """DIM-0003: Context should not explicitly specify the default member.

        Spec: Dimensions 1.0 §2.6.1 – if a dimension has a default
        member, using that member explicitly in a context is redundant
        and SHOULD be avoided.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        defaults = taxonomy.dimension_defaults
        for ctx_id, ctx in self._instance.contexts.items():
            for dm in ctx.all_dimensions:
                if dm.dimension in defaults and dm.member == defaults[dm.dimension]:
                    self.warning(
                        "DIM-0003",
                        f"Context '{ctx_id}' explicitly specifies the "
                        f"default member '{dm.member}' for dimension "
                        f"'{dm.dimension}'",
                        context_id=ctx_id,
                    )

    def _check_0004_typed_dimension_empty(self) -> None:
        """DIM-0004: Typed dimension value must not be empty.

        Spec: Dimensions 1.0 §2.4 – a typed dimension MUST contain
        a non-empty value element.
        """
        for ctx_id, ctx in self._instance.contexts.items():
            for dm in ctx.all_dimensions:
                if dm.is_typed and not dm.typed_value:
                    self.error(
                        "DIM-0004",
                        f"Context '{ctx_id}': typed dimension "
                        f"'{dm.dimension}' has an empty value",
                        context_id=ctx_id,
                    )

    def _check_0005_duplicate_dimension_in_context(self) -> None:
        """DIM-0005: Duplicate dimension in a single context.

        Spec: Dimensions 1.0 §2.1 – a context MUST NOT contain the
        same dimension more than once within the same container
        (segment or scenario).
        """
        for ctx_id, ctx in self._instance.contexts.items():
            for dims, container_name in [
                (ctx.segment_dims, "segment"),
                (ctx.scenario_dims, "scenario"),
            ]:
                seen: set[str] = set()
                for dm in dims:
                    if dm.dimension in seen:
                        self.error(
                            "DIM-0005",
                            f"Context '{ctx_id}': dimension "
                            f"'{dm.dimension}' appears more than once "
                            f"in {container_name}",
                            context_id=ctx_id,
                        )
                    seen.add(dm.dimension)

    def _check_0006_context_not_valid_for_hypercube(self) -> None:
        """DIM-0006: Fact's context is not valid for any applicable hypercube.

        Spec: Dimensions 1.0 §4.1 – a fact's context dimensional
        qualifiers MUST satisfy at least one applicable hypercube
        (if any are defined for the concept).
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None or not taxonomy.hypercubes:
            return
        for fact in self._iter_facts():
            ctx = self._instance.contexts.get(fact.context_ref)
            if ctx is None:
                continue
            ctx_dims = {dm.dimension for dm in ctx.all_dimensions}
            applicable_cubes = self._get_applicable_hypercubes(fact.concept)
            if not applicable_cubes:
                continue
            valid = False
            for cube in applicable_cubes:
                required = set(cube.dimensions)
                if required.issubset(ctx_dims):
                    valid = True
                    break
            if not valid:
                self.error(
                    "DIM-0006",
                    f"Fact '{fact.concept}' in context "
                    f"'{fact.context_ref}' does not satisfy any "
                    f"applicable hypercube",
                    concept=fact.concept,
                    context_id=fact.context_ref,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0007_closed_hypercube_extra_dimension(self) -> None:
        """DIM-0007: Closed hypercube rejects extra dimensions.

        Spec: Dimensions 1.0 §3.2 – when a hypercube is closed,
        contexts MUST NOT contain dimensions not listed in the hypercube.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for cube in taxonomy.hypercubes:
            if not cube.is_closed:
                continue
            cube_dims = set(cube.dimensions)
            for fact in self._iter_facts():
                ctx = self._instance.contexts.get(fact.context_ref)
                if ctx is None:
                    continue
                container_dims = (
                    ctx.segment_dims
                    if cube.context_element == "segment"
                    else ctx.scenario_dims
                )
                for dm in container_dims:
                    if dm.dimension not in cube_dims:
                        self.error(
                            "DIM-0007",
                            f"Closed hypercube '{cube.qname}' rejects "
                            f"extra dimension '{dm.dimension}' in context "
                            f"'{fact.context_ref}'",
                            concept=fact.concept,
                            context_id=fact.context_ref,
                            fact_id=fact.id,
                        )

    def _check_0008_missing_required_dimension(self) -> None:
        """DIM-0008: Required dimension missing from context.

        Spec: Dimensions 1.0 §4.2 – when a hypercube applies to a
        concept, every dimension in that hypercube MUST appear in the
        context (unless a default is defined).
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        defaults = taxonomy.dimension_defaults
        for fact in self._iter_facts():
            ctx = self._instance.contexts.get(fact.context_ref)
            if ctx is None:
                continue
            ctx_dims = {dm.dimension for dm in ctx.all_dimensions}
            for cube in self._get_applicable_hypercubes(fact.concept):
                for dim in cube.dimensions:
                    if dim not in ctx_dims and dim not in defaults:
                        self.error(
                            "DIM-0008",
                            f"Fact '{fact.concept}': required dimension "
                            f"'{dim}' from hypercube '{cube.qname}' is "
                            f"missing in context '{fact.context_ref}'",
                            concept=fact.concept,
                            context_id=fact.context_ref,
                            fact_id=fact.id,
                        )

    def _check_0009_dimension_in_wrong_container(self) -> None:
        """DIM-0009: Dimension placed in wrong container (segment/scenario).

        Spec: Dimensions 1.0 §3.1 – the ``contextElement`` attribute
        determines whether dimensions must appear in ``<segment>`` or
        ``<scenario>``.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for cube in taxonomy.hypercubes:
            expected = cube.context_element
            for ctx_id, ctx in self._instance.contexts.items():
                if expected == "segment":
                    wrong_dims = [
                        dm
                        for dm in ctx.scenario_dims
                        if dm.dimension in cube.dimensions
                    ]
                else:
                    wrong_dims = [
                        dm
                        for dm in ctx.segment_dims
                        if dm.dimension in cube.dimensions
                    ]
                for dm in wrong_dims:
                    self.error(
                        "DIM-0009",
                        f"Dimension '{dm.dimension}' in context "
                        f"'{ctx_id}' is in "
                        f"{'scenario' if expected == 'segment' else 'segment'} "
                        f"but hypercube '{cube.qname}' requires "
                        f"'{expected}'",
                        context_id=ctx_id,
                    )

    def _check_0010_orphan_dimension_member(self) -> None:
        """DIM-0010: Dimension member not valid for any hypercube.

        Spec: Dimensions 1.0 §2.3 – explicit dimension members MUST
        belong to the domain hierarchy of the dimension within an
        applicable hypercube.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for cube in taxonomy.hypercubes:
            if not cube.domain_members:
                continue
            for ctx_id, ctx in self._instance.contexts.items():
                for dm in ctx.all_dimensions:
                    if dm.is_typed or dm.dimension not in cube.domain_members:
                        continue
                    valid_members = cube.domain_members[dm.dimension]
                    if dm.member and dm.member not in valid_members:
                        self.warning(
                            "DIM-0010",
                            f"Context '{ctx_id}': member '{dm.member}' "
                            f"for dimension '{dm.dimension}' is not in "
                            f"the domain of hypercube '{cube.qname}'",
                            context_id=ctx_id,
                        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_applicable_hypercubes(self, concept: str) -> list[HypercubeModel]:
        """Return hypercubes applicable to a concept.

        A naive implementation that returns all hypercubes.  In a full
        implementation this would walk the DRS network.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return []
        return list(taxonomy.hypercubes)
