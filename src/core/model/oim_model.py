"""OIM (Open Information Model) canonical model.

Provides the format-neutral OIM representation that serves as the
common data model across xBRL-XML, xBRL-JSON, and xBRL-CSV formats.
Each fact is represented with its complete set of aspects (entity,
period, concept, unit, dimensions) rather than referencing separate
context/unit objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

import structlog

from src.core.model.xbrl_model import (
    Context, Fact, Unit, UnitMeasure, XBRLInstance,
)
from src.core.types import PeriodType, QName

logger = structlog.get_logger(__name__)


@dataclass
class OIMPeriod:
    """OIM period aspect — either instant or duration."""
    period_type: PeriodType
    instant: date | None = None
    start_date: date | None = None
    end_date: date | None = None

    def to_string(self) -> str:
        if self.period_type == PeriodType.INSTANT and self.instant:
            return self.instant.isoformat()
        if self.period_type == PeriodType.DURATION and self.start_date and self.end_date:
            return f"{self.start_date.isoformat()}/{self.end_date.isoformat()}"
        return "forever"


@dataclass
class OIMUnit:
    """OIM unit aspect — expressed as numerator/denominator measure lists."""
    numerators: list[str] = field(default_factory=list)
    denominators: list[str] = field(default_factory=list)

    def to_string(self) -> str:
        num = "*".join(sorted(self.numerators)) if self.numerators else ""
        if not self.denominators:
            return num
        den = "*".join(sorted(self.denominators))
        return f"{num}/{den}"


@dataclass
class OIMFact:
    """A fact in OIM canonical form with all aspects inlined."""
    id: str = ""
    concept: QName = ""
    entity: str = ""
    period: OIMPeriod | None = None
    unit: OIMUnit | None = None
    dimensions: dict[QName, str] = field(default_factory=dict)
    value: str | None = None
    numeric_value: Decimal | None = None
    decimals: int | Literal["INF"] | None = None
    is_nil: bool = False
    is_numeric: bool = False
    language: str | None = None
    footnotes: list[str] = field(default_factory=list)

    @property
    def aspect_key(self) -> tuple[Any, ...]:
        """Unique aspect combination for duplicate detection."""
        period_str = self.period.to_string() if self.period else ""
        unit_str = self.unit.to_string() if self.unit else ""
        dims = tuple(sorted(self.dimensions.items()))
        return (self.concept, self.entity, period_str, unit_str, dims, self.language)


@dataclass
class OIMReport:
    """An OIM report — the format-neutral top-level container."""
    facts: list[OIMFact] = field(default_factory=list)
    source_file: str = ""
    namespaces: dict[str, str] = field(default_factory=dict)
    link_groups: list[dict[str, Any]] = field(default_factory=list)


class OIMConverter:
    """Convert between XBRLInstance and OIM canonical form."""

    def __init__(self) -> None:
        self._log = logger.bind(component="oim_converter")

    def to_oim(self, instance: XBRLInstance) -> OIMReport:
        """Convert an XBRLInstance to OIM canonical form."""
        self._log.info("to_oim_start", facts=len(instance.facts))
        report = OIMReport(
            source_file=instance.file_path,
            namespaces=dict(instance.namespaces),
        )

        for fact in instance.facts:
            oim_fact = self._convert_fact(fact, instance)
            report.facts.append(oim_fact)

        self._log.info("to_oim_complete", facts=len(report.facts))
        return report

    def from_oim(self, report: OIMReport) -> XBRLInstance:
        """Convert an OIM report back to XBRLInstance form."""
        from src.core.model.builder_oim import OIMModelBuilder, OIMFact as BuilderOIMFact

        builder = OIMModelBuilder()
        oim_facts: list[BuilderOIMFact] = []

        for oim_fact in report.facts:
            bf = BuilderOIMFact(
                id=oim_fact.id,
                concept=oim_fact.concept,
                entity=oim_fact.entity,
                value=oim_fact.value,
                is_nil=oim_fact.is_nil,
                decimals=oim_fact.decimals,
                language=oim_fact.language,
                dimensions=dict(oim_fact.dimensions),
            )
            if oim_fact.period:
                if oim_fact.period.period_type == PeriodType.INSTANT and oim_fact.period.instant:
                    bf.period_instant = oim_fact.period.instant.isoformat()
                elif oim_fact.period.start_date and oim_fact.period.end_date:
                    bf.period_start = oim_fact.period.start_date.isoformat()
                    bf.period_end = oim_fact.period.end_date.isoformat()
            if oim_fact.unit:
                bf.unit = oim_fact.unit.to_string()
            oim_facts.append(bf)

        return builder.build_from_facts(
            oim_facts,
            source_file=report.source_file,
            prefixes=report.namespaces,
        )

    def _convert_fact(self, fact: Fact, instance: XBRLInstance) -> OIMFact:
        entity = ""
        period: OIMPeriod | None = None
        dimensions: dict[QName, str] = {}

        if fact.context_ref:
            ctx = instance.contexts.get(fact.context_ref)
            if ctx is not None:
                entity = str(ctx.entity)
                period = OIMPeriod(
                    period_type=ctx.period.period_type,
                    instant=ctx.period.instant,
                    start_date=ctx.period.start_date,
                    end_date=ctx.period.end_date,
                )
                for dm in ctx.all_dimensions:
                    val = dm.typed_value if dm.is_typed else dm.member
                    dimensions[dm.dimension] = val or ""

        unit: OIMUnit | None = None
        if fact.unit_ref:
            u = instance.units.get(fact.unit_ref)
            if u is not None:
                unit = self._convert_unit(u)

        return OIMFact(
            id=fact.id,
            concept=fact.concept_qname,
            entity=entity,
            period=period,
            unit=unit,
            dimensions=dimensions,
            value=fact.raw_value if not fact.is_nil else None,
            numeric_value=fact.numeric_value,
            decimals=fact.decimals,
            is_nil=fact.is_nil,
            is_numeric=fact.is_numeric,
            language=fact.language,
            footnotes=list(fact.footnote_refs),
        )

    def _convert_unit(self, unit: Unit) -> OIMUnit:
        if unit.is_divide:
            return OIMUnit(
                numerators=[m.clark for m in unit.numerator_measures],
                denominators=[m.clark for m in unit.denominator_measures],
            )
        return OIMUnit(numerators=[m.clark for m in unit.measures])
