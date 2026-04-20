"""Multi-document merger for XBRL instances.

Merges multiple :class:`XBRLInstance` objects (e.g. from a multi-document
inline XBRL filing) into a single unified instance with collision checks.

Error codes:
- ``MERGE-0001``: Entity identifier mismatch across documents.
- ``MERGE-0002``: Context ID collision with different definitions.
- ``MERGE-0003``: Unit ID collision with different definitions.
- ``MERGE-0004``: Duplicate fact ID across documents.
- ``MERGE-0005``: Cross-document continuation chain reference error.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.model.xbrl_model import (
    Context,
    Fact,
    Footnote,
    TaxonomyModel,
    Unit,
    ValidationMessage,
    XBRLInstance,
)
from src.core.types import ContextID, Severity, UnitID

logger = logging.getLogger(__name__)


class ModelMerger:
    """Merge multiple :class:`XBRLInstance` objects into one.

    Same entity required.  Context/unit ID collision checks are performed
    and reported as :class:`ValidationMessage` entries.
    """

    def merge(
        self, instances: list[XBRLInstance]
    ) -> tuple[XBRLInstance, list[ValidationMessage]]:
        """Merge multiple instances into a single :class:`XBRLInstance`.

        Args:
            instances: List of instances to merge.

        Returns:
            Tuple of (merged instance, list of validation messages).
            Messages include errors for entity mismatches, ID collisions,
            and continuation-chain problems.

        Raises:
            ValueError: If the instances list is empty.
        """
        if not instances:
            raise ValueError("Cannot merge an empty list of instances")

        if len(instances) == 1:
            return instances[0], []

        messages: list[ValidationMessage] = []

        # --- MERGE-0001: Entity identifier consistency ---
        entities = self._collect_entities(instances)
        if len(entities) > 1:
            messages.append(
                ValidationMessage(
                    code="MERGE-0001",
                    severity=Severity.ERROR,
                    message=(
                        f"Entity identifier mismatch across documents: "
                        f"{sorted(entities)}"
                    ),
                )
            )

        # --- Build merged collections ---
        merged_contexts: dict[ContextID, Context] = {}
        merged_units: dict[UnitID, Unit] = {}
        merged_facts: list[Fact] = []
        merged_footnotes: list[Footnote] = []
        merged_schema_refs: list[str] = []
        merged_namespaces: dict[str, str] = {}
        fact_ids_seen: set[str] = set()

        for idx, inst in enumerate(instances):
            source_label = inst.file_path or f"doc-{idx}"

            # --- Contexts ---
            for cid, ctx in inst.contexts.items():
                if cid in merged_contexts:
                    existing = merged_contexts[cid]
                    if not existing.is_dimensional_equivalent(ctx):
                        messages.append(
                            ValidationMessage(
                                code="MERGE-0002",
                                severity=Severity.ERROR,
                                message=(
                                    f"Context ID collision: '{cid}' has "
                                    f"different definitions in {source_label}"
                                ),
                                context_id=cid,
                                source_file=source_label,
                            )
                        )
                else:
                    merged_contexts[cid] = ctx

            # --- Units ---
            for uid, unit in inst.units.items():
                if uid in merged_units:
                    existing_unit = merged_units[uid]
                    if not self._units_equal(existing_unit, unit):
                        messages.append(
                            ValidationMessage(
                                code="MERGE-0003",
                                severity=Severity.ERROR,
                                message=(
                                    f"Unit ID collision: '{uid}' has "
                                    f"different definitions in {source_label}"
                                ),
                                source_file=source_label,
                            )
                        )
                else:
                    merged_units[uid] = unit

            # --- Facts ---
            for fact in inst.facts:
                # MERGE-0004: Fact ID uniqueness
                if fact.id:
                    if fact.id in fact_ids_seen:
                        messages.append(
                            ValidationMessage(
                                code="MERGE-0004",
                                severity=Severity.WARNING,
                                message=(
                                    f"Duplicate fact ID '{fact.id}' "
                                    f"found in {source_label}"
                                ),
                                fact_id=fact.id,
                                source_file=source_label,
                            )
                        )
                    else:
                        fact_ids_seen.add(fact.id)

                # Re-link context and unit
                updated_fact = Fact(
                    id=fact.id,
                    concept=fact.concept,
                    context_ref=fact.context_ref,
                    context=merged_contexts.get(fact.context_ref),
                    unit_ref=fact.unit_ref,
                    unit=merged_units.get(fact.unit_ref) if fact.unit_ref else None,
                    value=fact.value,
                    numeric_value=fact.numeric_value,
                    is_nil=fact.is_nil,
                    is_numeric=fact.is_numeric,
                    decimals=fact.decimals,
                    precision=fact.precision,
                    language=fact.language,
                    source_line=fact.source_line,
                    source_file=source_label,
                    is_hidden=fact.is_hidden,
                    footnote_refs=list(fact.footnote_refs),
                )
                merged_facts.append(updated_fact)

            # --- Footnotes ---
            merged_footnotes.extend(inst.footnotes)

            # --- Schema refs (de-duplicate) ---
            for sr in inst.schema_refs:
                if sr not in merged_schema_refs:
                    merged_schema_refs.append(sr)

            # --- Namespaces (first-wins) ---
            for prefix, uri in inst.namespaces.items():
                if prefix not in merged_namespaces:
                    merged_namespaces[prefix] = uri

        # --- MERGE-0005: Cross-doc continuation chains ---
        continuation_messages = self._check_continuation_chains(
            merged_facts, instances
        )
        messages.extend(continuation_messages)

        # --- Select taxonomy (first non-None) ---
        taxonomy: TaxonomyModel | None = None
        for inst in instances:
            if inst.taxonomy is not None:
                taxonomy = inst.taxonomy
                break

        merged = XBRLInstance(
            file_path=instances[0].file_path,
            format_type=instances[0].format_type,
            contexts=merged_contexts,
            units=merged_units,
            facts=merged_facts,
            footnotes=merged_footnotes,
            taxonomy=taxonomy,
            schema_refs=merged_schema_refs,
            namespaces=merged_namespaces,
        )
        merged.build_indexes()

        logger.info(
            "Merged %d instances: %d contexts, %d units, %d facts, %d messages",
            len(instances),
            len(merged_contexts),
            len(merged_units),
            len(merged_facts),
            len(messages),
        )
        return merged, messages

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_entities(instances: list[XBRLInstance]) -> set[tuple[str, str]]:
        """Collect unique entity identifiers across instances.

        Returns:
            Set of (scheme, identifier) tuples.
        """
        entities: set[tuple[str, str]] = set()
        for inst in instances:
            for ctx in inst.contexts.values():
                entities.add((ctx.entity.scheme, ctx.entity.identifier))
        return entities

    @staticmethod
    def _units_equal(a: Unit, b: Unit) -> bool:
        """Check structural equality of two units.

        Compares measures, numerator, and denominator lists.

        Args:
            a: First unit.
            b: Second unit.

        Returns:
            ``True`` if the units are structurally identical.
        """
        def _measures_key(measures: list[Any]) -> frozenset[tuple[str, str]]:
            return frozenset(
                (m.namespace, m.local_name) for m in measures
            )

        return (
            _measures_key(a.measures) == _measures_key(b.measures)
            and _measures_key(a.divide_numerator) == _measures_key(b.divide_numerator)
            and _measures_key(a.divide_denominator) == _measures_key(b.divide_denominator)
        )

    @staticmethod
    def _check_continuation_chains(
        facts: list[Fact], instances: list[XBRLInstance]
    ) -> list[ValidationMessage]:
        """Detect broken cross-document continuation chains.

        Args:
            facts: Merged fact list.
            instances: Original instance list (for footnote checking).

        Returns:
            List of validation messages for broken chains.
        """
        messages: list[ValidationMessage] = []
        # Collect all footnote IDs across documents
        all_footnote_ids: set[str] = set()
        for inst in instances:
            for fn in inst.footnotes:
                if fn.id:
                    all_footnote_ids.add(fn.id)

        # Check that all footnote_refs on facts resolve
        for fact in facts:
            for ref in fact.footnote_refs:
                if ref and ref not in all_footnote_ids:
                    messages.append(
                        ValidationMessage(
                            code="MERGE-0005",
                            severity=Severity.WARNING,
                            message=(
                                f"Footnote reference '{ref}' on fact "
                                f"'{fact.id or fact.concept}' not found "
                                f"in any merged document"
                            ),
                            fact_id=fact.id,
                            source_file=fact.source_file,
                        )
                    )
        return messages
