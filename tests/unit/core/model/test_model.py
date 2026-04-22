"""Unit tests for the XBRL core data model classes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.core.model import (
    Concept,
    Context,
    Entity,
    ExplicitDimension,
    Fact,
    Period,
    TypedDimension,
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


# ── Concept ──────────────────────────────────────────────────────────────


class TestConcept:
    def test_creation(self) -> None:
        c = Concept(
            qname="{http://example.com}Revenue",
            concept_type=ConceptType.ITEM,
            period_type=PeriodType.DURATION,
            balance_type=BalanceType.CREDIT,
            abstract=False,
            nillable=True,
            substitution_group="item",
            type_name="monetaryItemType",
            schema_url="http://example.com/schema.xsd",
        )
        assert c.qname == "{http://example.com}Revenue"
        assert c.concept_type == ConceptType.ITEM
        assert c.balance_type == BalanceType.CREDIT
        assert c.typed_domain_ref is None

    def test_frozen(self) -> None:
        c = Concept(
            qname="{http://example.com}X",
            concept_type=ConceptType.ITEM,
            period_type=PeriodType.INSTANT,
            balance_type=BalanceType.NONE,
            abstract=False,
            nillable=False,
            substitution_group="item",
            type_name="stringItemType",
            schema_url="http://example.com/schema.xsd",
        )
        try:
            c.qname = "changed"  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass


# ── Period / Entity / Context ────────────────────────────────────────────


class TestPeriod:
    def test_instant(self, simple_period: Period) -> None:
        assert simple_period.period_type == PeriodType.INSTANT
        assert simple_period.instant == date(2024, 12, 31)
        assert simple_period.start_date is None

    def test_duration(self, duration_period: Period) -> None:
        assert duration_period.period_type == PeriodType.DURATION
        assert duration_period.start_date == date(2024, 1, 1)
        assert duration_period.end_date == date(2024, 12, 31)


class TestContext:
    def test_instant_context(self, simple_context: Context) -> None:
        assert simple_context.context_id == "ctx1"
        assert simple_context.is_instant is True
        assert simple_context.is_duration is False

    def test_duration_context(self, duration_context: Context) -> None:
        assert duration_context.is_duration is True
        assert duration_context.is_instant is False

    def test_dimension_key_empty(self, simple_context: Context) -> None:
        assert simple_context.dimension_key == ()

    def test_with_dimensions(self, entity: Entity, simple_period: Period) -> None:
        ctx = Context(
            context_id="ctx_dim",
            entity=entity,
            period=simple_period,
            explicit_dimensions=(
                ExplicitDimension(
                    dimension="{http://example.com}Segment",
                    member="{http://example.com}Retail",
                ),
            ),
            typed_dimensions=(),
        )
        assert len(ctx.explicit_dimensions) == 1
        key = ctx.dimension_key
        assert len(key) == 1


# ── Unit ─────────────────────────────────────────────────────────────────


class TestUnit:
    def test_monetary(self, usd_unit: Unit) -> None:
        assert usd_unit.is_monetary is True
        assert usd_unit.is_pure is False
        assert usd_unit.is_divide is False

    def test_pure(self, pure_unit: Unit) -> None:
        assert pure_unit.is_pure is True
        assert pure_unit.is_monetary is False

    def test_divide(self) -> None:
        u = Unit(
            unit_id="rate",
            numerators=("{http://www.xbrl.org/2003/iso4217}USD",),
            denominators=("{http://www.xbrl.org/2003/instance}shares",),
        )
        assert u.is_divide is True
        assert u.is_monetary is False


# ── Fact ─────────────────────────────────────────────────────────────────


class TestFact:
    def test_numeric_fact(self, numeric_fact: Fact) -> None:
        assert numeric_fact.is_numeric is True
        assert numeric_fact.value == Decimal("1000000")
        assert numeric_fact.unit_ref == "usd"
        assert numeric_fact.decimals == -3

    def test_text_fact(self, text_fact: Fact) -> None:
        assert text_fact.is_numeric is False
        assert text_fact.value == "Acme Corp"
        assert text_fact.unit_ref is None

    def test_nil_fact(self) -> None:
        f = Fact(
            fact_id="nil1",
            concept_qname="{http://example.com}X",
            context_ref="ctx1",
            unit_ref=None,
            value=None,
            fact_type=FactType.NIL,
            decimals=None,
            precision=None,
            is_nil=True,
            language=None,
            source_line=1,
            source_file="test.xml",
        )
        assert f.is_nil is True
        assert f.value is None

    def test_effective_value_with_scale(self) -> None:
        f = Fact(
            fact_id="s1",
            concept_qname="{http://example.com}Revenue",
            context_ref="ctx1",
            unit_ref="usd",
            value=Decimal("5"),
            fact_type=FactType.NUMERIC,
            decimals=-6,
            precision=None,
            is_nil=False,
            language=None,
            source_line=1,
            source_file="test.xml",
            scale=6,
        )
        result = f.effective_value()
        assert result == Decimal("5000000")

    def test_effective_value_with_sign(self) -> None:
        f = Fact(
            fact_id="s2",
            concept_qname="{http://example.com}Loss",
            context_ref="ctx1",
            unit_ref="usd",
            value=Decimal("100"),
            fact_type=FactType.NUMERIC,
            decimals=0,
            precision=None,
            is_nil=False,
            language=None,
            source_line=1,
            source_file="test.xml",
            sign="-",
        )
        result = f.effective_value()
        assert result == Decimal("-100")


# ── XBRLInstance ─────────────────────────────────────────────────────────


class TestXBRLInstance:
    def test_fact_count(self, simple_instance: XBRLInstance) -> None:
        assert simple_instance.fact_count() == 2

    def test_iter_fact_ids(self, simple_instance: XBRLInstance) -> None:
        ids = simple_instance.iter_fact_ids()
        assert "f1" in ids
        assert "f2" in ids

    def test_facts_by_concept(self, simple_instance: XBRLInstance) -> None:
        facts = simple_instance.facts_by_concept(
            "{http://fasb.org/us-gaap/2024}Assets"
        )
        assert len(facts) == 1
        assert facts[0].fact_id == "f1"

    def test_facts_by_context(self, simple_instance: XBRLInstance) -> None:
        facts = simple_instance.facts_by_context("ctx1")
        assert len(facts) == 2

    def test_numeric_facts(self, simple_instance: XBRLInstance) -> None:
        nums = simple_instance.numeric_facts()
        assert len(nums) == 1
        assert nums[0].fact_id == "f1"

    def test_get_context(self, simple_instance: XBRLInstance) -> None:
        ctx = simple_instance.get_context("ctx1")
        assert ctx is not None
        assert ctx.context_id == "ctx1"
        assert simple_instance.get_context("nonexistent") is None

    def test_get_unit(self, simple_instance: XBRLInstance) -> None:
        u = simple_instance.get_unit("usd")
        assert u is not None
        assert u.is_monetary is True
        assert simple_instance.get_unit("nonexistent") is None


# ── ValidationMessage ────────────────────────────────────────────────────


class TestValidationMessage:
    def test_creation(self) -> None:
        msg = ValidationMessage(
            code="TEST-0001",
            severity=Severity.ERROR,
            message="Something went wrong",
            spec_ref="XBRL 2.1 §4.7",
            fix_suggestion="Fix the thing",
        )
        assert msg.code == "TEST-0001"
        assert msg.severity == Severity.ERROR
        assert msg.spec_ref == "XBRL 2.1 §4.7"
