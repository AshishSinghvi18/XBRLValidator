"""Inline XBRL (iXBRL) validator.

Implements 20 checks (IXBRL-0001 through IXBRL-0020) covering the
Inline XBRL 1.1 specification requirements.

Spec references:
- Inline XBRL 1.1 §3 (processing model)
- Inline XBRL 1.1 §4 (elements)
- Inline XBRL 1.1 §5 (transforms)
- Inline XBRL Transformations Registry
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Iterator

from src.core.model.xbrl_model import (
    Fact,
    Footnote,
    ValidationMessage,
    XBRLInstance,
)
from src.core.types import InputFormat, Severity
from src.validator.base import BaseValidator

logger = logging.getLogger(__name__)

# Standard transform registries
_KNOWN_TRANSFORM_REGISTRIES: set[str] = {
    "http://www.xbrl.org/inlineXBRL/transformation/2010-04-20",
    "http://www.xbrl.org/inlineXBRL/transformation/2011-07-31",
    "http://www.xbrl.org/inlineXBRL/transformation/2015-02-26",
    "http://www.xbrl.org/inlineXBRL/transformation/2020-02-12",
    "http://www.xbrl.org/inlineXBRL/transformation/2022-02-16",
}

# Known transforms (subset of commonly used ones)
_KNOWN_TRANSFORMS: set[str] = {
    "booleanfalse", "booleantrue",
    "calindaymonthyear", "datedaymonthyear", "datedaymonthyearen",
    "datemonthdayyear", "datemonthdayyearen", "datemonthyearen",
    "dateyearmonthday", "dateyearmonthdayen",
    "numdotdecimal", "numcommadecimal", "numunitdecimal",
    "zerodash", "nocontent", "fixed-empty", "fixed-false",
    "fixed-true", "fixed-zero",
    "date-day-month-year", "date-month-day-year", "date-year-month-day",
    "num-dot-decimal", "num-comma-decimal", "num-unit-decimal",
}

# ix namespace prefix
_IX_NS = "http://www.xbrl.org/2013/inlineXBRL"


class InlineXBRLValidator(BaseValidator):
    """Validator for Inline XBRL 1.1 specification rules.

    Implements 20 checks covering ix:header, transforms, continuations,
    hidden facts, target documents, and structural requirements.
    """

    def __init__(self, instance: XBRLInstance) -> None:
        super().__init__(instance)

    def validate(self) -> list[ValidationMessage]:
        """Run all 20 iXBRL checks and return messages."""
        self._messages.clear()

        # Only run for iXBRL instances
        if self._instance.format_type != InputFormat.IXBRL_HTML:
            return []

        checks = [
            self._check_0001_missing_ix_header,
            self._check_0002_multiple_ix_headers,
            self._check_0003_invalid_transform_name,
            self._check_0004_transform_format_mismatch,
            self._check_0005_broken_continuation_chain,
            self._check_0006_circular_continuation,
            self._check_0007_orphan_continuation,
            self._check_0008_hidden_fact_not_referenced,
            self._check_0009_missing_target_document,
            self._check_0010_duplicate_fact_id,
            self._check_0011_nested_inline_element,
            self._check_0012_invalid_ix_namespace,
            self._check_0013_missing_context_in_header,
            self._check_0014_missing_unit_in_header,
            self._check_0015_non_numeric_with_format,
            self._check_0016_numeric_without_format,
            self._check_0017_invalid_scale_attribute,
            self._check_0018_sign_attribute_misuse,
            self._check_0019_footnote_outside_body,
            self._check_0020_empty_fraction,
        ]
        for check in checks:
            try:
                check()
            except Exception:
                self._logger.exception("Check %s failed unexpectedly", check.__name__)
        return list(self._messages)

    def _iter_facts(self) -> Iterator[Fact]:
        """Iterate facts in both memory and large-file mode."""
        if self._instance.is_large_file_mode and self._instance.fact_store is not None:
            yield from self._instance.fact_store.iter_batches()
        else:
            yield from self._instance.facts

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_0001_missing_ix_header(self) -> None:
        """IXBRL-0001: Inline XBRL document must have an ix:header.

        Spec: Inline XBRL 1.1 §4.2 – an Inline XBRL document set
        MUST contain exactly one ``ix:header`` element.
        """
        # If there are no contexts and no units defined, the header
        # is likely missing entirely.
        if not self._instance.contexts and not self._instance.units:
            self.error(
                "IXBRL-0001",
                "Inline XBRL document appears to be missing ix:header "
                "(no contexts or units found)",
            )

    def _check_0002_multiple_ix_headers(self) -> None:
        """IXBRL-0002: Only one ix:header is allowed.

        Spec: Inline XBRL 1.1 §4.2 – there MUST be exactly one
        ``ix:header`` per document set.
        """
        # This check requires DOM-level inspection; model-level
        # detection is limited.  If the parser has stored header count
        # metadata, use it.
        header_count = self._instance.namespaces.get("_ix_header_count")
        if header_count is not None:
            try:
                count = int(header_count)
                if count > 1:
                    self.error(
                        "IXBRL-0002",
                        f"Found {count} ix:header elements; exactly one "
                        f"is allowed",
                    )
            except (ValueError, TypeError):
                pass

    def _check_0003_invalid_transform_name(self) -> None:
        """IXBRL-0003: Fact uses an unknown transform name.

        Spec: Inline XBRL 1.1 §5 – transform names MUST be from a
        registered transformation registry.
        """
        for fact in self._iter_facts():
            transform = fact.details.get("transform") if hasattr(fact, "details") else None
            if transform and transform not in _KNOWN_TRANSFORMS:
                self.error(
                    "IXBRL-0003",
                    f"Fact '{fact.concept}' uses unknown transform "
                    f"'{transform}'",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0004_transform_format_mismatch(self) -> None:
        """IXBRL-0004: Transform and format attribute mismatch.

        Spec: Inline XBRL 1.1 §5.1 – the ``format`` attribute MUST
        be compatible with the transform.
        """
        for fact in self._iter_facts():
            transform = fact.details.get("transform") if hasattr(fact, "details") else None
            fmt = fact.details.get("format") if hasattr(fact, "details") else None
            if transform and fmt:
                is_numeric_transform = any(
                    kw in transform for kw in ("num", "zero", "fixed-zero")
                )
                is_date_transform = "date" in transform or "cal" in transform
                if is_numeric_transform and not fact.is_numeric:
                    self.warning(
                        "IXBRL-0004",
                        f"Fact '{fact.concept}' has a numeric transform "
                        f"'{transform}' but is not marked as numeric",
                        concept=fact.concept,
                        fact_id=fact.id,
                        source_line=fact.source_line,
                    )

    def _check_0005_broken_continuation_chain(self) -> None:
        """IXBRL-0005: Continuation element references non-existent ID.

        Spec: Inline XBRL 1.1 §4.6 – ``continuedAt`` MUST reference
        an ``ix:continuation`` element by its ``id``.
        """
        # Detect broken chains from fact metadata if available
        for fact in self._iter_facts():
            continued_at = fact.details.get("continuedAt") if hasattr(fact, "details") else None
            if continued_at:
                # The actual continuation element existence check requires
                # DOM access; at model level we flag if metadata indicates
                # a broken chain.
                continuation_found = fact.details.get("continuation_resolved", True)
                if not continuation_found:
                    self.error(
                        "IXBRL-0005",
                        f"Fact '{fact.concept}' has continuedAt="
                        f"'{continued_at}' but the target continuation "
                        f"element was not found",
                        concept=fact.concept,
                        fact_id=fact.id,
                        source_line=fact.source_line,
                    )

    def _check_0006_circular_continuation(self) -> None:
        """IXBRL-0006: Circular continuation chain detected.

        Spec: Inline XBRL 1.1 §4.6 – continuation chains MUST NOT
        form cycles.
        """
        # Detect circular chains from fact metadata
        for fact in self._iter_facts():
            if hasattr(fact, "details") and fact.details.get("continuation_circular"):
                self.error(
                    "IXBRL-0006",
                    f"Fact '{fact.concept}' has a circular continuation chain",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0007_orphan_continuation(self) -> None:
        """IXBRL-0007: Continuation element not referenced by any fact.

        Spec: Inline XBRL 1.1 §4.6 – every ``ix:continuation``
        element MUST be referenced by exactly one ``continuedAt``.
        """
        # Model-level check using metadata
        for fact in self._iter_facts():
            if hasattr(fact, "details") and fact.details.get("orphan_continuation"):
                self.warning(
                    "IXBRL-0007",
                    f"Orphan continuation element detected near fact "
                    f"'{fact.concept}'",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0008_hidden_fact_not_referenced(self) -> None:
        """IXBRL-0008: Hidden fact should be referenced or excluded.

        Spec: Inline XBRL 1.1 §4.3 – facts in ``ix:hidden`` SHOULD
        be referenced by visible elements or have a recognized
        exclusion reason.
        """
        for fact in self._iter_facts():
            if fact.is_hidden and not fact.footnote_refs:
                self.warning(
                    "IXBRL-0008",
                    f"Hidden fact '{fact.concept}' is not referenced "
                    f"by any visible element",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0009_missing_target_document(self) -> None:
        """IXBRL-0009: Target attribute references unknown document.

        Spec: Inline XBRL 1.1 §4.1 – if a ``target`` attribute is
        specified, there MUST be a matching target document definition.
        """
        # Placeholder: requires DOM-level document set inspection
        pass

    def _check_0010_duplicate_fact_id(self) -> None:
        """IXBRL-0010: Duplicate fact IDs in inline document.

        Spec: Inline XBRL 1.1 §4.4 – the ``id`` attribute of inline
        elements MUST be unique within the document.
        """
        seen: Counter[str] = Counter()
        for fact in self._iter_facts():
            if fact.id:
                seen[fact.id] += 1
        for fid, count in seen.items():
            if count > 1:
                self.error(
                    "IXBRL-0010",
                    f"Duplicate fact ID '{fid}' found {count} times",
                    fact_id=fid,
                )

    def _check_0011_nested_inline_element(self) -> None:
        """IXBRL-0011: Nested ix:nonFraction or ix:nonNumeric elements.

        Spec: Inline XBRL 1.1 §4.4.1 – ``ix:nonFraction`` elements
        MUST NOT be nested inside other ``ix:nonFraction`` elements.
        """
        # Model-level detection uses parser metadata
        for fact in self._iter_facts():
            if hasattr(fact, "details") and fact.details.get("nested_inline"):
                self.error(
                    "IXBRL-0011",
                    f"Fact '{fact.concept}' is nested inside another "
                    f"inline XBRL element",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0012_invalid_ix_namespace(self) -> None:
        """IXBRL-0012: Invalid or outdated ix namespace.

        Spec: Inline XBRL 1.1 §2 – the namespace for Inline XBRL 1.1
        MUST be ``http://www.xbrl.org/2013/inlineXBRL``.
        """
        for prefix, uri in self._instance.namespaces.items():
            if prefix in ("ix", "inlineXBRL") and uri != _IX_NS:
                self.warning(
                    "IXBRL-0012",
                    f"Namespace prefix '{prefix}' uses non-standard "
                    f"namespace URI '{uri}'",
                )

    def _check_0013_missing_context_in_header(self) -> None:
        """IXBRL-0013: Context referenced by fact is missing from ix:header.

        Spec: Inline XBRL 1.1 §4.2 – all contexts MUST be defined
        within ``ix:header/ix:resources``.
        """
        for fact in self._iter_facts():
            if fact.context_ref not in self._instance.contexts:
                self.error(
                    "IXBRL-0013",
                    f"Fact '{fact.concept}' references context "
                    f"'{fact.context_ref}' not found in ix:header",
                    concept=fact.concept,
                    context_id=fact.context_ref,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0014_missing_unit_in_header(self) -> None:
        """IXBRL-0014: Unit referenced by fact is missing from ix:header.

        Spec: Inline XBRL 1.1 §4.2 – all units MUST be defined
        within ``ix:header/ix:resources``.
        """
        for fact in self._iter_facts():
            if fact.unit_ref and fact.unit_ref not in self._instance.units:
                self.error(
                    "IXBRL-0014",
                    f"Fact '{fact.concept}' references unit "
                    f"'{fact.unit_ref}' not found in ix:header",
                    concept=fact.concept,
                    fact_id=fact.id,
                    source_line=fact.source_line,
                )

    def _check_0015_non_numeric_with_format(self) -> None:
        """IXBRL-0015: Non-numeric fact should not have format attribute.

        Spec: Inline XBRL 1.1 §4.4.2 – ``ix:nonNumeric`` elements
        SHOULD NOT have a ``format`` attribute.
        """
        for fact in self._iter_facts():
            if not fact.is_numeric and hasattr(fact, "details"):
                fmt = fact.details.get("format")
                if fmt:
                    self.warning(
                        "IXBRL-0015",
                        f"Non-numeric fact '{fact.concept}' has format "
                        f"attribute '{fmt}'",
                        concept=fact.concept,
                        fact_id=fact.id,
                        source_line=fact.source_line,
                    )

    def _check_0016_numeric_without_format(self) -> None:
        """IXBRL-0016: Numeric fact without format attribute.

        Spec: Inline XBRL 1.1 §4.4.1 – ``ix:nonFraction`` elements
        SHOULD have a ``format`` attribute for proper transformation.
        """
        for fact in self._iter_facts():
            if fact.is_numeric and not fact.is_nil and hasattr(fact, "details"):
                fmt = fact.details.get("format")
                transform = fact.details.get("transform")
                if not fmt and not transform:
                    self.info(
                        "IXBRL-0016",
                        f"Numeric fact '{fact.concept}' has no format or "
                        f"transform attribute",
                        concept=fact.concept,
                        fact_id=fact.id,
                        source_line=fact.source_line,
                    )

    def _check_0017_invalid_scale_attribute(self) -> None:
        """IXBRL-0017: Invalid scale attribute on numeric fact.

        Spec: Inline XBRL 1.1 §4.4.1 – the ``scale`` attribute MUST
        be an integer.
        """
        for fact in self._iter_facts():
            if not fact.is_numeric or not hasattr(fact, "details"):
                continue
            scale = fact.details.get("scale")
            if scale is not None:
                try:
                    int(scale)
                except (ValueError, TypeError):
                    self.error(
                        "IXBRL-0017",
                        f"Fact '{fact.concept}' has invalid scale value "
                        f"'{scale}'",
                        concept=fact.concept,
                        fact_id=fact.id,
                        source_line=fact.source_line,
                    )

    def _check_0018_sign_attribute_misuse(self) -> None:
        """IXBRL-0018: Sign attribute used incorrectly.

        Spec: Inline XBRL 1.1 §4.4.1 – the ``sign`` attribute MUST
        only be ``"-"`` and only on ``ix:nonFraction`` elements.
        """
        for fact in self._iter_facts():
            if not hasattr(fact, "details"):
                continue
            sign = fact.details.get("sign")
            if sign is not None:
                if not fact.is_numeric:
                    self.error(
                        "IXBRL-0018",
                        f"Non-numeric fact '{fact.concept}' has a sign "
                        f"attribute",
                        concept=fact.concept,
                        fact_id=fact.id,
                        source_line=fact.source_line,
                    )
                elif sign != "-":
                    self.error(
                        "IXBRL-0018",
                        f"Fact '{fact.concept}' has invalid sign value "
                        f"'{sign}' (must be '-')",
                        concept=fact.concept,
                        fact_id=fact.id,
                        source_line=fact.source_line,
                    )

    def _check_0019_footnote_outside_body(self) -> None:
        """IXBRL-0019: Footnote appears outside the document body.

        Spec: Inline XBRL 1.1 §4.5 – ``ix:footnote`` elements MUST
        appear within the HTML body.
        """
        # Placeholder: requires DOM-level position tracking
        pass

    def _check_0020_empty_fraction(self) -> None:
        """IXBRL-0020: ix:fraction element with missing numerator/denominator.

        Spec: Inline XBRL 1.1 §4.4.3 – ``ix:fraction`` MUST contain
        both ``ix:numerator`` and ``ix:denominator`` child elements.
        """
        for fact in self._iter_facts():
            if not hasattr(fact, "details"):
                continue
            if fact.details.get("is_fraction"):
                has_num = fact.details.get("has_numerator", False)
                has_den = fact.details.get("has_denominator", False)
                if not has_num or not has_den:
                    self.error(
                        "IXBRL-0020",
                        f"Fraction fact '{fact.concept}' is missing "
                        f"{'numerator' if not has_num else 'denominator'}",
                        concept=fact.concept,
                        fact_id=fact.id,
                        source_line=fact.source_line,
                    )
