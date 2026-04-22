"""XBRL 2.1 instance document validation — §4.

Validates the structural integrity of an XBRL instance document,
including contexts (§4.7), units (§4.8), facts (§4.6), and schema
references (§4.2).

References:
    - XBRL 2.1 §4 (Instance Documents)
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from src.core.model.context import Context, Period
from src.core.model.fact import Fact
from src.core.model.instance import ValidationMessage, XBRLInstance
from src.core.model.unit import Unit
from src.core.types import FactType, PeriodType, Severity


class InstanceValidator:
    """Validates XBRL 2.1 instance documents.

    Spec: XBRL 2.1 §4 (Instance Documents)
    """

    def validate(self, instance: XBRLInstance) -> list[ValidationMessage]:
        """Run all XBRL 2.1 instance validation rules.

        Spec: XBRL 2.1 §4 | Emits: XBRL21-0001 through XBRL21-0030

        Args:
            instance: The parsed XBRL instance to validate.

        Returns:
            List of validation messages (errors, warnings, info).
        """
        messages: list[ValidationMessage] = []
        messages.extend(self._validate_schema_refs(instance))
        messages.extend(self._validate_contexts(instance))
        messages.extend(self._validate_units(instance))
        messages.extend(self._validate_facts(instance))
        return messages

    # ------------------------------------------------------------------
    # Context validation
    # ------------------------------------------------------------------

    def _validate_contexts(
        self, instance: XBRLInstance
    ) -> list[ValidationMessage]:
        """XBRL 2.1 §4.7: Context validation.

        Checks performed:
        - Each context must have a non-empty entity scheme and identifier.
        - Period type consistency: instant periods must have ``instant``
          set; duration periods must have ``start_date`` and ``end_date``
          set with start before end; forever periods must have no dates.
        - Segment/scenario content: explicit dimension members must be
          non-empty QNames.
        - No duplicate contexts with identical structural content.

        Spec: XBRL 2.1 §4.7 | Emits: XBRL21-0001, XBRL21-0002, XBRL21-0003

        Args:
            instance: The parsed XBRL instance.

        Returns:
            Validation messages for context-related issues.
        """
        messages: list[ValidationMessage] = []

        # Track structural signatures for duplicate detection
        seen_signatures: dict[
            tuple[str, str, PeriodType, str | None, str | None, str | None, tuple[tuple[str, str], ...]], str
        ] = {}

        for ctx_id, ctx in instance.contexts.items():
            messages.extend(self._validate_entity(ctx, instance.file_path))
            messages.extend(self._validate_period(ctx, instance.file_path))
            messages.extend(
                self._validate_dimension_content(ctx, instance.file_path)
            )

            # Build a structural signature for duplicate detection
            sig = (
                ctx.entity.scheme,
                ctx.entity.identifier,
                ctx.period.period_type,
                ctx.period.instant.isoformat() if ctx.period.instant else None,
                ctx.period.start_date.isoformat()
                if ctx.period.start_date
                else None,
                ctx.period.end_date.isoformat()
                if ctx.period.end_date
                else None,
                ctx.dimension_key,
            )
            if sig in seen_signatures:
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0003",
                        severity=Severity.WARNING,
                        message=(
                            f"Context '{ctx_id}' is structurally identical "
                            f"to context '{seen_signatures[sig]}'. "
                            f"Duplicate contexts are redundant per §4.7."
                        ),
                        spec_ref="XBRL 2.1 §4.7",
                        file_path=instance.file_path,
                    )
                )
            else:
                seen_signatures[sig] = ctx_id

        return messages

    def _validate_entity(
        self, ctx: Context, file_path: str
    ) -> list[ValidationMessage]:
        """Validate the entity element of a context.

        Spec: XBRL 2.1 §4.7.1 | Emits: XBRL21-0001

        Args:
            ctx: The context to validate.
            file_path: Source file path for error reporting.

        Returns:
            Validation messages for entity issues.
        """
        messages: list[ValidationMessage] = []

        if not ctx.entity.scheme or not ctx.entity.scheme.strip():
            messages.append(
                ValidationMessage(
                    code="XBRL21-0001",
                    severity=Severity.ERROR,
                    message=(
                        f"Context '{ctx.context_id}': entity identifier "
                        f"scheme must not be empty."
                    ),
                    spec_ref="XBRL 2.1 §4.7.1",
                    file_path=file_path,
                    fix_suggestion=(
                        "Provide a valid URI for the entity identifier scheme, "
                        "e.g. 'http://www.sec.gov/CIK'."
                    ),
                )
            )

        if not ctx.entity.identifier or not ctx.entity.identifier.strip():
            messages.append(
                ValidationMessage(
                    code="XBRL21-0001",
                    severity=Severity.ERROR,
                    message=(
                        f"Context '{ctx.context_id}': entity identifier "
                        f"value must not be empty."
                    ),
                    spec_ref="XBRL 2.1 §4.7.1",
                    file_path=file_path,
                    fix_suggestion="Provide a non-empty entity identifier value.",
                )
            )

        return messages

    def _validate_period(
        self, ctx: Context, file_path: str
    ) -> list[ValidationMessage]:
        """Validate the period element of a context.

        Spec: XBRL 2.1 §4.7.2 | Emits: XBRL21-0002

        Args:
            ctx: The context to validate.
            file_path: Source file path for error reporting.

        Returns:
            Validation messages for period issues.
        """
        messages: list[ValidationMessage] = []
        period: Period = ctx.period

        if period.period_type == PeriodType.INSTANT:
            if period.instant is None:
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0002",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': instant period "
                            f"must have an instant date."
                        ),
                        spec_ref="XBRL 2.1 §4.7.2",
                        file_path=file_path,
                        fix_suggestion="Set the <instant> date element.",
                    )
                )
        elif period.period_type == PeriodType.DURATION:
            if period.start_date is None:
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0002",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': duration period "
                            f"must have a start date."
                        ),
                        spec_ref="XBRL 2.1 §4.7.2",
                        file_path=file_path,
                        fix_suggestion="Set the <startDate> element.",
                    )
                )
            if period.end_date is None:
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0002",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': duration period "
                            f"must have an end date."
                        ),
                        spec_ref="XBRL 2.1 §4.7.2",
                        file_path=file_path,
                        fix_suggestion="Set the <endDate> element.",
                    )
                )
            if (
                period.start_date is not None
                and period.end_date is not None
                and period.start_date > period.end_date
            ):
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0002",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': duration start date "
                            f"({period.start_date.isoformat()}) must not be "
                            f"after end date ({period.end_date.isoformat()})."
                        ),
                        spec_ref="XBRL 2.1 §4.7.2",
                        file_path=file_path,
                        fix_suggestion=(
                            "Correct the period so startDate <= endDate."
                        ),
                    )
                )
        elif period.period_type == PeriodType.FOREVER:
            if (
                period.instant is not None
                or period.start_date is not None
                or period.end_date is not None
            ):
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0002",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': forever period "
                            f"must not have any date fields set."
                        ),
                        spec_ref="XBRL 2.1 §4.7.2",
                        file_path=file_path,
                        fix_suggestion=(
                            "Remove date elements from the forever period."
                        ),
                    )
                )

        return messages

    def _validate_dimension_content(
        self, ctx: Context, file_path: str
    ) -> list[ValidationMessage]:
        """Validate dimensional content in segment/scenario.

        Spec: XBRL Dimensions 1.0 §4 | Emits: XBRL21-0003

        Args:
            ctx: The context to validate.
            file_path: Source file path for error reporting.

        Returns:
            Validation messages for dimension content issues.
        """
        messages: list[ValidationMessage] = []

        for ed in ctx.explicit_dimensions:
            if not ed.dimension or not ed.dimension.strip():
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0003",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': explicit dimension "
                            f"has an empty dimension QName."
                        ),
                        spec_ref="XBRL Dimensions 1.0 §4",
                        file_path=file_path,
                    )
                )
            if not ed.member or not ed.member.strip():
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0003",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': explicit dimension "
                            f"'{ed.dimension}' has an empty member QName."
                        ),
                        spec_ref="XBRL Dimensions 1.0 §4",
                        file_path=file_path,
                    )
                )

        for td in ctx.typed_dimensions:
            if not td.dimension or not td.dimension.strip():
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0003",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': typed dimension "
                            f"has an empty dimension QName."
                        ),
                        spec_ref="XBRL Dimensions 1.0 §4",
                        file_path=file_path,
                    )
                )

        # Detect duplicate dimension bindings within a single context
        dim_names: list[str] = [
            ed.dimension for ed in ctx.explicit_dimensions
        ]
        dim_names.extend(td.dimension for td in ctx.typed_dimensions)
        dim_counts: Counter[str] = Counter(dim_names)
        for dim_qname, count in dim_counts.items():
            if count > 1:
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0003",
                        severity=Severity.ERROR,
                        message=(
                            f"Context '{ctx.context_id}': dimension "
                            f"'{dim_qname}' appears {count} times. "
                            f"Each dimension may only appear once per context."
                        ),
                        spec_ref="XBRL Dimensions 1.0 §4",
                        file_path=file_path,
                    )
                )

        return messages

    # ------------------------------------------------------------------
    # Unit validation
    # ------------------------------------------------------------------

    def _validate_units(
        self, instance: XBRLInstance
    ) -> list[ValidationMessage]:
        """XBRL 2.1 §4.8: Unit validation.

        Checks performed:
        - Numeric facts must have unit references that resolve.
        - Unit measures must be valid (non-empty) QNames.
        - No duplicate units with identical measure sets.

        Spec: XBRL 2.1 §4.8 | Emits: XBRL21-0010, XBRL21-0011

        Args:
            instance: The parsed XBRL instance.

        Returns:
            Validation messages for unit-related issues.
        """
        messages: list[ValidationMessage] = []

        # Validate each unit's measures
        for unit_id, unit in instance.units.items():
            messages.extend(
                self._validate_unit_measures(unit, instance.file_path)
            )

        # Check for duplicate units (identical measure content)
        seen_measures: dict[tuple[tuple[str, ...], tuple[str, ...]], str] = {}
        for unit_id, unit in instance.units.items():
            # Canonical form: sorted numerators and sorted denominators
            sig = (
                tuple(sorted(unit.numerators)),
                tuple(sorted(unit.denominators)),
            )
            if sig in seen_measures:
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0011",
                        severity=Severity.WARNING,
                        message=(
                            f"Unit '{unit_id}' has identical measures to "
                            f"unit '{seen_measures[sig]}'. "
                            f"Duplicate units are redundant."
                        ),
                        spec_ref="XBRL 2.1 §4.8",
                        file_path=instance.file_path,
                    )
                )
            else:
                seen_measures[sig] = unit_id

        return messages

    def _validate_unit_measures(
        self, unit: Unit, file_path: str
    ) -> list[ValidationMessage]:
        """Validate individual unit measures are valid QNames.

        Spec: XBRL 2.1 §4.8 | Emits: XBRL21-0010

        Args:
            unit: The unit to validate.
            file_path: Source file path for error reporting.

        Returns:
            Validation messages for measure issues.
        """
        messages: list[ValidationMessage] = []

        if not unit.numerators:
            messages.append(
                ValidationMessage(
                    code="XBRL21-0010",
                    severity=Severity.ERROR,
                    message=(
                        f"Unit '{unit.unit_id}': must have at least one "
                        f"numerator measure."
                    ),
                    spec_ref="XBRL 2.1 §4.8",
                    file_path=file_path,
                    fix_suggestion="Add at least one <measure> element.",
                )
            )

        for measure in unit.numerators:
            if not measure or not measure.strip():
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0010",
                        severity=Severity.ERROR,
                        message=(
                            f"Unit '{unit.unit_id}': numerator measure "
                            f"must be a non-empty QName."
                        ),
                        spec_ref="XBRL 2.1 §4.8",
                        file_path=file_path,
                    )
                )

        for measure in unit.denominators:
            if not measure or not measure.strip():
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0010",
                        severity=Severity.ERROR,
                        message=(
                            f"Unit '{unit.unit_id}': denominator measure "
                            f"must be a non-empty QName."
                        ),
                        spec_ref="XBRL 2.1 §4.8",
                        file_path=file_path,
                    )
                )

        return messages

    # ------------------------------------------------------------------
    # Fact validation
    # ------------------------------------------------------------------

    def _validate_facts(
        self, instance: XBRLInstance
    ) -> list[ValidationMessage]:
        """XBRL 2.1 §4.6: Fact validation.

        Checks performed:
        - Facts must reference existing contexts (XBRL21-0020).
        - Numeric facts must reference existing units (XBRL21-0021).
        - Nil facts must not have non-None values (XBRL21-0022).
        - Numeric facts must not have both decimals and precision (XBRL21-0023).
        - Numeric facts must have either decimals or precision (XBRL21-0024).
        - Numeric fact values must be Decimal, not float (XBRL21-0025).
        - Non-numeric facts must not have unit references (XBRL21-0026).
        - Fact IDs should be unique (XBRL21-0027).
        - Context ref must not be empty (XBRL21-0028).
        - Nil facts must not have decimals/precision (XBRL21-0029).

        Spec: XBRL 2.1 §4.6 | Emits: XBRL21-0020 through XBRL21-0029

        Args:
            instance: The parsed XBRL instance.

        Returns:
            Validation messages for fact-related issues.
        """
        messages: list[ValidationMessage] = []
        seen_ids: dict[str, int] = {}

        for fact in instance.facts:
            # XBRL21-0027: Duplicate fact IDs
            if fact.fact_id in seen_ids:
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0027",
                        severity=Severity.ERROR,
                        message=(
                            f"Fact ID '{fact.fact_id}' is not unique; "
                            f"first seen at line {seen_ids[fact.fact_id]}."
                        ),
                        spec_ref="XBRL 2.1 §4.6",
                        file_path=fact.source_file,
                        line=fact.source_line,
                    )
                )
            else:
                seen_ids[fact.fact_id] = fact.source_line or 0

            # XBRL21-0028: Empty context ref
            if not fact.context_ref or not fact.context_ref.strip():
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0028",
                        severity=Severity.ERROR,
                        message=(
                            f"Fact '{fact.fact_id}': contextRef must not "
                            f"be empty."
                        ),
                        spec_ref="XBRL 2.1 §4.6",
                        file_path=fact.source_file,
                        line=fact.source_line,
                        fix_suggestion=(
                            "Set the contextRef attribute to a valid context ID."
                        ),
                    )
                )
            else:
                # XBRL21-0020: Context reference must exist
                if fact.context_ref not in instance.contexts:
                    messages.append(
                        ValidationMessage(
                            code="XBRL21-0020",
                            severity=Severity.ERROR,
                            message=(
                                f"Fact '{fact.fact_id}' references context "
                                f"'{fact.context_ref}' which does not exist."
                            ),
                            spec_ref="XBRL 2.1 §4.6",
                            file_path=fact.source_file,
                            line=fact.source_line,
                            fix_suggestion=(
                                "Add the missing context or correct the "
                                "contextRef attribute."
                            ),
                        )
                    )

            if fact.is_numeric and fact.fact_type != FactType.NIL:
                # XBRL21-0021: Numeric facts need a unit
                if fact.unit_ref is None:
                    messages.append(
                        ValidationMessage(
                            code="XBRL21-0021",
                            severity=Severity.ERROR,
                            message=(
                                f"Numeric fact '{fact.fact_id}' "
                                f"(concept: {fact.concept_qname}) "
                                f"must have a unitRef."
                            ),
                            spec_ref="XBRL 2.1 §4.6.3",
                            file_path=fact.source_file,
                            line=fact.source_line,
                            fix_suggestion="Add a unitRef attribute.",
                        )
                    )
                elif fact.unit_ref not in instance.units:
                    messages.append(
                        ValidationMessage(
                            code="XBRL21-0021",
                            severity=Severity.ERROR,
                            message=(
                                f"Numeric fact '{fact.fact_id}' references "
                                f"unit '{fact.unit_ref}' which does not exist."
                            ),
                            spec_ref="XBRL 2.1 §4.6.3",
                            file_path=fact.source_file,
                            line=fact.source_line,
                            fix_suggestion=(
                                "Add the missing unit or correct the "
                                "unitRef attribute."
                            ),
                        )
                    )

                # XBRL21-0023: Cannot have both decimals and precision
                if (
                    fact.decimals is not None
                    and fact.precision is not None
                ):
                    messages.append(
                        ValidationMessage(
                            code="XBRL21-0023",
                            severity=Severity.ERROR,
                            message=(
                                f"Fact '{fact.fact_id}': numeric fact must "
                                f"not specify both decimals and precision."
                            ),
                            spec_ref="XBRL 2.1 §4.6.6",
                            file_path=fact.source_file,
                            line=fact.source_line,
                            fix_suggestion=(
                                "Remove either the decimals or precision "
                                "attribute. The decimals attribute is preferred."
                            ),
                        )
                    )

                # XBRL21-0024: Must have decimals or precision (unless nil)
                if (
                    fact.decimals is None
                    and fact.precision is None
                    and not fact.is_nil
                ):
                    messages.append(
                        ValidationMessage(
                            code="XBRL21-0024",
                            severity=Severity.ERROR,
                            message=(
                                f"Fact '{fact.fact_id}': non-nil numeric fact "
                                f"must specify either decimals or precision."
                            ),
                            spec_ref="XBRL 2.1 §4.6.6",
                            file_path=fact.source_file,
                            line=fact.source_line,
                            fix_suggestion="Add a decimals attribute.",
                        )
                    )

                # XBRL21-0025: Value must be Decimal, not float
                if isinstance(fact.value, float):
                    messages.append(
                        ValidationMessage(
                            code="XBRL21-0025",
                            severity=Severity.ERROR,
                            message=(
                                f"Fact '{fact.fact_id}': numeric value is a "
                                f"float ({fact.value}). XBRL requires Decimal "
                                f"representation to preserve precision."
                            ),
                            spec_ref="XBRL 2.1 §4.6.6",
                            file_path=fact.source_file,
                            line=fact.source_line,
                            fix_suggestion=(
                                "Use decimal.Decimal instead of float."
                            ),
                        )
                    )

            # XBRL21-0022: Nil facts must not have a value
            if fact.is_nil and fact.value is not None:
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0022",
                        severity=Severity.ERROR,
                        message=(
                            f"Fact '{fact.fact_id}': nil fact must not "
                            f"have a value (found: {fact.value!r})."
                        ),
                        spec_ref="XBRL 2.1 §4.6",
                        file_path=fact.source_file,
                        line=fact.source_line,
                        fix_suggestion=(
                            "Remove the element content or unset xsi:nil."
                        ),
                    )
                )

            # XBRL21-0026: Non-numeric facts must not have unitRef
            if (
                not fact.is_numeric
                and fact.fact_type != FactType.NIL
                and fact.unit_ref is not None
            ):
                messages.append(
                    ValidationMessage(
                        code="XBRL21-0026",
                        severity=Severity.ERROR,
                        message=(
                            f"Fact '{fact.fact_id}': non-numeric fact must "
                            f"not have a unitRef (found: '{fact.unit_ref}')."
                        ),
                        spec_ref="XBRL 2.1 §4.6",
                        file_path=fact.source_file,
                        line=fact.source_line,
                        fix_suggestion="Remove the unitRef attribute.",
                    )
                )

            # XBRL21-0029: Nil facts must not have decimals or precision
            if fact.is_nil:
                if fact.decimals is not None:
                    messages.append(
                        ValidationMessage(
                            code="XBRL21-0029",
                            severity=Severity.ERROR,
                            message=(
                                f"Fact '{fact.fact_id}': nil fact must not "
                                f"have a decimals attribute."
                            ),
                            spec_ref="XBRL 2.1 §4.6.6",
                            file_path=fact.source_file,
                            line=fact.source_line,
                            fix_suggestion="Remove the decimals attribute.",
                        )
                    )
                if fact.precision is not None:
                    messages.append(
                        ValidationMessage(
                            code="XBRL21-0029",
                            severity=Severity.ERROR,
                            message=(
                                f"Fact '{fact.fact_id}': nil fact must not "
                                f"have a precision attribute."
                            ),
                            spec_ref="XBRL 2.1 §4.6.6",
                            file_path=fact.source_file,
                            line=fact.source_line,
                            fix_suggestion="Remove the precision attribute.",
                        )
                    )

        return messages

    # ------------------------------------------------------------------
    # Schema-ref validation
    # ------------------------------------------------------------------

    def _validate_schema_refs(
        self, instance: XBRLInstance
    ) -> list[ValidationMessage]:
        """XBRL 2.1 §4.2: schemaRef validation.

        At least one ``schemaRef`` is required in every XBRL instance.

        Spec: XBRL 2.1 §4.2 | Emits: XBRL21-0030

        Args:
            instance: The parsed XBRL instance.

        Returns:
            Validation messages for schemaRef issues.
        """
        messages: list[ValidationMessage] = []

        if not instance.schema_refs:
            messages.append(
                ValidationMessage(
                    code="XBRL21-0030",
                    severity=Severity.ERROR,
                    message=(
                        "Instance document must contain at least one "
                        "schemaRef element linking to a taxonomy schema."
                    ),
                    spec_ref="XBRL 2.1 §4.2",
                    file_path=instance.file_path,
                    fix_suggestion=(
                        "Add a <link:schemaRef> element pointing to the "
                        "entry-point taxonomy schema."
                    ),
                )
            )
        else:
            for href in instance.schema_refs:
                if not href or not href.strip():
                    messages.append(
                        ValidationMessage(
                            code="XBRL21-0030",
                            severity=Severity.ERROR,
                            message=(
                                "schemaRef href must not be empty."
                            ),
                            spec_ref="XBRL 2.1 §4.2",
                            file_path=instance.file_path,
                            fix_suggestion=(
                                "Provide a valid URL in the xlink:href "
                                "attribute of the schemaRef."
                            ),
                        )
                    )

        return messages
