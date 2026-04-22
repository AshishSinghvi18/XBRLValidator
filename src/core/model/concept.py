"""Taxonomy concept definition — XBRL 2.1 §5.1.

A :class:`Concept` is the immutable representation of a single element
declaration in a taxonomy schema.  Every concept carries enough metadata
to drive period-type validation, balance consistency checks, and
dimensional qualification.

References:
    - XBRL 2.1 §5.1 (Concept definitions)
    - XBRL 2.1 §5.1.1 (Item element declarations)
    - XBRL Dimensions 1.0 §2.4 (Typed dimension domains)
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.types import BalanceType, ConceptType, PeriodType


@dataclass(frozen=True, slots=True)
class Concept:
    """An XBRL taxonomy concept (element declaration) — XBRL 2.1 §5.1.

    Attributes:
        qname: Clark-notation QName, e.g.
            ``"{http://fasb.org/us-gaap/2024}Assets"``.
        concept_type: Category of the concept (item, tuple, dimension, …).
        period_type: Required period type for facts reporting this concept
            — XBRL 2.1 §5.1.1.
        balance_type: Debit / credit / none — XBRL 2.1 §5.1.1.
        abstract: ``True`` if the concept is abstract and cannot have facts.
        nillable: ``True`` if facts may carry ``xsi:nil="true"``.
        substitution_group: Substitution-group local name
            (e.g. ``"item"``, ``"tuple"``).
        type_name: XSD type name (e.g. ``"monetaryItemType"``).
        schema_url: Absolute URL of the taxonomy schema that defines this
            concept.
        typed_domain_ref: Optional href to the typed-dimension domain
            element — XDT 1.0 §2.4.  ``None`` for non-typed-dimension
            concepts.
    """

    qname: str
    concept_type: ConceptType
    period_type: PeriodType
    balance_type: BalanceType
    abstract: bool
    nillable: bool
    substitution_group: str
    type_name: str
    schema_url: str
    typed_domain_ref: str | None = None
