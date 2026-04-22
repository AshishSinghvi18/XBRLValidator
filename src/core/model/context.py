"""XBRL context element — XBRL 2.1 §4.7.

A :class:`Context` groups the entity, period, and dimensional qualifiers
that apply to one or more facts.  All sub-components are immutable
frozen dataclasses so they can be safely used as dictionary keys and in
sets.

References:
    - XBRL 2.1 §4.7   (context element)
    - XBRL 2.1 §4.7.1 (entity)
    - XBRL 2.1 §4.7.2 (period)
    - XBRL Dimensions 1.0 §4 (scenario / segment dimensional items)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.core.types import DimensionKey, PeriodType


@dataclass(frozen=True, slots=True)
class Period:
    """Period element of an XBRL context — XBRL 2.1 §4.7.2.

    Exactly one of the following patterns is valid:

    * **Instant**: ``period_type=INSTANT``, ``instant`` is set.
    * **Duration**: ``period_type=DURATION``, ``start_date`` and
      ``end_date`` are set.
    * **Forever**: ``period_type=FOREVER``, all date fields are ``None``.

    Attributes:
        period_type: Discriminator for the period variant.
        instant: Point-in-time date for instant periods.
        start_date: Inclusive start date for duration periods.
        end_date: Exclusive end date for duration periods.
    """

    period_type: PeriodType
    instant: date | None = None
    start_date: date | None = None
    end_date: date | None = None


@dataclass(frozen=True, slots=True)
class Entity:
    """Entity identifier within an XBRL context — XBRL 2.1 §4.7.1.

    Attributes:
        scheme: URI identifying the identification scheme
            (e.g. ``"http://www.sec.gov/CIK"``).
        identifier: Entity identifier value within the scheme
            (e.g. ``"0000320193"``).
    """

    scheme: str
    identifier: str


@dataclass(frozen=True, slots=True)
class ExplicitDimension:
    """An explicit-dimension member binding — XDT 1.0 §4.

    Attributes:
        dimension: Clark-notation QName of the dimension concept.
        member: Clark-notation QName of the domain member.
    """

    dimension: str
    member: str


@dataclass(frozen=True, slots=True)
class TypedDimension:
    """A typed-dimension value binding — XDT 1.0 §4.

    Attributes:
        dimension: Clark-notation QName of the dimension concept.
        value: Serialised XML fragment representing the typed value.
    """

    dimension: str
    value: str


@dataclass(frozen=True, slots=True)
class Context:
    """Full XBRL context element — XBRL 2.1 §4.7.

    Attributes:
        context_id: The ``id`` attribute of the ``<xbrli:context>``
            element (serves as :pydata:`src.core.types.ContextID`).
        entity: Entity identifier for this context.
        period: Period element for this context.
        explicit_dimensions: Tuple of explicit-dimension bindings found
            in the ``<scenario>`` or ``<segment>`` child elements.
        typed_dimensions: Tuple of typed-dimension bindings found in the
            ``<scenario>`` or ``<segment>`` child elements.
    """

    context_id: str
    entity: Entity
    period: Period
    explicit_dimensions: tuple[ExplicitDimension, ...] = ()
    typed_dimensions: tuple[TypedDimension, ...] = ()

    @property
    def dimension_key(self) -> DimensionKey:
        """Return a canonical dimension key for duplicate-detection.

        The key is a sorted tuple of ``(dimension_qname, member_qname)``
        pairs covering all explicit dimensions.  Typed dimensions are
        represented as ``(dimension_qname, serialised_value)`` pairs.

        Returns:
            Sorted tuple suitable for hashing and equality comparison
            — see :pydata:`src.core.types.DimensionKey`.

        References:
            - XBRL Dimensions 1.0 §4
        """
        pairs: list[tuple[str, str]] = [
            (ed.dimension, ed.member) for ed in self.explicit_dimensions
        ]
        pairs.extend(
            (td.dimension, td.value) for td in self.typed_dimensions
        )
        return tuple(sorted(pairs))

    @property
    def is_instant(self) -> bool:
        """Return ``True`` if this context has an instant period.

        References:
            - XBRL 2.1 §4.7.2
        """
        return self.period.period_type == PeriodType.INSTANT

    @property
    def is_duration(self) -> bool:
        """Return ``True`` if this context has a duration period.

        References:
            - XBRL 2.1 §4.7.2
        """
        return self.period.period_type == PeriodType.DURATION
