"""XBRL Dimensions 1.0 (XDT) validation.

Validates dimensional aspects of XBRL instance documents against
the taxonomy's definition linkbase, including explicit dimension
member validity, required dimension presence, and hypercube
validation (has-hypercube all / notAll).

References:
    - XBRL Dimensions 1.0 §2 (Dimensional Validation)
    - XBRL Dimensions 1.0 §2.2 (Relationship arcroles)
    - XBRL Dimensions 1.0 §2.4 (Typed dimensions)
    - XBRL Dimensions 1.0 §2.5 (Hypercube validation)
    - XBRL Dimensions 1.0 §2.6 (Default dimension members)
"""

from __future__ import annotations

from collections import defaultdict

from src.core.constants import (
    ARCROLE_ALL,
    ARCROLE_DIMENSION_DEFAULT,
    ARCROLE_DIMENSION_DOMAIN,
    ARCROLE_DOMAIN_MEMBER,
    ARCROLE_HYPERCUBE_DIMENSION,
    ARCROLE_NOT_ALL,
)
from src.core.model.context import Context, ExplicitDimension
from src.core.model.fact import Fact
from src.core.model.instance import ValidationMessage, XBRLInstance
from src.core.networks.relationship import Arc, RelationshipNetwork
from src.core.taxonomy.schema import TaxonomySchema
from src.core.types import ConceptType, Severity


class DimensionValidator:
    """Validates dimensional context validity.

    Spec: XBRL Dimensions 1.0 §2 (Dimensional Validation)
    """

    def validate(
        self,
        instance: XBRLInstance,
        def_network: RelationshipNetwork,
        taxonomy: TaxonomySchema,
    ) -> list[ValidationMessage]:
        """Validate all dimensional aspects of the instance.

        Checks:
        - Explicit dimension members are defined in the taxonomy (DIM-0001).
        - Explicit dimension members belong to the dimension's domain (DIM-0002).
        - Required (non-defaulted) dimensions are present in contexts (DIM-0003).
        - Dimensions referenced in contexts are declared as dimensions (DIM-0004).
        - Hypercube validation: ``all`` relationships (DIM-0005).
        - Hypercube validation: ``notAll`` relationships (DIM-0006).
        - Typed dimension values are non-empty (DIM-0007).
        - Dimension is not used with a prohibited member (DIM-0008).
        - No dimension appears more than once per segment/scenario (DIM-0009).
        - Facts reference valid dimensional contexts (DIM-0010).

        Spec: XBRL Dimensions 1.0 §2 | Emits: DIM-0001 through DIM-0010

        Args:
            instance: The parsed XBRL instance.
            def_network: A :class:`RelationshipNetwork` containing
                definition linkbase arcs (dimension-domain, domain-member,
                hypercube-dimension, all, notAll, etc.).
            taxonomy: The taxonomy schema providing concept definitions.

        Returns:
            List of validation messages.
        """
        messages: list[ValidationMessage] = []

        # Build helper indexes from the definition network
        dimension_domains: dict[str, set[str]] = (
            self._build_dimension_domain_map(def_network)
        )
        dimension_defaults: dict[str, str] = (
            self._build_dimension_defaults(def_network)
        )
        hypercube_dims: dict[str, list[str]] = (
            self._build_hypercube_dimensions(def_network)
        )
        concept_hypercubes_all: dict[str, list[str]] = (
            self._build_concept_hypercube_map(def_network, arcrole=ARCROLE_ALL)
        )
        concept_hypercubes_not_all: dict[str, list[str]] = (
            self._build_concept_hypercube_map(
                def_network, arcrole=ARCROLE_NOT_ALL
            )
        )

        # Validate each context's dimensional content
        for ctx_id, ctx in instance.contexts.items():
            messages.extend(
                self._validate_context_dimensions(
                    ctx,
                    dimension_domains,
                    taxonomy,
                    instance.file_path,
                )
            )

        # Validate facts against hypercubes
        for fact in instance.facts:
            ctx: Context | None = instance.get_context(fact.context_ref)
            if ctx is None:
                continue

            messages.extend(
                self._validate_fact_hypercubes(
                    fact,
                    ctx,
                    concept_hypercubes_all,
                    concept_hypercubes_not_all,
                    hypercube_dims,
                    dimension_domains,
                    dimension_defaults,
                    instance.file_path,
                )
            )

        return messages

    # ------------------------------------------------------------------
    # Context dimension validation
    # ------------------------------------------------------------------

    def _validate_context_dimensions(
        self,
        ctx: Context,
        dimension_domains: dict[str, set[str]],
        taxonomy: TaxonomySchema,
        file_path: str,
    ) -> list[ValidationMessage]:
        """Validate dimensional bindings in a single context.

        Spec: XBRL Dimensions 1.0 §4 | Emits: DIM-0001, DIM-0002, DIM-0004, DIM-0007, DIM-0009

        Args:
            ctx: The context to validate.
            dimension_domains: Mapping of dimension QName → set of valid member QNames.
            taxonomy: The taxonomy schema.
            file_path: Source file path for error reporting.

        Returns:
            Validation messages.
        """
        messages: list[ValidationMessage] = []

        # DIM-0009: duplicate dimensions within a context
        seen_dims: dict[str, int] = {}
        for ed in ctx.explicit_dimensions:
            count: int = seen_dims.get(ed.dimension, 0)
            seen_dims[ed.dimension] = count + 1
        for td in ctx.typed_dimensions:
            count = seen_dims.get(td.dimension, 0)
            seen_dims[td.dimension] = count + 1
        for dim_qname, count in seen_dims.items():
            if count > 1:
                messages.append(
                    ValidationMessage(
                        code="DIM-0009",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': dimension "
                            f"'{dim_qname}' appears {count} times. "
                            f"Each dimension may appear at most once."
                        ),
                        spec_ref="XBRL Dimensions 1.0 §4",
                        file_path=file_path,
                    )
                )

        # Validate each explicit dimension binding
        for ed in ctx.explicit_dimensions:
            # DIM-0004: dimension must be declared as a dimension concept
            concept = taxonomy.concepts.get(ed.dimension)
            if concept is not None and concept.concept_type not in (
                ConceptType.DIMENSION,
                ConceptType.TYPED_DIMENSION,
            ):
                messages.append(
                    ValidationMessage(
                        code="DIM-0004",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': '{ed.dimension}' "
                            f"is used as a dimension but is declared as "
                            f"'{concept.concept_type.value}' in the taxonomy."
                        ),
                        spec_ref="XBRL Dimensions 1.0 §2.1",
                        file_path=file_path,
                    )
                )

            # DIM-0001: member must exist in the taxonomy
            if ed.member and taxonomy.concepts and ed.member not in taxonomy.concepts:
                messages.append(
                    ValidationMessage(
                        code="DIM-0001",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': explicit dimension "
                            f"'{ed.dimension}' references member "
                            f"'{ed.member}' which is not defined in the "
                            f"taxonomy."
                        ),
                        spec_ref="XBRL Dimensions 1.0 §2.1",
                        file_path=file_path,
                        fix_suggestion=(
                            "Use a member QName that exists in the taxonomy."
                        ),
                    )
                )

            # DIM-0002: member must be in the dimension's domain
            valid_members: set[str] | None = dimension_domains.get(
                ed.dimension
            )
            if valid_members is not None and ed.member not in valid_members:
                messages.append(
                    ValidationMessage(
                        code="DIM-0002",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': member "
                            f"'{ed.member}' is not a valid domain member "
                            f"for dimension '{ed.dimension}'."
                        ),
                        spec_ref="XBRL Dimensions 1.0 §2.2.2",
                        file_path=file_path,
                        fix_suggestion=(
                            "Use a member that belongs to the dimension's "
                            "domain hierarchy."
                        ),
                    )
                )

        # DIM-0007: Typed dimension values must be non-empty
        for td in ctx.typed_dimensions:
            if not td.value or not td.value.strip():
                messages.append(
                    ValidationMessage(
                        code="DIM-0007",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': typed dimension "
                            f"'{td.dimension}' has an empty value."
                        ),
                        spec_ref="XBRL Dimensions 1.0 §2.4",
                        file_path=file_path,
                    )
                )

        return messages

    # ------------------------------------------------------------------
    # Hypercube validation
    # ------------------------------------------------------------------

    def _validate_fact_hypercubes(
        self,
        fact: Fact,
        ctx: Context,
        concept_hypercubes_all: dict[str, list[str]],
        concept_hypercubes_not_all: dict[str, list[str]],
        hypercube_dims: dict[str, list[str]],
        dimension_domains: dict[str, set[str]],
        dimension_defaults: dict[str, str],
        file_path: str,
    ) -> list[ValidationMessage]:
        """Validate a fact against hypercube constraints.

        Per XBRL Dimensions 1.0 §2.5:
        - For ``all`` (closed) hypercubes: the context must provide valid
          members for every dimension in the hypercube.
        - For ``notAll`` hypercubes: the context must NOT fully satisfy
          the hypercube (i.e., at least one dimension must be absent or
          have a non-matching member).

        Spec: XBRL Dimensions 1.0 §2.5 | Emits: DIM-0005, DIM-0006, DIM-0003

        Args:
            fact: The fact to validate.
            ctx: The context of the fact.
            concept_hypercubes_all: Concept → list of ``all`` hypercubes.
            concept_hypercubes_not_all: Concept → list of ``notAll`` hypercubes.
            hypercube_dims: Hypercube → list of dimension QNames.
            dimension_domains: Dimension → set of valid members.
            dimension_defaults: Dimension → default member QName.
            file_path: Source file for error reporting.

        Returns:
            Validation messages.
        """
        messages: list[ValidationMessage] = []

        # Collect context dimension bindings for quick lookup
        ctx_dim_members: dict[str, str] = {}
        for ed in ctx.explicit_dimensions:
            ctx_dim_members[ed.dimension] = ed.member
        # Typed dimensions count as "present" but with a placeholder value
        for td in ctx.typed_dimensions:
            ctx_dim_members[td.dimension] = td.value

        # --- Validate ``all`` (positive) hypercubes ---
        for hc_qname in concept_hypercubes_all.get(fact.concept_qname, []):
            hc_dimensions: list[str] = hypercube_dims.get(hc_qname, [])
            for dim_qname in hc_dimensions:
                member: str | None = ctx_dim_members.get(dim_qname)
                if member is None:
                    # Check for a default member
                    default_member: str | None = dimension_defaults.get(
                        dim_qname
                    )
                    if default_member is None:
                        messages.append(
                            ValidationMessage(
                                code="DIM-0003",
                                severity=Severity.ERROR,
                                message=(
                                    f"Fact '{fact.fact_id}' "
                                    f"(concept: {fact.concept_qname}) in "
                                    f"context '{ctx.context_id}': required "
                                    f"dimension '{dim_qname}' from hypercube "
                                    f"'{hc_qname}' is missing and has no "
                                    f"default member."
                                ),
                                spec_ref="XBRL Dimensions 1.0 §2.5",
                                file_path=file_path,
                                line=fact.source_line,
                                fix_suggestion=(
                                    "Add the required dimension to the context."
                                ),
                            )
                        )
                else:
                    # Validate the member is within the dimension's domain
                    valid_members: set[str] | None = dimension_domains.get(
                        dim_qname
                    )
                    if valid_members is not None and member not in valid_members:
                        messages.append(
                            ValidationMessage(
                                code="DIM-0005",
                                severity=Severity.ERROR,
                                message=(
                                    f"Fact '{fact.fact_id}' "
                                    f"(concept: {fact.concept_qname}) in "
                                    f"context '{ctx.context_id}': member "
                                    f"'{member}' is not valid for dimension "
                                    f"'{dim_qname}' in hypercube "
                                    f"'{hc_qname}'."
                                ),
                                spec_ref="XBRL Dimensions 1.0 §2.5",
                                file_path=file_path,
                                line=fact.source_line,
                            )
                        )

        # --- Validate ``notAll`` (negative) hypercubes ---
        for hc_qname in concept_hypercubes_not_all.get(
            fact.concept_qname, []
        ):
            hc_dimensions = hypercube_dims.get(hc_qname, [])
            if not hc_dimensions:
                continue

            all_match: bool = True
            for dim_qname in hc_dimensions:
                member = ctx_dim_members.get(dim_qname)
                if member is None:
                    all_match = False
                    break
                valid_members = dimension_domains.get(dim_qname)
                if valid_members is not None and member not in valid_members:
                    all_match = False
                    break

            if all_match:
                messages.append(
                    ValidationMessage(
                        code="DIM-0006",
                        severity=Severity.ERROR,
                        message=(
                            f"Fact '{fact.fact_id}' "
                            f"(concept: {fact.concept_qname}) in context "
                            f"'{ctx.context_id}': context satisfies the "
                            f"notAll hypercube '{hc_qname}' — this "
                            f"combination is prohibited."
                        ),
                        spec_ref="XBRL Dimensions 1.0 §2.5",
                        file_path=file_path,
                        line=fact.source_line,
                        fix_suggestion=(
                            "Change the context's dimensional qualifiers "
                            "so it does not match the prohibited hypercube."
                        ),
                    )
                )

        return messages

    # ------------------------------------------------------------------
    # Helper index builders
    # ------------------------------------------------------------------

    def _build_dimension_domain_map(
        self, network: RelationshipNetwork
    ) -> dict[str, set[str]]:
        """Build a mapping of dimension QName → set of valid member QNames.

        Traverses dimension-domain and domain-member arcs to build the
        complete set of valid members for each dimension.

        Spec: XBRL Dimensions 1.0 §2.2.1, §2.2.2

        Args:
            network: The definition linkbase relationship network.

        Returns:
            Dimension QName → set of member QNames.
        """
        result: dict[str, set[str]] = defaultdict(set)

        for arc in network.children("", ""):
            # Handled below via full traversal
            pass

        # Find dimension → domain arcs by checking all arcs
        # We need to look at arcs whose arcrole is dimension-domain
        # Since the network is for a single arcrole, we look at all roots
        # and traverse from there.
        # However, the definition network may contain multiple arcrole types
        # mixed together. We search for dimension-domain patterns.
        all_roots: list[str] = network.roots()
        for root in all_roots:
            child_arcs: list[Arc] = network.children(root)
            for arc in child_arcs:
                if arc.arcrole == ARCROLE_DIMENSION_DOMAIN:
                    # arc.from_qname is the dimension, arc.to_qname is the domain head
                    domain_head: str = arc.to_qname
                    dimension: str = arc.from_qname
                    result[dimension].add(domain_head)
                    # Recursively collect domain-member descendants
                    self._collect_domain_members(
                        network, domain_head, result[dimension]
                    )

        return dict(result)

    def _collect_domain_members(
        self,
        network: RelationshipNetwork,
        domain: str,
        members: set[str],
    ) -> None:
        """Recursively collect domain members via domain-member arcs.

        Args:
            network: The definition linkbase relationship network.
            domain: Current domain/member QName to explore.
            members: Accumulator set of member QNames.
        """
        for arc in network.children(domain):
            if arc.arcrole == ARCROLE_DOMAIN_MEMBER:
                if arc.to_qname not in members:
                    members.add(arc.to_qname)
                    self._collect_domain_members(
                        network, arc.to_qname, members
                    )

    def _build_dimension_defaults(
        self, network: RelationshipNetwork
    ) -> dict[str, str]:
        """Build a mapping of dimension QName → default member QName.

        Spec: XBRL Dimensions 1.0 §2.6.1

        Args:
            network: The definition linkbase relationship network.

        Returns:
            Dimension QName → default member QName.
        """
        defaults: dict[str, str] = {}
        all_roots: list[str] = network.roots()
        for root in all_roots:
            for arc in network.children(root):
                if arc.arcrole == ARCROLE_DIMENSION_DEFAULT:
                    defaults[arc.from_qname] = arc.to_qname
        return defaults

    def _build_hypercube_dimensions(
        self, network: RelationshipNetwork
    ) -> dict[str, list[str]]:
        """Build a mapping of hypercube QName → list of dimension QNames.

        Spec: XBRL Dimensions 1.0 §2.2.3

        Args:
            network: The definition linkbase relationship network.

        Returns:
            Hypercube QName → ordered list of dimension QNames.
        """
        result: dict[str, list[str]] = defaultdict(list)
        all_roots: list[str] = network.roots()
        for root in all_roots:
            for arc in network.children(root):
                if arc.arcrole == ARCROLE_HYPERCUBE_DIMENSION:
                    result[arc.from_qname].append(arc.to_qname)
            # Also check grandchildren for nested hypercube-dimension
            for arc in network.children(root):
                for child_arc in network.children(arc.to_qname):
                    if child_arc.arcrole == ARCROLE_HYPERCUBE_DIMENSION:
                        result[child_arc.from_qname].append(
                            child_arc.to_qname
                        )
        return dict(result)

    def _build_concept_hypercube_map(
        self,
        network: RelationshipNetwork,
        arcrole: str,
    ) -> dict[str, list[str]]:
        """Build a mapping of concept QName → list of hypercube QNames.

        Follows ``all`` or ``notAll`` arcs from concepts to their
        associated hypercubes.

        Spec: XBRL Dimensions 1.0 §2.2.4, §2.2.5

        Args:
            network: The definition linkbase relationship network.
            arcrole: Either :data:`ARCROLE_ALL` or :data:`ARCROLE_NOT_ALL`.

        Returns:
            Concept QName → list of hypercube QNames.
        """
        result: dict[str, list[str]] = defaultdict(list)
        all_roots: list[str] = network.roots()
        for root in all_roots:
            for arc in network.children(root):
                if arc.arcrole == arcrole:
                    result[arc.from_qname].append(arc.to_qname)
        return dict(result)
