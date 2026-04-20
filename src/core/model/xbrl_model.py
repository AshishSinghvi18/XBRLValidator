"""Central XBRL data model.

Defines all core dataclasses used throughout the validation engine:
contexts, units, facts, footnotes, taxonomy structures, and the
top-level :class:`XBRLInstance` container.

Design principles:
- All numeric values use :class:`~decimal.Decimal`, **never** ``float``.
- Full type hints on every field and method.
- Dataclass-based for clarity, immutability hints, and serialization.

Spec references:
- XBRL 2.1 §4.7 (contexts / periods)
- XBRL 2.1 §4.8 (units)
- XBRL 2.1 §4.6 (facts / items)
- XBRL Dimensions 1.0 §2 (dimensional qualifiers)
- Inline XBRL 1.1 §4 (hidden facts, continuations)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Optional

from src.core.types import (
    BalanceType,
    ContextID,
    DimensionKey,
    FactID,
    InputFormat,
    LinkbaseType,
    PeriodType,
    QName,
    Severity,
    UnitID,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context-related models
# ---------------------------------------------------------------------------


@dataclass
class Period:
    """XBRL period (XBRL 2.1 §4.7.2).

    Attributes:
        period_type: One of INSTANT, DURATION, or FOREVER.
        instant: Date for instant periods.
        start_date: Start date for duration periods.
        end_date: End date for duration periods.
    """

    period_type: PeriodType
    instant: date | None = None
    start_date: date | None = None
    end_date: date | None = None


@dataclass
class EntityIdentifier:
    """Entity identifier (XBRL 2.1 §4.7.1).

    Attributes:
        scheme: The identification scheme URI.
        identifier: The entity identifier value.
    """

    scheme: str
    identifier: str


@dataclass
class DimensionMember:
    """A single dimension-member pair on a context.

    Attributes:
        dimension: QName of the dimension axis.
        member: QName of the domain member.
        is_typed: Whether this is a typed dimension.
        typed_value: Raw typed-dimension value (if typed).
    """

    dimension: str  # QName
    member: str  # QName
    is_typed: bool = False
    typed_value: str | None = None


@dataclass
class Context:
    """XBRL context element (XBRL 2.1 §4.7).

    Attributes:
        id: Context identifier.
        entity: Entity identifier (scheme + value).
        period: Reporting period.
        segment_dims: Dimensional qualifiers from ``<segment>``.
        scenario_dims: Dimensional qualifiers from ``<scenario>``.
    """

    id: ContextID
    entity: EntityIdentifier
    period: Period
    segment_dims: list[DimensionMember] = field(default_factory=list)
    scenario_dims: list[DimensionMember] = field(default_factory=list)

    @property
    def dimension_key(self) -> DimensionKey:
        """Unique key for dimensional equivalence.

        Returns a sorted, hashable tuple of (dimension, member) pairs
        from both segment and scenario dimensions.
        """
        pairs: list[tuple[str, str]] = []
        for dm in self.all_dimensions:
            val = dm.typed_value if dm.is_typed else dm.member
            pairs.append((dm.dimension, val or ""))
        return tuple(sorted(pairs))

    @property
    def all_dimensions(self) -> list[DimensionMember]:
        """All dimensional qualifiers (segment + scenario)."""
        return self.segment_dims + self.scenario_dims

    def is_dimensional_equivalent(self, other: "Context") -> bool:
        """Check if two contexts are dimensionally equivalent.

        Two contexts are equivalent when they share the same entity,
        period, and dimension key.

        Args:
            other: The other context to compare.

        Returns:
            ``True`` if dimensionally equivalent.
        """
        return (
            self.entity.scheme == other.entity.scheme
            and self.entity.identifier == other.entity.identifier
            and self.period.period_type == other.period.period_type
            and self.period.instant == other.period.instant
            and self.period.start_date == other.period.start_date
            and self.period.end_date == other.period.end_date
            and self.dimension_key == other.dimension_key
        )


# ---------------------------------------------------------------------------
# Unit-related models
# ---------------------------------------------------------------------------


@dataclass
class UnitMeasure:
    """A single measure QName within a unit (XBRL 2.1 §4.8).

    Attributes:
        namespace: Namespace URI of the measure.
        local_name: Local part of the measure QName.
    """

    namespace: str
    local_name: str


@dataclass
class Unit:
    """XBRL unit element (XBRL 2.1 §4.8).

    Attributes:
        id: Unit identifier.
        measures: Simple-unit measures.
        divide_numerator: Numerator measures (for divide units).
        divide_denominator: Denominator measures (for divide units).
    """

    id: UnitID
    measures: list[UnitMeasure] = field(default_factory=list)
    divide_numerator: list[UnitMeasure] = field(default_factory=list)
    divide_denominator: list[UnitMeasure] = field(default_factory=list)

    @property
    def is_divide(self) -> bool:
        """Whether this unit uses a divide (numerator/denominator) form."""
        return bool(self.divide_numerator or self.divide_denominator)

    @property
    def is_monetary(self) -> bool:
        """Whether the unit represents a monetary measure (ISO 4217)."""
        iso4217 = "http://www.xbrl.org/2003/iso4217"
        for m in self.measures:
            if m.namespace == iso4217:
                return True
        return False

    @property
    def is_pure(self) -> bool:
        """Whether the unit is the XBRL ``pure`` measure."""
        for m in self.measures:
            if m.local_name == "pure":
                return True
        return False


# ---------------------------------------------------------------------------
# Fact
# ---------------------------------------------------------------------------


@dataclass
class Fact:
    """A single XBRL fact / item (XBRL 2.1 §4.6).

    Attributes:
        id: Optional fact identifier.
        concept: Concept QName (Clark or prefixed form).
        context_ref: ID of the associated context.
        context: Resolved context object (populated during model build).
        unit_ref: ID of the associated unit (numeric facts).
        unit: Resolved unit object (populated during model build).
        value: Raw string value.
        numeric_value: Parsed Decimal value (**never** ``float``).
        is_nil: ``True`` if ``xsi:nil="true"``.
        is_numeric: ``True`` if the concept type is numeric.
        decimals: ``decimals`` attribute value.
        precision: ``precision`` attribute value.
        language: ``xml:lang`` attribute.
        source_line: Line number in the source file.
        source_file: Path of the source file.
        is_hidden: ``True`` if the fact comes from ``ix:hidden``.
        footnote_refs: IDs of associated footnotes.
    """

    id: FactID | None
    concept: QName
    context_ref: ContextID
    context: Context | None = None
    unit_ref: UnitID | None = None
    unit: Unit | None = None
    value: str | None = None
    numeric_value: Decimal | None = None  # NEVER float!
    is_nil: bool = False
    is_numeric: bool = False
    decimals: str | None = None
    precision: str | None = None
    language: str | None = None
    source_line: int = 0
    source_file: str = ""
    is_hidden: bool = False
    footnote_refs: list[str] = field(default_factory=list)

    @property
    def duplicate_key(self) -> tuple:
        """Key for duplicate fact detection.

        Returns:
            ``(concept, context_ref, unit_ref, language)``
        """
        return (self.concept, self.context_ref, self.unit_ref, self.language)

    @property
    def rounded_value(self) -> Decimal | None:
        """Value rounded according to the ``decimals`` attribute.

        Returns:
            The rounded :class:`Decimal` value, or ``None`` if the fact
            is non-numeric, nil, or has no decimals attribute.
        """
        if self.numeric_value is None or self.is_nil:
            return None
        if self.decimals is None or self.decimals.upper() == "INF":
            return self.numeric_value
        try:
            dec_places = int(self.decimals)
        except (ValueError, TypeError):
            return self.numeric_value
        try:
            if dec_places >= 0:
                quant = Decimal(10) ** -dec_places
            else:
                quant = Decimal(10) ** (-dec_places)
            return self.numeric_value.quantize(quant, rounding=ROUND_HALF_UP)
        except (InvalidOperation, OverflowError):
            return self.numeric_value


# ---------------------------------------------------------------------------
# Footnotes
# ---------------------------------------------------------------------------


@dataclass
class Footnote:
    """XBRL footnote (XBRL 2.1 §4.11).

    Attributes:
        id: Footnote element id.
        role: Footnote role URI.
        language: Language code (xml:lang).
        content: Text content of the footnote.
        fact_refs: IDs of facts linked to this footnote.
    """

    id: str | None
    role: str
    language: str
    content: str
    fact_refs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation messages
# ---------------------------------------------------------------------------


@dataclass
class ValidationMessage:
    """A single validation finding.

    Attributes:
        code: Machine-readable error/warning code.
        severity: Severity level.
        message: Human-readable description.
        concept: Related concept QName (if applicable).
        context_id: Related context ID (if applicable).
        fact_id: Related fact ID (if applicable).
        location: Free-form location description.
        source_file: Source file path.
        source_line: Source line number.
        details: Additional structured details.
        fix_suggestion: Suggested fix text.
        rule_source: Identifier of the validation rule that triggered this.
    """

    code: str
    severity: Severity
    message: str
    concept: str | None = None
    context_id: str | None = None
    fact_id: str | None = None
    location: str | None = None
    source_file: str | None = None
    source_line: int | None = None
    details: dict[str, Any] = field(default_factory=dict)
    fix_suggestion: str | None = None
    rule_source: str | None = None


# ---------------------------------------------------------------------------
# Taxonomy models
# ---------------------------------------------------------------------------


@dataclass
class ConceptDefinition:
    """Definition of a taxonomy concept.

    Attributes:
        qname: Fully-qualified name (Clark notation).
        namespace: Namespace URI.
        local_name: Local part of the name.
        data_type: XSD data type.
        period_type: Required period type.
        balance_type: Debit/credit balance (monetary items).
        abstract: Whether the concept is abstract.
        nillable: Whether the concept is nillable.
        substitution_group: Substitution group (e.g. ``xbrli:item``).
        type_is_numeric: Derived flag for numeric types.
        type_is_textblock: Derived flag for text-block types.
        type_is_enum: Derived flag for enumeration types.
        labels: Nested dict ``{role: {lang: label_text}}``.
        references: List of reference part dicts.
    """

    qname: QName
    namespace: str
    local_name: str
    data_type: str = ""
    period_type: PeriodType | None = None
    balance_type: BalanceType | None = None
    abstract: bool = False
    nillable: bool = False
    substitution_group: str = ""
    type_is_numeric: bool = False
    type_is_textblock: bool = False
    type_is_enum: bool = False
    labels: dict[str, dict[str, str]] = field(default_factory=dict)
    references: list[dict[str, str]] = field(default_factory=list)


@dataclass
class ArcModel:
    """A relationship arc from a linkbase.

    Attributes:
        arc_type: Local name of the arc element.
        arcrole: Arcrole URI defining the relationship semantics.
        from_concept: Source concept QName.
        to_concept: Target concept QName.
        order: Presentation order.
        weight: Calculation weight (Decimal, never float).
        priority: Arc priority for prohibition/override.
        use: ``"optional"`` or ``"prohibited"``.
        preferred_label: Preferred label role URI.
    """

    arc_type: str
    arcrole: str
    from_concept: QName
    to_concept: QName
    order: float = 1.0
    weight: Decimal | None = None
    priority: int = 0
    use: str = "optional"
    preferred_label: str | None = None


@dataclass
class LinkbaseModel:
    """A single linkbase (or extended link) with its arcs.

    Attributes:
        linkbase_type: Type of linkbase (calculation, presentation, etc.).
        role_uri: Extended link role URI.
        arcs: List of arcs in this linkbase.
    """

    linkbase_type: LinkbaseType
    role_uri: str
    arcs: list[ArcModel] = field(default_factory=list)


@dataclass
class HypercubeModel:
    """A dimensional hypercube definition.

    Attributes:
        qname: QName of the hypercube concept.
        dimensions: List of dimension QNames.
        is_closed: Whether the hypercube is closed.
        context_element: ``"segment"`` or ``"scenario"``.
        domain_members: Dimension QName → list of valid member QNames.
    """

    qname: QName
    dimensions: list[QName] = field(default_factory=list)
    is_closed: bool = False
    context_element: str = "segment"
    domain_members: dict[QName, list[QName]] = field(default_factory=dict)


@dataclass
class TaxonomyModel:
    """Complete taxonomy model built from a DTS.

    Attributes:
        concepts: QName → ConceptDefinition mapping.
        role_types: Role URI → definition.
        arcrole_types: Arcrole URI → definition.
        calculation_linkbases: Calculation linkbases.
        presentation_linkbases: Presentation linkbases.
        definition_linkbases: Definition linkbases.
        label_linkbases: Label linkbases.
        reference_linkbases: Reference linkbases.
        namespaces: Prefix → URI mapping collected from the DTS.
        dimension_defaults: Dimension QName → default member QName.
        hypercubes: Dimensional hypercube definitions.
    """

    concepts: dict[QName, ConceptDefinition] = field(default_factory=dict)
    role_types: dict[str, str] = field(default_factory=dict)
    arcrole_types: dict[str, str] = field(default_factory=dict)
    calculation_linkbases: list[LinkbaseModel] = field(default_factory=list)
    presentation_linkbases: list[LinkbaseModel] = field(default_factory=list)
    definition_linkbases: list[LinkbaseModel] = field(default_factory=list)
    label_linkbases: list[LinkbaseModel] = field(default_factory=list)
    reference_linkbases: list[LinkbaseModel] = field(default_factory=list)
    namespaces: dict[str, str] = field(default_factory=dict)
    dimension_defaults: dict[QName, QName] = field(default_factory=dict)
    hypercubes: list[HypercubeModel] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level instance model
# ---------------------------------------------------------------------------


@dataclass
class XBRLInstance:
    """Central XBRL instance model.

    Supports dual mode:

    - **Mode 1 (small)**: facts in list, indexes as dicts.
    - **Mode 2 (large)**: facts in FactStore, values read on-demand.

    Attributes:
        file_path: Path to the source instance file.
        format_type: Detected input format.
        contexts: Context ID → Context mapping.
        units: Unit ID → Unit mapping.
        facts: In-memory fact list (Mode 1).
        footnotes: Parsed footnotes.
        taxonomy: Associated taxonomy model.
        schema_refs: Schema reference URLs.
        namespaces: Prefix → URI namespace mapping.
        fact_store: Optional FactStore (Mode 2).
        value_reader: Optional MMapReader or ChunkedReader (Mode 2).
    """

    file_path: str = ""
    format_type: InputFormat = InputFormat.UNKNOWN
    contexts: dict[ContextID, Context] = field(default_factory=dict)
    units: dict[UnitID, Unit] = field(default_factory=dict)
    facts: list[Fact] = field(default_factory=list)
    footnotes: list[Footnote] = field(default_factory=list)
    taxonomy: TaxonomyModel | None = None
    schema_refs: list[str] = field(default_factory=list)
    namespaces: dict[str, str] = field(default_factory=dict)

    # Large-file mode
    fact_store: Any | None = None  # Optional[FactStore]
    value_reader: Any | None = None  # Optional[MMapReader | ChunkedReader]
    _mode: str = "memory"

    # In-memory indexes (built lazily)
    _by_concept: dict[QName, list[Fact]] = field(default_factory=dict)
    _by_context: dict[ContextID, list[Fact]] = field(default_factory=dict)
    _by_unit: dict[UnitID, list[Fact]] = field(default_factory=dict)

    def build_indexes(self) -> None:
        """Build in-memory lookup indexes from the facts list."""
        self._by_concept.clear()
        self._by_context.clear()
        self._by_unit.clear()
        for fact in self.facts:
            self._by_concept.setdefault(fact.concept, []).append(fact)
            self._by_context.setdefault(fact.context_ref, []).append(fact)
            if fact.unit_ref:
                self._by_unit.setdefault(fact.unit_ref, []).append(fact)
        logger.debug(
            "Built indexes: %d concept keys, %d context keys, %d unit keys",
            len(self._by_concept),
            len(self._by_context),
            len(self._by_unit),
        )

    def get_facts_by_concept(self, concept: QName) -> list[Fact]:
        """Get facts by concept QName.  Works in both modes.

        Args:
            concept: The concept QName to look up.

        Returns:
            List of matching facts (may be empty).
        """
        if self._by_concept:
            return list(self._by_concept.get(concept, []))
        return [f for f in self.facts if f.concept == concept]

    def get_facts_by_context(self, context_id: ContextID) -> list[Fact]:
        """Get facts by context ID.

        Args:
            context_id: The context identifier.

        Returns:
            List of matching facts (may be empty).
        """
        if self._by_context:
            return list(self._by_context.get(context_id, []))
        return [f for f in self.facts if f.context_ref == context_id]

    def get_facts_by_unit(self, unit_id: UnitID) -> list[Fact]:
        """Get facts by unit ID.

        Args:
            unit_id: The unit identifier.

        Returns:
            List of matching facts (may be empty).
        """
        if self._by_unit:
            return list(self._by_unit.get(unit_id, []))
        return [f for f in self.facts if f.unit_ref == unit_id]

    @property
    def fact_count(self) -> int:
        """Total number of facts in the instance."""
        if self.fact_store is not None:
            return self.fact_store.count
        return len(self.facts)

    @property
    def is_large_file_mode(self) -> bool:
        """Whether the instance is in large-file (store-backed) mode."""
        return self._mode == "store"
