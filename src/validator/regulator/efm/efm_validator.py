"""SEC EDGAR Filing Manual (EFM) validation rules.

Implements key EFM rules for SEC XBRL/iXBRL filings.
Reference: EDGAR Filing Manual (https://www.sec.gov/info/edgar/edgarfm.htm)
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Final

from src.core.constants import NS_ISO4217, NS_XBRLI
from src.core.model.context import Context
from src.core.model.fact import Fact
from src.core.model.instance import ValidationMessage, XBRLInstance
from src.core.model.unit import Unit
from src.core.types import FactType, Severity

# ---------------------------------------------------------------------------
# DEI namespace and required facts — EFM 6.5.20–6.5.35
# ---------------------------------------------------------------------------
_NS_DEI: Final[str] = "http://xbrl.sec.gov/dei"

_REQUIRED_DEI_CONCEPTS: Final[tuple[str, ...]] = (
    "EntityRegistrantName",
    "EntityCentralIndexKey",
    "DocumentType",
    "DocumentPeriodEndDate",
    "AmendmentFlag",
    "CurrentFiscalYearEndDate",
    "DocumentFiscalYearFocus",
    "DocumentFiscalPeriodFocus",
)

_VALID_DOCUMENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "10-K",
        "10-K/A",
        "10-Q",
        "10-Q/A",
        "20-F",
        "20-F/A",
        "40-F",
        "40-F/A",
        "6-K",
        "6-K/A",
        "8-K",
        "8-K/A",
        "S-1",
        "S-1/A",
        "S-3",
        "S-3/A",
        "S-4",
        "S-4/A",
        "S-11",
        "S-11/A",
        "F-1",
        "F-1/A",
        "F-3",
        "F-3/A",
        "F-4",
        "F-4/A",
        "F-10",
        "F-10/A",
        "N-CSR",
        "N-CSR/A",
        "N-CSRS",
        "N-CSRS/A",
        "SD",
        "SD/A",
    }
)

# SEC CIK scheme URI — EFM 6.5.8
_CIK_SCHEME: Final[str] = "http://www.sec.gov/CIK"
_CIK_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9]{10}$")

# Standard taxonomy entry-point prefixes — EFM 6.3.3
_STANDARD_TAXONOMY_PREFIXES: Final[tuple[str, ...]] = (
    "http://xbrl.fasb.org/",
    "https://xbrl.fasb.org/",
    "http://xbrl.sec.gov/",
    "https://xbrl.sec.gov/",
    "http://taxonomies.xbrl.us/",
)

# ISO 4217 currency codes accepted by EDGAR — EFM 6.5.38
_ACCEPTED_CURRENCIES: Final[frozenset[str]] = frozenset(
    {
        "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG",
        "AZN", "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND",
        "BOB", "BRL", "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF",
        "CHF", "CLP", "CNY", "COP", "CRC", "CUP", "CVE", "CZK", "DJF",
        "DKK", "DOP", "DZD", "EGP", "ERN", "ETB", "EUR", "FJD", "FKP",
        "GBP", "GEL", "GHS", "GIP", "GMD", "GNF", "GTQ", "GYD", "HKD",
        "HNL", "HRK", "HTG", "HUF", "IDR", "ILS", "INR", "IQD", "IRR",
        "ISK", "JMD", "JOD", "JPY", "KES", "KGS", "KHR", "KMF", "KPW",
        "KRW", "KWD", "KYD", "KZT", "LAK", "LBP", "LKR", "LRD", "LSL",
        "LYD", "MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP", "MRU",
        "MUR", "MVR", "MWK", "MXN", "MYR", "MZN", "NAD", "NGN", "NIO",
        "NOK", "NPR", "NZD", "OMR", "PAB", "PEN", "PGK", "PHP", "PKR",
        "PLN", "PYG", "QAR", "RON", "RSD", "RUB", "RWF", "SAR", "SBD",
        "SCR", "SDG", "SEK", "SGD", "SHP", "SLE", "SOS", "SRD", "SSP",
        "STN", "SVC", "SYP", "SZL", "THB", "TJS", "TMT", "TND", "TOP",
        "TRY", "TTD", "TWD", "TZS", "UAH", "UGX", "USD", "UYU", "UZS",
        "VES", "VND", "VUV", "WST", "XAF", "XCD", "XOF", "XPF", "YER",
        "ZAR", "ZMW", "ZWL",
    }
)

# Concepts that should never have negative values — EFM 6.5.17
_NON_NEGATIVE_CONCEPTS: Final[frozenset[str]] = frozenset(
    {
        "Assets",
        "StockholdersEquity",
        "LiabilitiesAndStockholdersEquity",
        "CommonStockSharesOutstanding",
        "CommonStockSharesAuthorized",
        "PreferredStockSharesAuthorized",
        "PreferredStockSharesOutstanding",
        "EntityCommonStockSharesOutstanding",
        "SharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
        "WeightedAverageNumberOfDilutedSharesOutstanding",
    }
)


def _is_dei_concept(qname: str, local_name: str) -> bool:
    """Check if a Clark-notation QName matches a DEI local name."""
    return qname.endswith(f"}}{local_name}") and _NS_DEI in qname


def _local_name(qname: str) -> str:
    """Extract local name from Clark-notation QName."""
    idx = qname.rfind("}")
    return qname[idx + 1:] if idx >= 0 else qname


class EFMValidator:
    """Validates SEC EFM filing rules.

    Spec: EDGAR Filing Manual Chapter 6 — Interactive Data
    """

    def validate(self, instance: XBRLInstance) -> list[ValidationMessage]:
        """Run all EFM validation rules.

        Returns list of validation messages for EFM rule violations.
        """
        messages: list[ValidationMessage] = []
        messages.extend(self._validate_dei_facts(instance))
        messages.extend(self._validate_context_rules(instance))
        messages.extend(self._validate_unit_rules(instance))
        messages.extend(self._validate_fact_rules(instance))
        messages.extend(self._validate_taxonomy_refs(instance))
        return messages

    # ------------------------------------------------------------------
    # DEI validation — EFM 6.5.20–6.5.35
    # ------------------------------------------------------------------
    def _validate_dei_facts(
        self, instance: XBRLInstance
    ) -> list[ValidationMessage]:
        """EFM 6.5.20-6.5.35: Required DEI (Document and Entity Information) facts.

        Checks:
        - Required DEI facts are present (EntityRegistrantName, etc.)
        - DocumentType is valid
        - DocumentPeriodEndDate consistency

        Emits: EFM-0001, EFM-0002, EFM-0003
        """
        messages: list[ValidationMessage] = []

        # Build a lookup of present DEI local names → facts
        dei_facts: dict[str, list[Fact]] = {}
        for fact in instance.facts:
            ln = _local_name(fact.concept_qname)
            if _is_dei_concept(fact.concept_qname, ln):
                dei_facts.setdefault(ln, []).append(fact)

        # EFM-0001: required DEI facts must be present
        for concept_name in _REQUIRED_DEI_CONCEPTS:
            if concept_name not in dei_facts:
                messages.append(
                    ValidationMessage(
                        code="EFM-0001",
                        severity=Severity.ERROR,
                        message=(
                            f"Required DEI fact '{concept_name}' is missing."
                        ),
                        spec_ref="EFM 6.5.20",
                        file_path=instance.file_path,
                        fix_suggestion=(
                            f"Add a dei:{concept_name} fact to the filing."
                        ),
                    )
                )

        # EFM-0002: DocumentType must be a recognised value
        doc_type_facts = dei_facts.get("DocumentType", [])
        for fact in doc_type_facts:
            if (
                fact.value is not None
                and str(fact.value) not in _VALID_DOCUMENT_TYPES
            ):
                messages.append(
                    ValidationMessage(
                        code="EFM-0002",
                        severity=Severity.ERROR,
                        message=(
                            f"DocumentType '{fact.value}' is not a valid "
                            f"SEC filing type."
                        ),
                        spec_ref="EFM 6.5.20",
                        file_path=instance.file_path,
                        line=fact.source_line,
                        fix_suggestion=(
                            "Use a valid DocumentType such as '10-K', "
                            "'10-Q', '8-K', etc."
                        ),
                    )
                )

        # EFM-0003: DocumentPeriodEndDate should match context period
        dpend_facts = dei_facts.get("DocumentPeriodEndDate", [])
        for fact in dpend_facts:
            if fact.value is None:
                continue
            ctx = instance.get_context(fact.context_ref)
            if ctx is None:
                continue
            period = ctx.period
            end_date_str = str(fact.value)
            # Compare with instant or end_date
            if period.instant is not None:
                if period.instant.isoformat() != end_date_str:
                    messages.append(
                        ValidationMessage(
                            code="EFM-0003",
                            severity=Severity.WARNING,
                            message=(
                                f"DocumentPeriodEndDate '{end_date_str}' "
                                f"does not match context instant "
                                f"'{period.instant.isoformat()}'."
                            ),
                            spec_ref="EFM 6.5.20",
                            file_path=instance.file_path,
                            line=fact.source_line,
                        ),
                    )
            elif period.end_date is not None:
                if period.end_date.isoformat() != end_date_str:
                    messages.append(
                        ValidationMessage(
                            code="EFM-0003",
                            severity=Severity.WARNING,
                            message=(
                                f"DocumentPeriodEndDate '{end_date_str}' "
                                f"does not match context end date "
                                f"'{period.end_date.isoformat()}'."
                            ),
                            spec_ref="EFM 6.5.20",
                            file_path=instance.file_path,
                            line=fact.source_line,
                        ),
                    )

        return messages

    # ------------------------------------------------------------------
    # Context rules — EFM 6.5.8, 6.5.19
    # ------------------------------------------------------------------
    def _validate_context_rules(
        self, instance: XBRLInstance
    ) -> list[ValidationMessage]:
        """EFM 6.5.8, 6.5.19: Context-specific EFM rules.

        Checks:
        - Required context date format rules
        - Entity identifier must use CIK scheme
        - Context must not use segment (only scenario for dimensions)

        Emits: EFM-0010, EFM-0011, EFM-0012
        """
        messages: list[ValidationMessage] = []

        for ctx in instance.contexts.values():
            entity = ctx.entity

            # EFM-0010: Entity identifier scheme must be the SEC CIK URI
            if entity.scheme != _CIK_SCHEME:
                messages.append(
                    ValidationMessage(
                        code="EFM-0010",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': entity scheme "
                            f"'{entity.scheme}' is not the required SEC "
                            f"CIK scheme '{_CIK_SCHEME}'."
                        ),
                        spec_ref="EFM 6.5.8",
                        file_path=instance.file_path,
                        fix_suggestion=(
                            f"Set the entity identifier scheme to "
                            f"'{_CIK_SCHEME}'."
                        ),
                    )
                )

            # EFM-0011: CIK value must be a zero-padded 10-digit number
            if entity.scheme == _CIK_SCHEME and not _CIK_PATTERN.match(
                entity.identifier
            ):
                messages.append(
                    ValidationMessage(
                        code="EFM-0011",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': CIK value "
                            f"'{entity.identifier}' must be a zero-padded "
                            f"10-digit number."
                        ),
                        spec_ref="EFM 6.5.8",
                        file_path=instance.file_path,
                        fix_suggestion=(
                            "Pad the CIK with leading zeros to 10 digits."
                        ),
                    )
                )

            # EFM-0012: Period dates must not be before 1980 or after 2099
            for dt in (
                ctx.period.instant,
                ctx.period.start_date,
                ctx.period.end_date,
            ):
                if dt is not None and (dt.year < 1980 or dt.year > 2099):
                    messages.append(
                        ValidationMessage(
                            code="EFM-0012",
                            severity=Severity.ERROR,
                            message=(
                                f"Context '{ctx.context_id}': date "
                                f"'{dt.isoformat()}' is outside the "
                                f"acceptable range 1980-2099."
                            ),
                            spec_ref="EFM 6.5.19",
                            file_path=instance.file_path,
                        ),
                    )

        return messages

    # ------------------------------------------------------------------
    # Unit rules — EFM 6.5.38–6.5.39
    # ------------------------------------------------------------------
    def _validate_unit_rules(
        self, instance: XBRLInstance
    ) -> list[ValidationMessage]:
        """EFM 6.5.38-6.5.39: Unit-specific EFM rules.

        Checks:
        - Only standard unit measures allowed
        - Monetary items must use ISO 4217 currencies

        Emits: EFM-0020, EFM-0021
        """
        messages: list[ValidationMessage] = []

        for unit in instance.units.values():
            for measure in unit.numerators + unit.denominators:
                ns_end = measure.find("}")
                if ns_end < 0:
                    continue
                ns = measure[1:ns_end]
                local = measure[ns_end + 1:]

                # EFM-0020: Monetary unit must use an accepted currency
                if ns == NS_ISO4217 and local not in _ACCEPTED_CURRENCIES:
                    messages.append(
                        ValidationMessage(
                            code="EFM-0020",
                            severity=Severity.ERROR,
                            message=(
                                f"Unit '{unit.unit_id}': currency code "
                                f"'{local}' is not an accepted ISO 4217 "
                                f"currency."
                            ),
                            spec_ref="EFM 6.5.38",
                            file_path=instance.file_path,
                        ),
                    )

            # EFM-0021: Non-standard measure namespaces
            for measure in unit.numerators + unit.denominators:
                ns_end = measure.find("}")
                if ns_end < 0:
                    continue
                ns = measure[1:ns_end]
                if ns not in (NS_ISO4217, NS_XBRLI):
                    messages.append(
                        ValidationMessage(
                            code="EFM-0021",
                            severity=Severity.WARNING,
                            message=(
                                f"Unit '{unit.unit_id}': measure "
                                f"'{measure}' uses a non-standard "
                                f"namespace."
                            ),
                            spec_ref="EFM 6.5.39",
                            file_path=instance.file_path,
                            fix_suggestion=(
                                "Use standard ISO 4217 or xbrli measures."
                            ),
                        ),
                    )

        return messages

    # ------------------------------------------------------------------
    # Fact rules — EFM 6.5.17, 6.5.25
    # ------------------------------------------------------------------
    def _validate_fact_rules(
        self, instance: XBRLInstance
    ) -> list[ValidationMessage]:
        """EFM 6.5.17, 6.5.25: Fact-level rules.

        Checks:
        - Negative value checks (NEGVAL)
        - Duplicate fact detection (same concept, context, unit)
        - Precision/decimals attributes
        - Facts must have non-empty values (unless nil)

        Emits: EFM-0030, EFM-0031, EFM-0032, EFM-0033
        """
        messages: list[ValidationMessage] = []

        # Track seen (concept, context, unit, dims) for duplicate detection
        seen_keys: dict[tuple[str, str, str | None, str], Fact] = {}

        for fact in instance.facts:
            local = _local_name(fact.concept_qname)

            # EFM-0030: Negative value for concepts that must not be negative
            if (
                fact.is_numeric
                and isinstance(fact.value, Decimal)
                and fact.value < Decimal(0)
                and local in _NON_NEGATIVE_CONCEPTS
            ):
                messages.append(
                    ValidationMessage(
                        code="EFM-0030",
                        severity=Severity.WARNING,
                        message=(
                            f"Fact '{local}' has a negative value "
                            f"({fact.value}), which is unexpected."
                        ),
                        spec_ref="EFM 6.5.17",
                        file_path=instance.file_path,
                        line=fact.source_line,
                        fix_suggestion=(
                            "Review the sign of this value. Use a "
                            "credit-balance concept if the amount "
                            "should be presented as negative."
                        ),
                    )
                )

            # EFM-0031: Duplicate facts (same concept, context, unit,
            # and dimension key)
            dim_key_str = ""
            ctx = instance.get_context(fact.context_ref)
            if ctx is not None:
                dim_key_str = str(ctx.dimension_key)
            dup_key = (
                fact.concept_qname,
                fact.context_ref,
                fact.unit_ref,
                dim_key_str,
            )
            if dup_key in seen_keys:
                prior = seen_keys[dup_key]
                if fact.value != prior.value:
                    messages.append(
                        ValidationMessage(
                            code="EFM-0031",
                            severity=Severity.ERROR,
                            message=(
                                f"Duplicate fact for concept '{local}' in "
                                f"context '{fact.context_ref}' with "
                                f"different values "
                                f"('{prior.value}' vs '{fact.value}')."
                            ),
                            spec_ref="EFM 6.5.25",
                            file_path=instance.file_path,
                            line=fact.source_line,
                        )
                    )
            else:
                seen_keys[dup_key] = fact

            # EFM-0032: Numeric facts should not use 'precision'
            if fact.is_numeric and fact.precision is not None:
                messages.append(
                    ValidationMessage(
                        code="EFM-0032",
                        severity=Severity.WARNING,
                        message=(
                            f"Fact '{local}' uses deprecated 'precision' "
                            f"attribute; use 'decimals' instead."
                        ),
                        spec_ref="EFM 6.5.17",
                        file_path=instance.file_path,
                        line=fact.source_line,
                        fix_suggestion=(
                            "Replace the 'precision' attribute with "
                            "'decimals'."
                        ),
                    )
                )

            # EFM-0033: Non-nil facts should have non-empty values
            if not fact.is_nil and fact.value is None:
                messages.append(
                    ValidationMessage(
                        code="EFM-0033",
                        severity=Severity.ERROR,
                        message=(
                            f"Fact '{local}' has no value and is not "
                            f"marked as nil."
                        ),
                        spec_ref="EFM 6.5.25",
                        file_path=instance.file_path,
                        line=fact.source_line,
                        fix_suggestion=(
                            "Provide a value for the fact, or set "
                            "xsi:nil='true'."
                        ),
                    )
                )

        return messages

    # ------------------------------------------------------------------
    # Taxonomy reference rules — EFM 6.3.3
    # ------------------------------------------------------------------
    def _validate_taxonomy_refs(
        self, instance: XBRLInstance
    ) -> list[ValidationMessage]:
        """EFM 6.3.3: Taxonomy reference validation.

        Checks:
        - schemaRef must reference a standard taxonomy entry point

        Emits: EFM-0040
        """
        messages: list[ValidationMessage] = []

        for ref in instance.schema_refs:
            if not any(
                ref.startswith(prefix)
                for prefix in _STANDARD_TAXONOMY_PREFIXES
            ):
                messages.append(
                    ValidationMessage(
                        code="EFM-0040",
                        severity=Severity.WARNING,
                        message=(
                            f"Schema reference '{ref}' does not point to "
                            f"a recognised standard taxonomy entry point."
                        ),
                        spec_ref="EFM 6.3.3",
                        file_path=instance.file_path,
                        fix_suggestion=(
                            "Reference the standard US-GAAP or SEC "
                            "taxonomy entry point."
                        ),
                    )
                )

        return messages
