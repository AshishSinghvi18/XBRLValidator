"""OIM (Open Information Model) builder — transforms xBRL-JSON and xBRL-CSV into XBRLInstance.

Spec references:
  - OIM 1.0: https://www.xbrl.org/Specification/oim/CR-2021-02-03/oim-CR-2021-02-03.html
  - xBRL-JSON: https://www.xbrl.org/Specification/xbrl-json/CR-2021-02-03/
  - xBRL-CSV: https://www.xbrl.org/Specification/xbrl-csv/CR-2021-02-03/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

from src.core.constants import NS_XBRLI, NS_ISO4217
from src.core.model.xbrl_model import (
    Context, DimensionMember, EntityIdentifier, Fact, Footnote,
    Period, SchemaRef, TaxonomyModel, Unit, UnitMeasure, XBRLInstance,
)
from src.core.qname import format_qname, split_clark
from src.core.types import InputFormat, PeriodType
from src.utils.datetime_utils import parse_iso_date
from src.utils.decimal_utils import XBRL_DECIMAL_CONTEXT

logger = structlog.get_logger(__name__)


@dataclass
class OIMFact:
    """Intermediate OIM fact representation before conversion."""
    id: str = ""
    concept: str = ""
    entity: str = ""
    period_start: str = ""
    period_end: str = ""
    period_instant: str = ""
    unit: str = ""
    value: Any = None
    decimals: int | str | None = None
    dimensions: dict[str, str] = field(default_factory=dict)
    language: str | None = None
    is_nil: bool = False


class OIMModelBuilder:
    """Build an XBRLInstance from OIM-format data (JSON/CSV parsed structures)."""

    def __init__(self) -> None:
        self._log = logger.bind(component="oim_model_builder")
        self._context_counter: int = 0
        self._unit_counter: int = 0

    def build_from_facts(
        self,
        oim_facts: list[OIMFact],
        *,
        source_file: str = "",
        format_type: InputFormat = InputFormat.XBRL_JSON,
        taxonomy: TaxonomyModel | None = None,
        prefixes: dict[str, str] | None = None,
    ) -> XBRLInstance:
        """Build an XBRLInstance from a list of OIM facts."""
        self._log.info("oim_build_start", fact_count=len(oim_facts), source=source_file)
        self._context_counter = 0
        self._unit_counter = 0

        instance = XBRLInstance(
            file_path=source_file,
            format_type=format_type,
            taxonomy=taxonomy,
            namespaces=prefixes or {},
        )

        context_cache: dict[tuple[Any, ...], str] = {}
        unit_cache: dict[str, str] = {}

        for idx, oim_fact in enumerate(oim_facts):
            ctx_key = self._context_key(oim_fact)
            if ctx_key not in context_cache:
                ctx = self._create_context(oim_fact)
                instance.contexts[ctx.id] = ctx
                context_cache[ctx_key] = ctx.id
            ctx_id = context_cache[ctx_key]

            unit_id: str | None = None
            if oim_fact.unit:
                if oim_fact.unit not in unit_cache:
                    unit = self._create_unit(oim_fact.unit)
                    instance.units[unit.id] = unit
                    unit_cache[oim_fact.unit] = unit.id
                unit_id = unit_cache[oim_fact.unit]

            fact = self._create_fact(oim_fact, idx, ctx_id, unit_id, source_file, taxonomy)
            instance.facts.append(fact)

        self._log.info(
            "oim_build_complete",
            facts=len(instance.facts),
            contexts=len(instance.contexts),
            units=len(instance.units),
        )
        return instance

    def _context_key(self, oim_fact: OIMFact) -> tuple[Any, ...]:
        dims = tuple(sorted(oim_fact.dimensions.items()))
        return (
            oim_fact.entity,
            oim_fact.period_instant,
            oim_fact.period_start,
            oim_fact.period_end,
            dims,
        )

    def _create_context(self, oim_fact: OIMFact) -> Context:
        self._context_counter += 1
        ctx_id = f"c_{self._context_counter}"

        scheme, _, identifier = oim_fact.entity.rpartition(":")
        if not scheme:
            scheme = "http://www.sec.gov/CIK"
            identifier = oim_fact.entity
        entity = EntityIdentifier(scheme=scheme, identifier=identifier)

        if oim_fact.period_instant:
            period = Period(
                period_type=PeriodType.INSTANT,
                instant=parse_iso_date(oim_fact.period_instant),
            )
        elif oim_fact.period_start and oim_fact.period_end:
            period = Period(
                period_type=PeriodType.DURATION,
                start_date=parse_iso_date(oim_fact.period_start),
                end_date=parse_iso_date(oim_fact.period_end),
            )
        else:
            period = Period(period_type=PeriodType.FOREVER)

        segment_dims: list[DimensionMember] = []
        for dim_name, member_val in oim_fact.dimensions.items():
            segment_dims.append(DimensionMember(
                dimension=dim_name,
                member=member_val,
                is_typed=False,
            ))

        return Context(
            id=ctx_id,
            entity=entity,
            period=period,
            segment_dims=segment_dims,
        )

    def _create_unit(self, unit_spec: str) -> Unit:
        self._unit_counter += 1
        unit_id = f"u_{self._unit_counter}"

        measures: list[UnitMeasure] = []
        numerator_measures: list[UnitMeasure] = []
        denominator_measures: list[UnitMeasure] = []

        if "/" in unit_spec:
            num_part, den_part = unit_spec.split("/", 1)
            for m in num_part.strip().split("*"):
                numerator_measures.append(self._parse_measure_spec(m.strip()))
            for m in den_part.strip().split("*"):
                denominator_measures.append(self._parse_measure_spec(m.strip()))
        else:
            for m in unit_spec.split("*"):
                measures.append(self._parse_measure_spec(m.strip()))

        return Unit(
            id=unit_id,
            measures=measures,
            numerator_measures=numerator_measures,
            denominator_measures=denominator_measures,
        )

    def _parse_measure_spec(self, spec: str) -> UnitMeasure:
        if spec.startswith("iso4217:"):
            return UnitMeasure(namespace=NS_ISO4217, local_name=spec[8:])
        if spec.startswith("xbrli:"):
            return UnitMeasure(namespace=NS_XBRLI, local_name=spec[6:])
        if ":" in spec:
            prefix, local = spec.split(":", 1)
            return UnitMeasure(namespace=prefix, local_name=local)
        return UnitMeasure(namespace="", local_name=spec)

    def _create_fact(
        self,
        oim_fact: OIMFact,
        index: int,
        ctx_id: str,
        unit_id: str | None,
        source_file: str,
        taxonomy: TaxonomyModel | None,
    ) -> Fact:
        fact_id = oim_fact.id or f"f_{index}"
        concept_qname = oim_fact.concept

        is_numeric = unit_id is not None
        numeric_value: Decimal | None = None
        raw_value = str(oim_fact.value) if oim_fact.value is not None else ""

        if is_numeric and raw_value and not oim_fact.is_nil:
            try:
                numeric_value = XBRL_DECIMAL_CONTEXT.create_decimal(raw_value)
            except (InvalidOperation, ValueError):
                pass

        parsed_decimals: int | str | None = None
        if oim_fact.decimals is not None:
            parsed_decimals = oim_fact.decimals

        return Fact(
            id=fact_id,
            concept_qname=concept_qname,
            context_ref=ctx_id,
            unit_ref=unit_id,
            raw_value=raw_value,
            numeric_value=numeric_value,
            is_nil=oim_fact.is_nil,
            is_numeric=is_numeric,
            decimals=parsed_decimals,
            language=oim_fact.language,
            source_file=source_file,
        )
