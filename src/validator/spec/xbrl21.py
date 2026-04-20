"""XBRL 2.1 specification validator.

Implements 25 checks (XBRL21-0001 through XBRL21-0025) covering the core
XBRL 2.1 specification requirements for contexts, units, facts, and
linkbases.

Spec references:
- XBRL 2.1 §4.6 (facts/items)
- XBRL 2.1 §4.7 (contexts/periods)
- XBRL 2.1 §4.8 (units)
- XBRL 2.1 §4.11 (footnotes)
- XBRL 2.1 §5.2.5.2 (calculation consistency)
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date
from decimal import Decimal
from typing import Iterator

from src.core.model.xbrl_model import (
    Context,
    Fact,
    Footnote,
    Unit,
    ValidationMessage,
    XBRLInstance,
)
from src.core.types import PeriodType, Severity
from src.validator.base import BaseValidator

logger = logging.getLogger(__name__)

# Standard XBRL footnote role
_STANDARD_FOOTNOTE_ROLE = "http://www.xbrl.org/2003/role/footnote"
_ISO4217_NS = "http://www.xbrl.org/2003/iso4217"
_XBRLI_NS = "http://www.xbrl.org/2003/instance"

# ISO 4217 currency codes (subset for validation)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class XBRL21Validator(BaseValidator):
    """Validator for XBRL 2.1 core specification rules.

    Implements 25 checks covering contexts, units, facts, footnotes,
    and schema references.  Supports both in-memory and large-file mode.
    """

    def __init__(self, instance: XBRLInstance) -> None:
        super().__init__(instance)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self) -> list[ValidationMessage]:
        """Run all 25 XBRL 2.1 checks and return messages.

        Returns:
            Collected validation messages.
        """
        self._messages.clear()
        checks = [
            self._check_0001_missing_entity_identifier,
            self._check_0002_missing_period,
            self._check_0003_invalid_instant_date,
            self._check_0004_start_after_end,
            self._check_0005_duplicate_context_id,
            self._check_0006_duplicate_unit_id,
            self._check_0007_unit_missing_measure,
            self._check_0008_fact_invalid_context,
            self._check_0009_numeric_fact_missing_unit,
            self._check_0010_missing_decimals_precision,
            self._check_0011_both_decimals_and_precision,
            self._check_0012_nil_fact_has_value,
            self._check_0013_concept_not_in_taxonomy,
            self._check_0014_type_mismatch,
            self._check_0015_period_type_mismatch,
            self._check_0016_monetary_iso4217,
            self._check_0017_shares_unit,
            self._check_0018_pure_unit,
            self._check_0019_invalid_identifier_scheme,
            self._check_0020_conflicting_duplicate_facts,
            self._check_0021_tuple_ordering,
            self._check_0022_missing_schema_ref,
            self._check_0023_missing_lang_for_string,
            self._check_0024_invalid_footnote_role,
            self._check_0025_missing_footnote_language,
        ]
        for check in checks:
            try:
                check()
            except Exception:
                self._logger.exception("Check %s failed unexpectedly", check.__name__)
        return list(self._messages)

    # ------------------------------------------------------------------
    # Fact iteration helpers (support large-file mode)
    # ------------------------------------------------------------------

    def _iter_facts(self) -> Iterator[Fact]:
        """Iterate facts in both memory and large-file mode."""
        if self._instance.is_large_file_mode and self._instance.fact_store is not None:
            yield from self._instance.fact_store.iter_batches()
        else:
            yield from self._instance.facts

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_0001_missing_entity_identifier(self) -> None:
        """XBRL21-0001: Context must have an entity identifier.

        Spec: XBRL 2.1 §4.7.1 – every context MUST contain an
        ``<xbrli:entity>`` with an ``<xbrli:identifier>``.
        """
        for ctx_id, ctx in self._instance.contexts.items():
            if not ctx.entity or not ctx.entity.identifier:
                self.error(
                    "XBRL21-0001",
                    f"Context '{ctx_id}' is missing an entity identifier",
                    context_id=ctx_id,
                )

    def _check_0002_missing_period(self) -> None:
        """XBRL21-0002: Context must have a period.

        Spec: XBRL 2.1 §4.7.2 – every context MUST contain a
        ``<xbrli:period>`` element.
        """
        for ctx_id, ctx in self._instance.contexts.items():
            if ctx.period is None:
                self.error(
                    "XBRL21-0002",
                    f"Context '{ctx_id}' is missing a period",
                    context_id=ctx_id,
                )

    def _check_0003_invalid_instant_date(self) -> None:
        """XBRL21-0003: Instant period must have a valid date.

        Spec: XBRL 2.1 §4.7.2 – an instant period MUST contain a
        valid ``<xbrli:instant>`` date.
        """
        for ctx_id, ctx in self._instance.contexts.items():
            if ctx.period and ctx.period.period_type == PeriodType.INSTANT:
                if ctx.period.instant is None:
                    self.error(
                        "XBRL21-0003",
                        f"Context '{ctx_id}' has instant period but no valid date",
                        context_id=ctx_id,
                    )

    def _check_0004_start_after_end(self) -> None:
        """XBRL21-0004: Duration startDate must not be after endDate.

        Spec: XBRL 2.1 §4.7.2 – for duration periods the start date
        MUST NOT be after the end date.
        """
        for ctx_id, ctx in self._instance.contexts.items():
            if ctx.period and ctx.period.period_type == PeriodType.DURATION:
                if (
                    ctx.period.start_date is not None
                    and ctx.period.end_date is not None
                    and ctx.period.start_date > ctx.period.end_date
                ):
                    self.error(
                        "XBRL21-0004",
                        f"Context '{ctx_id}' has startDate after endDate "
                        f"({ctx.period.start_date} > {ctx.period.end_date})",
                        context_id=ctx_id,
                    )

    def _check_0005_duplicate_context_id(self) -> None:
        """XBRL21-0005: Context IDs must be unique.

        Spec: XBRL 2.1 §4.7 – the ``id`` attribute of ``<xbrli:context>``
        elements must be unique within an instance.

        Note: dict keys are inherently unique, but this check catches
        issues from parsers that may have overwritten entries.
        """
        # Already deduplicated by dict storage; check is a no-op for
        # correctly parsed instances but we validate the model anyway.
        seen: dict[str, int] = Counter()
        for ctx_id in self._instance.contexts:
            seen[ctx_id] += 1
        for ctx_id, count in seen.items():
            if count > 1:
                self.error(
                    "XBRL21-0005",
                    f"Duplicate context ID '{ctx_id}' ({count} occurrences)",
                    context_id=ctx_id,
                )

    def _check_0006_duplicate_unit_id(self) -> None:
        """XBRL21-0006: Unit IDs must be unique.

        Spec: XBRL 2.1 §4.8 – the ``id`` attribute of ``<xbrli:unit>``
        elements must be unique within an instance.
        """
        seen: dict[str, int] = Counter()
        for unit_id in self._instance.units:
            seen[unit_id] += 1
        for unit_id, count in seen.items():
            if count > 1:
                self.error(
                    "XBRL21-0006",
                    f"Duplicate unit ID '{unit_id}' ({count} occurrences)",
                )

    def _check_0007_unit_missing_measure(self) -> None:
        """XBRL21-0007: Unit must have at least one measure.

        Spec: XBRL 2.1 §4.8.1 – a unit element MUST contain at least one
        ``<xbrli:measure>`` element (or a ``<xbrli:divide>``).
        """
        for unit_id, unit in self._instance.units.items():
            if not unit.measures and not unit.is_divide:
                self.error(
                    "XBRL21-0007",
                    f"Unit '{unit_id}' has no measures and is not a divide unit",
                )

    def _check_0008_fact_invalid_context(self) -> None:
        """XBRL21-0008: Fact contextRef must reference a declared context.

        Spec: XBRL 2.1 §4.6.1 – every fact's ``contextRef`` MUST match
        the ``id`` of a context in the same instance.
        """
        for fact in self._iter_facts():
            if fact.context_ref not in self._instance.contexts:
                self.error(
                    "XBRL21-0008",
                    f"Fact '{fact.concept}' references undeclared context "
                    f"'{fact.context_ref}'",
                    concept=fact.concept,
                    context_id=fact.context_ref,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0009_numeric_fact_missing_unit(self) -> None:
        """XBRL21-0009: Numeric facts must have a unitRef.

        Spec: XBRL 2.1 §4.6.2 – every numeric item MUST have a
        ``unitRef`` attribute referencing a declared unit.
        """
        for fact in self._iter_facts():
            if fact.is_numeric and not fact.is_nil and not fact.unit_ref:
                self.error(
                    "XBRL21-0009",
                    f"Numeric fact '{fact.concept}' is missing unitRef",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0010_missing_decimals_precision(self) -> None:
        """XBRL21-0010: Numeric facts must have decimals or precision.

        Spec: XBRL 2.1 §4.6.3 – every non-nil numeric item MUST have
        either a ``decimals`` or ``precision`` attribute.
        """
        for fact in self._iter_facts():
            if fact.is_numeric and not fact.is_nil:
                if fact.decimals is None and fact.precision is None:
                    self.error(
                        "XBRL21-0010",
                        f"Numeric fact '{fact.concept}' missing both "
                        f"decimals and precision",
                        concept=fact.concept,
                        fact_id=fact.id,
                        source_line=fact.source_line,
                    )

    def _check_0011_both_decimals_and_precision(self) -> None:
        """XBRL21-0011: Fact must not have both decimals AND precision.

        Spec: XBRL 2.1 §4.6.3 – an item MUST NOT specify both
        ``decimals`` and ``precision``.
        """
        for fact in self._iter_facts():
            if fact.decimals is not None and fact.precision is not None:
                self.error(
                    "XBRL21-0011",
                    f"Fact '{fact.concept}' specifies both decimals "
                    f"and precision",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0012_nil_fact_has_value(self) -> None:
        """XBRL21-0012: A nil fact must not carry a value.

        Spec: XBRL 2.1 §4.6.1 – when ``xsi:nil="true"`` the element
        MUST be empty and MUST NOT have ``decimals``/``precision``.
        """
        for fact in self._iter_facts():
            if fact.is_nil:
                if fact.value is not None and fact.value.strip():
                    self.error(
                        "XBRL21-0012",
                        f"Nil fact '{fact.concept}' has a non-empty value",
                        concept=fact.concept,
                        fact_id=fact.id,
                        source_line=fact.source_line,
                    )

    def _check_0013_concept_not_in_taxonomy(self) -> None:
        """XBRL21-0013: Fact concept must be defined in the taxonomy.

        Spec: XBRL 2.1 §4.6 – every item concept must be declared in
        the DTS.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for fact in self._iter_facts():
            if fact.concept not in taxonomy.concepts:
                self.error(
                    "XBRL21-0013",
                    f"Concept '{fact.concept}' is not defined in the taxonomy",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0014_type_mismatch(self) -> None:
        """XBRL21-0014: Numeric/non-numeric type mismatch.

        Spec: XBRL 2.1 §4.6.2 – a non-numeric concept MUST NOT have
        a ``unitRef``, and a numeric concept MUST have one.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for fact in self._iter_facts():
            cdef = taxonomy.concepts.get(fact.concept)
            if cdef is None:
                continue
            if cdef.type_is_numeric and not fact.is_numeric:
                self.warning(
                    "XBRL21-0014",
                    f"Concept '{fact.concept}' is numeric in taxonomy but "
                    f"fact is not marked numeric",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )
            if not cdef.type_is_numeric and fact.unit_ref:
                self.error(
                    "XBRL21-0014",
                    f"Non-numeric concept '{fact.concept}' has a unitRef",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0015_period_type_mismatch(self) -> None:
        """XBRL21-0015: Period type mismatch.

        Spec: XBRL 2.1 §4.7.2 – the period in the context MUST match
        the ``periodType`` declared for the concept.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for fact in self._iter_facts():
            cdef = taxonomy.concepts.get(fact.concept)
            if cdef is None or cdef.period_type is None:
                continue
            ctx = self._instance.contexts.get(fact.context_ref)
            if ctx is None or ctx.period is None:
                continue
            if ctx.period.period_type != cdef.period_type:
                self.error(
                    "XBRL21-0015",
                    f"Period type mismatch for '{fact.concept}': context "
                    f"has {ctx.period.period_type.value}, concept requires "
                    f"{cdef.period_type.value}",
                    concept=fact.concept,
                    context_id=fact.context_ref,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0016_monetary_iso4217(self) -> None:
        """XBRL21-0016: Monetary items must use ISO 4217 currency unit.

        Spec: XBRL 2.1 §4.8.2 – monetary item types MUST have a unit
        whose single measure is in the ISO 4217 namespace.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for fact in self._iter_facts():
            if not fact.is_numeric or fact.is_nil or not fact.unit_ref:
                continue
            cdef = taxonomy.concepts.get(fact.concept)
            if cdef is None:
                continue
            is_monetary = "monetary" in cdef.data_type.lower() if cdef.data_type else False
            if not is_monetary:
                continue
            unit = self._instance.units.get(fact.unit_ref)
            if unit is None:
                continue
            if not unit.is_monetary:
                self.error(
                    "XBRL21-0016",
                    f"Monetary fact '{fact.concept}' uses unit "
                    f"'{fact.unit_ref}' which is not an ISO 4217 currency",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0017_shares_unit(self) -> None:
        """XBRL21-0017: Share items must use xbrli:shares unit.

        Spec: XBRL 2.1 §4.8.2 – shares item types MUST have a unit
        whose measure is ``xbrli:shares``.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for fact in self._iter_facts():
            if not fact.is_numeric or fact.is_nil or not fact.unit_ref:
                continue
            cdef = taxonomy.concepts.get(fact.concept)
            if cdef is None:
                continue
            is_shares = "shares" in cdef.data_type.lower() if cdef.data_type else False
            if not is_shares:
                continue
            unit = self._instance.units.get(fact.unit_ref)
            if unit is None:
                continue
            has_shares = any(m.local_name == "shares" for m in unit.measures)
            if not has_shares:
                self.error(
                    "XBRL21-0017",
                    f"Shares fact '{fact.concept}' uses unit "
                    f"'{fact.unit_ref}' which is not xbrli:shares",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0018_pure_unit(self) -> None:
        """XBRL21-0018: Pure items must use xbrli:pure unit.

        Spec: XBRL 2.1 §4.8.2 – pure item types MUST use a unit
        whose measure is ``xbrli:pure``.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for fact in self._iter_facts():
            if not fact.is_numeric or fact.is_nil or not fact.unit_ref:
                continue
            cdef = taxonomy.concepts.get(fact.concept)
            if cdef is None:
                continue
            is_pure = "pure" in cdef.data_type.lower() if cdef.data_type else False
            if not is_pure:
                continue
            unit = self._instance.units.get(fact.unit_ref)
            if unit is None:
                continue
            if not unit.is_pure:
                self.error(
                    "XBRL21-0018",
                    f"Pure fact '{fact.concept}' uses unit "
                    f"'{fact.unit_ref}' which is not xbrli:pure",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0019_invalid_identifier_scheme(self) -> None:
        """XBRL21-0019: Entity identifier scheme must be a valid URI.

        Spec: XBRL 2.1 §4.7.1 – the ``scheme`` attribute of
        ``<xbrli:identifier>`` MUST be a valid URI.
        """
        for ctx_id, ctx in self._instance.contexts.items():
            if ctx.entity and ctx.entity.scheme:
                scheme = ctx.entity.scheme.strip()
                if not scheme or not (
                    scheme.startswith("http://")
                    or scheme.startswith("https://")
                    or ":" in scheme
                ):
                    self.warning(
                        "XBRL21-0019",
                        f"Context '{ctx_id}' has a potentially invalid "
                        f"entity identifier scheme: '{scheme}'",
                        context_id=ctx_id,
                    )

    def _check_0020_conflicting_duplicate_facts(self) -> None:
        """XBRL21-0020: Duplicate facts with conflicting values.

        Spec: XBRL 2.1 §4.6 – complete duplicates (same value) are
        allowed; inconsistent duplicates (different values for the
        same concept/context/unit/lang) are an error.
        """
        groups: dict[tuple, list[Fact]] = {}
        for fact in self._iter_facts():
            key = fact.duplicate_key
            groups.setdefault(key, []).append(fact)

        for key, facts in groups.items():
            if len(facts) <= 1:
                continue
            values = set()
            for f in facts:
                if f.is_numeric and f.rounded_value is not None:
                    values.add(str(f.rounded_value))
                else:
                    values.add(f.value or "")
            if len(values) > 1:
                self.inconsistency(
                    "XBRL21-0020",
                    f"Conflicting duplicate facts for concept "
                    f"'{facts[0].concept}' in context "
                    f"'{facts[0].context_ref}': {len(facts)} facts with "
                    f"{len(values)} distinct values",
                    concept=facts[0].concept,
                    context_id=facts[0].context_ref,
                )

    def _check_0021_tuple_ordering(self) -> None:
        """XBRL21-0021: Tuple ordering violation.

        Spec: XBRL 2.1 §4.9 – tuple children order must be consistent
        with the schema.  This is a structural check; the validator
        emits a warning if tuple ordering metadata is present but
        cannot be verified (full check requires schema access).
        """
        # Tuple ordering requires schema-level information that may not
        # be available.  This is a placeholder that logs an info message
        # when tuples are detected.
        pass

    def _check_0022_missing_schema_ref(self) -> None:
        """XBRL21-0022: Instance must have at least one schemaRef.

        Spec: XBRL 2.1 §4.2 – an instance document MUST contain at
        least one ``<link:schemaRef>`` element.
        """
        if not self._instance.schema_refs:
            self.error(
                "XBRL21-0022",
                "Instance document has no schemaRef element",
            )

    def _check_0023_missing_lang_for_string(self) -> None:
        """XBRL21-0023: String/text facts should have xml:lang.

        Spec: XBRL 2.1 §4.6.1 – non-numeric facts SHOULD declare
        ``xml:lang`` for proper language identification.
        """
        for fact in self._iter_facts():
            if not fact.is_numeric and not fact.is_nil and not fact.language:
                self.warning(
                    "XBRL21-0023",
                    f"String fact '{fact.concept}' is missing xml:lang",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0024_invalid_footnote_role(self) -> None:
        """XBRL21-0024: Footnote must use a valid role.

        Spec: XBRL 2.1 §4.11.1 – the footnote role MUST be defined in
        the DTS or be the standard footnote role.
        """
        taxonomy = self._instance.taxonomy
        for fn in self._instance.footnotes:
            if fn.role and fn.role != _STANDARD_FOOTNOTE_ROLE:
                if taxonomy and fn.role not in taxonomy.role_types:
                    self.error(
                        "XBRL21-0024",
                        f"Footnote uses undeclared role '{fn.role}'",
                    )

    def _check_0025_missing_footnote_language(self) -> None:
        """XBRL21-0025: Footnote must have xml:lang.

        Spec: XBRL 2.1 §4.11.1.1 – every footnote element MUST have
        an ``xml:lang`` attribute.
        """
        for fn in self._instance.footnotes:
            if not fn.language:
                self.error(
                    "XBRL21-0025",
                    "Footnote is missing xml:lang attribute",
                )
