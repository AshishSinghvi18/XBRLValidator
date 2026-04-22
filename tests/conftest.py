"""Shared test fixtures for XBRL Validator tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.core.model import (
    Concept,
    Context,
    Entity,
    ExplicitDimension,
    Fact,
    Period,
    Unit,
    ValidationMessage,
    XBRLInstance,
)
from src.core.types import (
    BalanceType,
    ConceptType,
    FactType,
    InputFormat,
    PeriodType,
    Severity,
)


@pytest.fixture
def simple_period() -> Period:
    return Period(period_type=PeriodType.INSTANT, instant=date(2024, 12, 31))


@pytest.fixture
def duration_period() -> Period:
    return Period(
        period_type=PeriodType.DURATION,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )


@pytest.fixture
def entity() -> Entity:
    return Entity(scheme="http://www.sec.gov/CIK", identifier="0001234567")


@pytest.fixture
def simple_context(entity: Entity, simple_period: Period) -> Context:
    return Context(
        context_id="ctx1",
        entity=entity,
        period=simple_period,
        explicit_dimensions=(),
        typed_dimensions=(),
    )


@pytest.fixture
def duration_context(entity: Entity, duration_period: Period) -> Context:
    return Context(
        context_id="ctx2",
        entity=entity,
        period=duration_period,
        explicit_dimensions=(),
        typed_dimensions=(),
    )


@pytest.fixture
def usd_unit() -> Unit:
    return Unit(
        unit_id="usd",
        numerators=("{http://www.xbrl.org/2003/iso4217}USD",),
        denominators=(),
    )


@pytest.fixture
def pure_unit() -> Unit:
    return Unit(
        unit_id="pure",
        numerators=("{http://www.xbrl.org/2003/instance}pure",),
        denominators=(),
    )


@pytest.fixture
def numeric_fact() -> Fact:
    return Fact(
        fact_id="f1",
        concept_qname="{http://fasb.org/us-gaap/2024}Assets",
        context_ref="ctx1",
        unit_ref="usd",
        value=Decimal("1000000"),
        fact_type=FactType.NUMERIC,
        decimals=-3,
        precision=None,
        is_nil=False,
        language=None,
        source_line=10,
        source_file="test.xml",
    )


@pytest.fixture
def text_fact() -> Fact:
    return Fact(
        fact_id="f2",
        concept_qname="{http://fasb.org/us-gaap/2024}EntityName",
        context_ref="ctx1",
        unit_ref=None,
        value="Acme Corp",
        fact_type=FactType.NON_NUMERIC,
        decimals=None,
        precision=None,
        is_nil=False,
        language="en-US",
        source_line=20,
        source_file="test.xml",
    )


@pytest.fixture
def simple_instance(
    simple_context: Context,
    usd_unit: Unit,
    numeric_fact: Fact,
    text_fact: Fact,
) -> XBRLInstance:
    return XBRLInstance(
        file_path="test.xml",
        input_format=InputFormat.XBRL_XML,
        schema_refs=["http://xbrl.fasb.org/us-gaap/2024/elts/us-gaap-2024.xsd"],
        contexts={"ctx1": simple_context},
        units={"usd": usd_unit},
        facts=[numeric_fact, text_fact],
        footnotes=[],
    )
