"""XBRL model dataclasses — the canonical in-memory representation.

Every numeric value uses ``decimal.Decimal`` (Rule 1: NEVER float).
All dataclasses are frozen where possible for hashability and safety.
"""

from __future__ import annotations

import decimal
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from src.core.constants import NS_ISO4217, NS_XBRLI
from src.core.types import (
    ArcroleURI,
    BalanceType,
    ContextID,
    DimensionKey,
    FactID,
    InputFormat,
    LinkbaseType,
    PeriodType,
    QName,
    RoleURI,
    Severity,
    UnitID,
)

# ---------------------------------------------------------------------------
# Period
# ---------------------------------------------------------------------------


@dataclass
class Period:
    """XBRL 2.1 §4.7.2 — period of a context."""

    period_type: PeriodType
    instant: date | None = None
    start_date: date | None = None
    end_date: date | None = None

    def equals(self, other: Period) -> bool:
        """Test structural equality per XBRL spec."""
        if self.period_type != other.period_type:
            return False
        if self.period_type == PeriodType.INSTANT:
            return self.instant == other.instant
        if self.period_type == PeriodType.DURATION:
            return self.start_date == other.start_date and self.end_date == other.end_date
        # FOREVER matches FOREVER
        return True

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Period):
            return NotImplemented
        return self.equals(other)

    def __hash__(self) -> int:
        return hash((self.period_type, self.instant, self.start_date, self.end_date))


# ---------------------------------------------------------------------------
# EntityIdentifier
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntityIdentifier:
    """XBRL 2.1 §4.7.3.1 — entity identifier within a context."""

    scheme: str
    identifier: str

    def __str__(self) -> str:
        return f"{self.scheme}:{self.identifier}"


# ---------------------------------------------------------------------------
# DimensionMember
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DimensionMember:
    """A single dimension-member pair from a context segment/scenario."""

    dimension: QName
    member: QName = ""
    typed_value: str | None = None
    is_typed: bool = False

    def __str__(self) -> str:
        if self.is_typed:
            return f"{self.dimension}=[typed:{self.typed_value}]"
        return f"{self.dimension}={self.member}"


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class Context:
    """XBRL 2.1 §4.7 — a context element."""

    id: ContextID
    entity: EntityIdentifier
    period: Period
    segment_dims: list[DimensionMember] = field(default_factory=list)
    scenario_dims: list[DimensionMember] = field(default_factory=list)

    @property
    def dimension_key(self) -> DimensionKey:
        """Sorted, hashable tuple of all (dimension, member) pairs."""
        pairs: list[tuple[str, str]] = []
        for dm in self.all_dimensions:
            val = dm.typed_value if dm.is_typed else dm.member
            pairs.append((dm.dimension, val or ""))
        return tuple(sorted(pairs))

    @property
    def all_dimensions(self) -> list[DimensionMember]:
        """All dimension members from segment and scenario."""
        return self.segment_dims + self.scenario_dims

    def is_dimensional_equivalent(self, other: Context) -> bool:
        """Test c-equal per XBRL Dimensions 1.0 §5."""
        if self.entity != other.entity:
            return False
        if not self.period.equals(other.period):
            return False
        return self.dimension_key == other.dimension_key


# ---------------------------------------------------------------------------
# UnitMeasure & Unit
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnitMeasure:
    """A single measure QName within a unit."""

    namespace: str
    local_name: str

    @property
    def clark(self) -> str:
        if self.namespace:
            return f"{{{self.namespace}}}{self.local_name}"
        return self.local_name

    def __str__(self) -> str:
        return self.clark


@dataclass
class Unit:
    """XBRL 2.1 §4.8 — a unit element."""

    id: UnitID
    measures: list[UnitMeasure] = field(default_factory=list)
    numerator_measures: list[UnitMeasure] = field(default_factory=list)
    denominator_measures: list[UnitMeasure] = field(default_factory=list)

    @property
    def is_divide(self) -> bool:
        return bool(self.numerator_measures and self.denominator_measures)

    @property
    def is_monetary(self) -> bool:
        if self.is_divide:
            return False
        return any(m.namespace == NS_ISO4217 for m in self.measures)

    @property
    def is_shares(self) -> bool:
        if self.is_divide:
            return False
        return any(
            m.namespace == NS_XBRLI and m.local_name == "shares"
            for m in self.measures
        )

    @property
    def is_pure(self) -> bool:
        if self.is_divide:
            return False
        return (
            len(self.measures) == 1
            and self.measures[0].namespace == NS_XBRLI
            and self.measures[0].local_name == "pure"
        )

    def is_equal(self, other: Unit) -> bool:
        """Test unit equality per XBRL 2.1 §4.8.2."""
        if self.is_divide != other.is_divide:
            return False
        if self.is_divide:
            return (
                sorted(m.clark for m in self.numerator_measures)
                == sorted(m.clark for m in other.numerator_measures)
                and sorted(m.clark for m in self.denominator_measures)
                == sorted(m.clark for m in other.denominator_measures)
            )
        return sorted(m.clark for m in self.measures) == sorted(
            m.clark for m in other.measures
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Unit):
            return NotImplemented
        return self.is_equal(other)

    def __hash__(self) -> int:
        if self.is_divide:
            return hash((
                tuple(sorted(m.clark for m in self.numerator_measures)),
                tuple(sorted(m.clark for m in self.denominator_measures)),
            ))
        return hash(tuple(sorted(m.clark for m in self.measures)))


# ---------------------------------------------------------------------------
# Fact
# ---------------------------------------------------------------------------


@dataclass
class Fact:
    """A reported XBRL fact — item or tuple."""

    id: FactID
    concept_qname: QName
    context_ref: ContextID | None = None
    unit_ref: UnitID | None = None
    raw_value: str = ""
    numeric_value: Decimal | None = None
    is_nil: bool = False
    is_numeric: bool = False
    is_tuple: bool = False
    decimals: int | Literal["INF"] | None = None
    precision: int | Literal["INF"] | None = None
    language: str | None = None
    source_line: int | None = None
    source_file: str = ""
    is_hidden: bool = False
    footnote_refs: list[str] = field(default_factory=list)

    @property
    def duplicate_key(self) -> tuple[Any, ...]:
        """Key for detecting duplicate facts (XBRL 2.1 §4.10)."""
        return (self.concept_qname, self.context_ref, self.unit_ref, self.language)

    @property
    def rounded_value(self) -> Decimal | None:
        """Value rounded per the decimals attribute using ROUND_HALF_UP."""
        if self.numeric_value is None:
            return None
        if self.decimals is None:
            return self.numeric_value
        if self.decimals == "INF":
            return self.numeric_value
        quantize_exp = Decimal(10) ** (-self.decimals)
        return self.numeric_value.quantize(quantize_exp, rounding=decimal.ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Footnote
# ---------------------------------------------------------------------------


@dataclass
class Footnote:
    """XBRL 2.1 §4.11 — a footnote."""

    id: str
    role: str = ""
    language: str = ""
    content: str = ""
    fact_refs: list[str] = field(default_factory=list)
    source_line: int | None = None


# ---------------------------------------------------------------------------
# ValidationMessage
# ---------------------------------------------------------------------------


@dataclass
class ValidationMessage:
    """A validation finding — error, warning, or info."""

    code: str
    severity: Severity
    message: str
    concept_qname: QName = ""
    context_id: ContextID = ""
    source_file: str = ""
    source_line: int | None = None
    details: dict[str, Any] = field(default_factory=dict)
    fix_suggestion: str = ""
    rule_source: str = ""
    arelle_equivalent_code: str = ""


# ---------------------------------------------------------------------------
# ConceptDefinition
# ---------------------------------------------------------------------------


@dataclass
class ConceptDefinition:
    """A taxonomy concept (element declaration)."""

    qname: QName
    namespace: str
    local_name: str
    data_type: QName = ""
    period_type: PeriodType = PeriodType.DURATION
    balance_type: BalanceType = BalanceType.NONE
    abstract: bool = False
    nillable: bool = False
    type_is_numeric: bool = False
    is_hypercube: bool = False
    is_dimension: bool = False
    labels: dict[str, dict[str, str]] = field(default_factory=dict)
    references: list[dict[str, str]] = field(default_factory=list)

    def get_label(
        self,
        role: str = "http://www.xbrl.org/2003/role/label",
        lang: str = "en",
    ) -> str | None:
        """Return the label for the given role and language."""
        role_labels = self.labels.get(role, {})
        return role_labels.get(lang)


# ---------------------------------------------------------------------------
# ArcModel
# ---------------------------------------------------------------------------


@dataclass
class ArcModel:
    """A single arc from a linkbase (calc, pres, def, label, ref, etc.)."""

    arc_type: str
    arcrole: ArcroleURI
    role: RoleURI = ""
    from_concept: QName = ""
    to_concept: QName = ""
    order: Decimal = Decimal("1")
    weight: Decimal = Decimal("1")
    priority: int = 0
    use: str = "optional"
    preferred_label: str = ""
    closed: bool = False
    targetRole: str = ""
    usable: bool = True


# ---------------------------------------------------------------------------
# LinkbaseModel
# ---------------------------------------------------------------------------


@dataclass
class LinkbaseModel:
    """A parsed linkbase document (or extended link within a schema)."""

    linkbase_type: LinkbaseType
    role_uri: RoleURI = ""
    arcs: list[ArcModel] = field(default_factory=list)
    source_file: str = ""


# ---------------------------------------------------------------------------
# HypercubeModel
# ---------------------------------------------------------------------------


@dataclass
class HypercubeModel:
    """XBRL Dimensions 1.0 — a hypercube."""

    qname: QName
    dimensions: list[QName] = field(default_factory=list)
    is_closed: bool = False
    context_element: str = "segment"
    targetRole: str = ""
    domain_members_by_dim: dict[QName, list[QName]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SchemaRef & LinkbaseRef
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchemaRef:
    """Reference to an external taxonomy schema."""

    href: str
    role: str = ""


@dataclass(frozen=True)
class LinkbaseRef:
    """Reference to an external linkbase document."""

    href: str
    role: str = ""
    arcrole: str = ""


# ---------------------------------------------------------------------------
# TaxonomyModel
# ---------------------------------------------------------------------------


@dataclass
class TaxonomyModel:
    """Resolved DTS (Discoverable Taxonomy Set)."""

    concepts: dict[QName, ConceptDefinition] = field(default_factory=dict)
    role_types: dict[RoleURI, str] = field(default_factory=dict)
    arcrole_types: dict[ArcroleURI, str] = field(default_factory=dict)
    calc_networks: list[LinkbaseModel] = field(default_factory=list)
    pres_networks: list[LinkbaseModel] = field(default_factory=list)
    def_networks: list[LinkbaseModel] = field(default_factory=list)
    label_linkbases: list[LinkbaseModel] = field(default_factory=list)
    dimension_defaults: dict[QName, QName] = field(default_factory=dict)
    hypercubes: dict[QName, HypercubeModel] = field(default_factory=dict)
    namespaces: dict[str, str] = field(default_factory=dict)

    def get_concept(self, qname: QName) -> ConceptDefinition | None:
        """Look up a concept by QName."""
        return self.concepts.get(qname)

    def is_numeric_concept(self, qname: QName) -> bool:
        """Return True if the concept is numeric."""
        c = self.concepts.get(qname)
        return c.type_is_numeric if c else False


# ---------------------------------------------------------------------------
# XBRLInstance
# ---------------------------------------------------------------------------


@dataclass
class XBRLInstance:
    """Top-level XBRL instance document model."""

    file_path: str = ""
    format_type: InputFormat = InputFormat.XBRL_XML
    contexts: dict[ContextID, Context] = field(default_factory=dict)
    units: dict[UnitID, Unit] = field(default_factory=dict)
    facts: list[Fact] = field(default_factory=list)
    footnotes: list[Footnote] = field(default_factory=list)
    taxonomy: TaxonomyModel | None = None
    schema_refs: list[SchemaRef] = field(default_factory=list)
    namespaces: dict[str, str] = field(default_factory=dict)

    # Lazy-built indexes
    _facts_by_concept: dict[QName, list[Fact]] | None = field(
        default=None, repr=False, compare=False
    )
    _facts_by_context: dict[ContextID, list[Fact]] | None = field(
        default=None, repr=False, compare=False
    )

    @property
    def facts_by_concept(self) -> dict[QName, list[Fact]]:
        """Index: concept QName → list of facts."""
        if self._facts_by_concept is None:
            idx: dict[QName, list[Fact]] = {}
            for f in self.facts:
                idx.setdefault(f.concept_qname, []).append(f)
            self._facts_by_concept = idx
        return self._facts_by_concept

    @property
    def facts_by_context(self) -> dict[ContextID, list[Fact]]:
        """Index: context ID → list of facts."""
        if self._facts_by_context is None:
            idx: dict[ContextID, list[Fact]] = {}
            for f in self.facts:
                if f.context_ref is not None:
                    idx.setdefault(f.context_ref, []).append(f)
            self._facts_by_context = idx
        return self._facts_by_context

    def get_facts_by_concept(self, concept: QName) -> list[Fact]:
        """Return all facts reporting the given concept."""
        return self.facts_by_concept.get(concept, [])

    def get_facts_by_context(self, context_id: ContextID) -> list[Fact]:
        """Return all facts sharing the given context id."""
        return self.facts_by_context.get(context_id, [])

    def iter_facts(self) -> Iterator[Fact]:
        """Iterate over all reported facts."""
        return iter(self.facts)

    def get_fact_count(self) -> int:
        """Return the total number of facts."""
        return len(self.facts)

    def invalidate_indexes(self) -> None:
        """Clear cached indexes (call after adding/removing facts)."""
        self._facts_by_concept = None
        self._facts_by_context = None
