"""Model merger — combine multiple XBRL documents into a single model.

Used for multi-document filings (e.g., report packages with separate
taxonomy and instance documents, or iXBRL document sets).
"""

from __future__ import annotations

import structlog

from src.core.model.xbrl_model import (
    Context, Fact, Footnote, TaxonomyModel, Unit, XBRLInstance,
)
from src.core.types import ContextID, UnitID

logger = structlog.get_logger(__name__)


class ModelMerger:
    """Merge multiple XBRLInstance objects into a single unified model."""

    def __init__(self) -> None:
        self._log = logger.bind(component="model_merger")

    def merge(self, instances: list[XBRLInstance]) -> XBRLInstance:
        """Merge a list of XBRLInstance objects into one.

        Contexts and units are deduplicated by ID. Facts from all
        instances are combined. The taxonomy from the first instance
        with a non-None taxonomy is used.
        """
        if not instances:
            return XBRLInstance()
        if len(instances) == 1:
            return instances[0]

        self._log.info("merge_start", instance_count=len(instances))
        merged = XBRLInstance(
            file_path=instances[0].file_path,
            format_type=instances[0].format_type,
        )

        # Merge namespaces
        for inst in instances:
            merged.namespaces.update(inst.namespaces)

        # Merge schema refs (deduplicate by href)
        seen_hrefs: set[str] = set()
        for inst in instances:
            for sr in inst.schema_refs:
                if sr.href not in seen_hrefs:
                    merged.schema_refs.append(sr)
                    seen_hrefs.add(sr.href)

        # Merge contexts
        context_remap: dict[tuple[str, ContextID], ContextID] = {}
        for inst in instances:
            for ctx_id, ctx in inst.contexts.items():
                existing = self._find_equivalent_context(merged.contexts, ctx)
                if existing is not None:
                    context_remap[(inst.file_path, ctx_id)] = existing
                else:
                    if ctx_id in merged.contexts:
                        new_id = f"{ctx_id}_{inst.file_path}"
                        context_remap[(inst.file_path, ctx_id)] = new_id
                        merged.contexts[new_id] = Context(
                            id=new_id,
                            entity=ctx.entity,
                            period=ctx.period,
                            segment_dims=ctx.segment_dims,
                            scenario_dims=ctx.scenario_dims,
                        )
                    else:
                        merged.contexts[ctx_id] = ctx
                        context_remap[(inst.file_path, ctx_id)] = ctx_id

        # Merge units
        unit_remap: dict[tuple[str, UnitID], UnitID] = {}
        for inst in instances:
            for unit_id, unit in inst.units.items():
                existing = self._find_equivalent_unit(merged.units, unit)
                if existing is not None:
                    unit_remap[(inst.file_path, unit_id)] = existing
                else:
                    if unit_id in merged.units:
                        new_id = f"{unit_id}_{inst.file_path}"
                        unit_remap[(inst.file_path, unit_id)] = new_id
                        merged.units[new_id] = Unit(
                            id=new_id,
                            measures=unit.measures,
                            numerator_measures=unit.numerator_measures,
                            denominator_measures=unit.denominator_measures,
                        )
                    else:
                        merged.units[unit_id] = unit
                        unit_remap[(inst.file_path, unit_id)] = unit_id

        # Merge facts with remapped references
        for inst in instances:
            for fact in inst.facts:
                new_ctx = fact.context_ref
                if fact.context_ref and (inst.file_path, fact.context_ref) in context_remap:
                    new_ctx = context_remap[(inst.file_path, fact.context_ref)]
                new_unit = fact.unit_ref
                if fact.unit_ref and (inst.file_path, fact.unit_ref) in unit_remap:
                    new_unit = unit_remap[(inst.file_path, fact.unit_ref)]

                merged.facts.append(Fact(
                    id=fact.id,
                    concept_qname=fact.concept_qname,
                    context_ref=new_ctx,
                    unit_ref=new_unit,
                    raw_value=fact.raw_value,
                    numeric_value=fact.numeric_value,
                    is_nil=fact.is_nil,
                    is_numeric=fact.is_numeric,
                    is_tuple=fact.is_tuple,
                    decimals=fact.decimals,
                    precision=fact.precision,
                    language=fact.language,
                    source_line=fact.source_line,
                    source_file=fact.source_file or inst.file_path,
                    is_hidden=fact.is_hidden,
                    footnote_refs=fact.footnote_refs,
                ))

        # Merge footnotes
        for inst in instances:
            merged.footnotes.extend(inst.footnotes)

        # Use first non-None taxonomy
        for inst in instances:
            if inst.taxonomy is not None:
                merged.taxonomy = inst.taxonomy
                break

        self._log.info(
            "merge_complete",
            contexts=len(merged.contexts),
            units=len(merged.units),
            facts=len(merged.facts),
        )
        return merged

    def _find_equivalent_context(
        self, contexts: dict[ContextID, Context], ctx: Context
    ) -> ContextID | None:
        for cid, existing in contexts.items():
            if existing.is_dimensional_equivalent(ctx):
                return cid
        return None

    def _find_equivalent_unit(
        self, units: dict[UnitID, Unit], unit: Unit
    ) -> UnitID | None:
        for uid, existing in units.items():
            if existing.is_equal(unit):
                return uid
        return None
