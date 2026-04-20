"""DOM model builder.

Transforms the raw parsed representations (:class:`RawXBRLDocument` and
:class:`InlineXBRLDocument`) produced by the Phase 2/3 parsers into a
fully-resolved :class:`XBRLInstance`.

All numeric values are converted to :class:`~decimal.Decimal`.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from src.core.constants import NS_ISO4217, NS_XBRLI
from src.core.model.xbrl_model import (
    Context,
    DimensionMember,
    EntityIdentifier,
    Fact,
    Footnote,
    Period,
    TaxonomyModel,
    Unit,
    UnitMeasure,
    XBRLInstance,
)
from src.core.parser.xml_parser import (
    RawContext,
    RawFact,
    RawFootnote,
    RawUnit,
    RawXBRLDocument,
)
from src.core.types import InputFormat, PeriodType

logger = logging.getLogger(__name__)


def _parse_date(value: Optional[str]) -> date | None:
    """Parse an ISO 8601 date string to a :class:`date`.

    Args:
        value: Date string (``YYYY-MM-DD``).

    Returns:
        Parsed date or ``None``.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        logger.warning("Invalid date value: %s", value)
        return None


def _parse_measure(qname_str: str) -> UnitMeasure:
    """Convert a measure QName string to a :class:`UnitMeasure`.

    Handles both Clark notation ``{ns}local`` and prefixed ``prefix:local``.

    Args:
        qname_str: The measure QName string.

    Returns:
        A :class:`UnitMeasure` instance.
    """
    if qname_str.startswith("{"):
        # Clark notation
        ns, local = qname_str[1:].split("}", 1)
        return UnitMeasure(namespace=ns, local_name=local)
    if ":" in qname_str:
        prefix, local = qname_str.split(":", 1)
        # Map common prefixes
        if prefix == "iso4217":
            return UnitMeasure(namespace=NS_ISO4217, local_name=local)
        if prefix == "xbrli":
            return UnitMeasure(namespace=NS_XBRLI, local_name=local)
        return UnitMeasure(namespace=prefix, local_name=local)
    return UnitMeasure(namespace="", local_name=qname_str)


class ModelBuilder:
    """Build :class:`XBRLInstance` from parsed documents (DOM mode)."""

    def build(
        self,
        raw_doc: RawXBRLDocument,
        taxonomy: TaxonomyModel | None = None,
    ) -> XBRLInstance:
        """Build :class:`XBRLInstance` from :class:`RawXBRLDocument`.

        Args:
            raw_doc: Intermediate representation from the XML parser.
            taxonomy: Optional taxonomy model for concept classification.

        Returns:
            A fully-populated :class:`XBRLInstance`.
        """
        contexts: dict[str, Context] = {}
        for cid, raw_ctx in raw_doc.contexts.items():
            try:
                contexts[cid] = self._build_context(raw_ctx)
            except Exception as exc:
                logger.warning("Failed to build context %s: %s", cid, exc)

        units: dict[str, Unit] = {}
        for uid, raw_unit in raw_doc.units.items():
            try:
                units[uid] = self._build_unit(raw_unit)
            except Exception as exc:
                logger.warning("Failed to build unit %s: %s", uid, exc)

        facts: list[Fact] = []
        for raw_fact in raw_doc.facts:
            try:
                fact = self._build_fact(raw_fact, contexts, units, taxonomy)
                facts.append(fact)
            except Exception as exc:
                logger.warning(
                    "Failed to build fact %s (line %d): %s",
                    raw_fact.concept,
                    raw_fact.source_line,
                    exc,
                )

        footnotes: list[Footnote] = []
        for raw_fn in raw_doc.footnotes:
            footnotes.append(
                Footnote(
                    id=raw_fn.footnote_id or None,
                    role=raw_fn.role,
                    language=raw_fn.lang,
                    content=raw_fn.content,
                    fact_refs=[raw_fn.fact_id] if raw_fn.fact_id else [],
                )
            )

        schema_refs = [sr.href for sr in raw_doc.schema_refs]

        instance = XBRLInstance(
            file_path=raw_doc.file_path,
            format_type=InputFormat.XBRL_XML,
            contexts=contexts,
            units=units,
            facts=facts,
            footnotes=footnotes,
            taxonomy=taxonomy,
            schema_refs=schema_refs,
            namespaces=dict(raw_doc.namespaces),
        )
        instance.build_indexes()
        logger.info(
            "Built XBRLInstance: %d contexts, %d units, %d facts",
            len(contexts),
            len(units),
            len(facts),
        )
        return instance

    def build_from_inline(
        self,
        inline_doc: "InlineXBRLDocument",
        taxonomy: TaxonomyModel | None = None,
    ) -> XBRLInstance:
        """Build :class:`XBRLInstance` from :class:`InlineXBRLDocument`.

        Args:
            inline_doc: Intermediate representation from the iXBRL parser.
            taxonomy: Optional taxonomy model for concept classification.

        Returns:
            A fully-populated :class:`XBRLInstance`.
        """
        from src.core.parser.ixbrl_parser import InlineXBRLDocument

        contexts: dict[str, Context] = {}
        for cid, raw_ctx in inline_doc.contexts.items():
            try:
                contexts[cid] = self._build_context(raw_ctx)
            except Exception as exc:
                logger.warning("Failed to build inline context %s: %s", cid, exc)

        units: dict[str, Unit] = {}
        for uid, raw_unit in inline_doc.units.items():
            try:
                units[uid] = self._build_unit(raw_unit)
            except Exception as exc:
                logger.warning("Failed to build inline unit %s: %s", uid, exc)

        facts: list[Fact] = []
        all_inline_facts = inline_doc.inline_facts + inline_doc.hidden_facts
        for ifact in all_inline_facts:
            try:
                # Resolve continuations
                value = ifact.value or ""
                if hasattr(ifact, "continuation_refs"):
                    for cont_id in getattr(ifact, "continuation_refs", []):
                        cont_text = inline_doc.continuations.get(cont_id, "")
                        value += cont_text

                is_hidden = ifact in inline_doc.hidden_facts

                raw_fact = RawFact(
                    concept=ifact.concept,
                    context_ref=ifact.context_ref,
                    unit_ref=getattr(ifact, "unit_ref", None),
                    value=value,
                    decimals=getattr(ifact, "decimals", None),
                    precision=getattr(ifact, "precision", None),
                    id=getattr(ifact, "id", None),
                    is_nil=getattr(ifact, "is_nil", False),
                    source_line=getattr(ifact, "source_line", 0),
                    namespace=getattr(ifact, "namespace", ""),
                )

                fact = self._build_fact(raw_fact, contexts, units, taxonomy)
                fact.is_hidden = is_hidden
                facts.append(fact)
            except Exception as exc:
                logger.warning(
                    "Failed to build inline fact %s: %s",
                    getattr(ifact, "concept", "?"),
                    exc,
                )

        schema_refs = [sr.href for sr in inline_doc.schema_refs]

        instance = XBRLInstance(
            file_path=inline_doc.file_path,
            format_type=InputFormat.IXBRL_HTML,
            contexts=contexts,
            units=units,
            facts=facts,
            taxonomy=taxonomy,
            schema_refs=schema_refs,
            namespaces=dict(inline_doc.namespaces),
        )
        instance.build_indexes()
        logger.info(
            "Built inline XBRLInstance: %d contexts, %d units, %d facts",
            len(contexts),
            len(units),
            len(facts),
        )
        return instance

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_context(self, raw: RawContext) -> Context:
        """Build a :class:`Context` from a :class:`RawContext`.

        Args:
            raw: The raw parsed context.

        Returns:
            A model :class:`Context` instance.
        """
        entity = EntityIdentifier(
            scheme=raw.entity_scheme,
            identifier=raw.entity_id,
        )

        period_type_str = raw.period_type.lower() if raw.period_type else "duration"
        try:
            period_type = PeriodType(period_type_str)
        except ValueError:
            period_type = PeriodType.DURATION

        period = Period(
            period_type=period_type,
            instant=_parse_date(raw.instant),
            start_date=_parse_date(raw.start_date),
            end_date=_parse_date(raw.end_date),
        )

        segment_dims = self._extract_dimensions(raw.segments)
        scenario_dims = self._extract_dimensions(raw.scenarios)

        return Context(
            id=raw.id,
            entity=entity,
            period=period,
            segment_dims=segment_dims,
            scenario_dims=scenario_dims,
        )

    def _build_unit(self, raw: RawUnit) -> Unit:
        """Build a :class:`Unit` from a :class:`RawUnit`.

        Args:
            raw: The raw parsed unit.

        Returns:
            A model :class:`Unit` instance.
        """
        measures = [_parse_measure(m) for m in raw.measures]
        divide_num = [_parse_measure(m) for m in raw.divide_numerator]
        divide_den = [_parse_measure(m) for m in raw.divide_denominator]

        return Unit(
            id=raw.id,
            measures=measures,
            divide_numerator=divide_num,
            divide_denominator=divide_den,
        )

    def _build_fact(
        self,
        raw: RawFact,
        contexts: dict[str, Context],
        units: dict[str, Unit],
        taxonomy: TaxonomyModel | None,
    ) -> Fact:
        """Build a :class:`Fact` from a :class:`RawFact`.

        Args:
            raw: The raw parsed fact.
            contexts: Resolved context map.
            units: Resolved unit map.
            taxonomy: Optional taxonomy for type classification.

        Returns:
            A model :class:`Fact` instance.
        """
        context = contexts.get(raw.context_ref)
        unit = units.get(raw.unit_ref) if raw.unit_ref else None

        # Determine if numeric from taxonomy or heuristic
        is_numeric = False
        if taxonomy and raw.concept in taxonomy.concepts:
            concept_def = taxonomy.concepts[raw.concept]
            is_numeric = concept_def.type_is_numeric
        elif raw.unit_ref:
            # Heuristic: facts with a unit are likely numeric
            is_numeric = True

        numeric_value: Decimal | None = None
        if is_numeric and raw.value and not raw.is_nil:
            try:
                cleaned = raw.value.strip().replace(",", "")
                numeric_value = Decimal(cleaned)
            except (InvalidOperation, ValueError):
                logger.debug(
                    "Could not parse numeric value for %s: %r",
                    raw.concept,
                    raw.value,
                )

        return Fact(
            id=raw.id,
            concept=raw.concept,
            context_ref=raw.context_ref,
            context=context,
            unit_ref=raw.unit_ref,
            unit=unit,
            value=raw.value,
            numeric_value=numeric_value,
            is_nil=raw.is_nil,
            is_numeric=is_numeric,
            decimals=raw.decimals,
            precision=raw.precision,
            source_line=raw.source_line,
            source_file="",
        )

    @staticmethod
    def _extract_dimensions(
        raw_dims: list[dict[str, str]],
    ) -> list[DimensionMember]:
        """Extract dimension members from raw segment/scenario dicts.

        Args:
            raw_dims: List of raw dimension dictionaries.

        Returns:
            List of :class:`DimensionMember` instances.
        """
        dims: list[DimensionMember] = []
        for d in raw_dims:
            dimension = d.get("dimension", "")
            member = d.get("member", d.get("value", ""))
            is_typed = d.get("is_typed", "false").lower() == "true"
            typed_value = d.get("typed_value")

            if dimension:
                dims.append(
                    DimensionMember(
                        dimension=dimension,
                        member=member,
                        is_typed=is_typed,
                        typed_value=typed_value,
                    )
                )
        return dims
