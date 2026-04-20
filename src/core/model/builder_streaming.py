"""Streaming model builder.

Transforms :class:`StreamingParseResult` (from the SAX/iterparse
pipeline) into a store-backed :class:`XBRLInstance` suitable for
large files that exceed the memory budget.

The builder selects the appropriate value reader
(:class:`MMapReader` for SSD, :class:`ChunkedReader` for HDD)
and classifies :class:`FactReference` objects using the taxonomy.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from src.core.model.xbrl_model import (
    Context,
    DimensionMember,
    EntityIdentifier,
    Fact,
    Period,
    TaxonomyModel,
    Unit,
    UnitMeasure,
    XBRLInstance,
)
from src.core.parser.streaming.sax_handler import StreamingParseResult
from src.core.parser.xml_parser import RawContext, RawUnit
from src.core.types import InputFormat, PeriodType

logger = logging.getLogger(__name__)


def _parse_date_safe(value: Optional[str]) -> date | None:
    """Parse a date string, returning None on failure."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _parse_measure_str(qname_str: str) -> UnitMeasure:
    """Convert a measure QName string to :class:`UnitMeasure`."""
    if qname_str.startswith("{"):
        ns, local = qname_str[1:].split("}", 1)
        return UnitMeasure(namespace=ns, local_name=local)
    if ":" in qname_str:
        prefix, local = qname_str.split(":", 1)
        ns = ""
        if prefix == "iso4217":
            ns = "http://www.xbrl.org/2003/iso4217"
        elif prefix == "xbrli":
            ns = "http://www.xbrl.org/2003/instance"
        return UnitMeasure(namespace=ns, local_name=local)
    return UnitMeasure(namespace="", local_name=qname_str)


def _is_ssd(path: str) -> bool:
    """Heuristic check whether the file resides on an SSD.

    Falls back to ``True`` (prefer mmap) on platforms where
    detection is not available.
    """
    try:
        # Linux: check /sys/block/<dev>/queue/rotational
        real_path = os.path.realpath(path)
        st = os.stat(real_path)
        major = os.major(st.st_dev)
        minor = os.minor(st.st_dev)
        rotational_path = f"/sys/dev/block/{major}:{minor}/../queue/rotational"
        if os.path.exists(rotational_path):
            with open(rotational_path) as f:
                return f.read().strip() == "0"
    except (OSError, ValueError):
        pass
    return True  # Default: assume SSD


class StreamingModelBuilder:
    """Build :class:`XBRLInstance` from streaming parse results.

    Creates a store-backed instance that reads fact values on-demand
    from the source file using memory-mapped or chunked I/O.
    """

    def build(
        self,
        parse_result: StreamingParseResult,
        taxonomy: TaxonomyModel | None = None,
        source_file: str = "",
    ) -> XBRLInstance:
        """Create store-backed :class:`XBRLInstance`.

        Sets up the value reader (:class:`MMapReader` if SSD,
        :class:`ChunkedReader` if HDD).  Classifies
        :class:`FactReference` entries using the taxonomy.

        Args:
            parse_result: Result from the streaming SAX parser.
            taxonomy: Optional taxonomy for concept classification.
            source_file: Path to the source XBRL file.

        Returns:
            A store-backed :class:`XBRLInstance`.
        """
        # Build contexts
        contexts: dict[str, Context] = {}
        for cid, raw_ctx in parse_result.contexts.items():
            try:
                contexts[cid] = self._build_context(raw_ctx)
            except Exception as exc:
                logger.warning("Failed to build streaming context %s: %s", cid, exc)

        # Build units
        units: dict[str, Unit] = {}
        for uid, raw_unit in parse_result.units.items():
            try:
                units[uid] = self._build_unit(raw_unit)
            except Exception as exc:
                logger.warning("Failed to build streaming unit %s: %s", uid, exc)

        # Set up value reader
        value_reader = None
        if source_file and Path(source_file).is_file():
            try:
                if _is_ssd(source_file):
                    from src.core.parser.streaming.mmap_reader import MMapReader
                    value_reader = MMapReader(source_file)
                    logger.debug("Using MMapReader for %s", source_file)
                else:
                    from src.core.parser.streaming.chunked_reader import ChunkedReader
                    value_reader = ChunkedReader(source_file)
                    logger.debug("Using ChunkedReader for %s", source_file)
            except (OSError, ImportError) as exc:
                logger.warning("Failed to create value reader: %s", exc)

        # Classify fact references using taxonomy
        if taxonomy and parse_result.fact_store:
            self._classify_facts(parse_result.fact_store, taxonomy)

        schema_refs = [sr.href for sr in parse_result.schema_refs]

        instance = XBRLInstance(
            file_path=source_file,
            format_type=InputFormat.XBRL_XML,
            contexts=contexts,
            units=units,
            facts=[],
            taxonomy=taxonomy,
            schema_refs=schema_refs,
            namespaces=dict(parse_result.namespaces),
            fact_store=parse_result.fact_store,
            value_reader=value_reader,
            _mode="store",
        )

        logger.info(
            "Built streaming XBRLInstance: %d contexts, %d units, "
            "%d facts, spill=%s",
            len(contexts),
            len(units),
            parse_result.total_facts,
            parse_result.spill_occurred,
        )
        return instance

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_context(self, raw: RawContext) -> Context:
        """Build a Context from a RawContext."""
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
            instant=_parse_date_safe(raw.instant),
            start_date=_parse_date_safe(raw.start_date),
            end_date=_parse_date_safe(raw.end_date),
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
        """Build a Unit from a RawUnit."""
        return Unit(
            id=raw.id,
            measures=[_parse_measure_str(m) for m in raw.measures],
            divide_numerator=[_parse_measure_str(m) for m in raw.divide_numerator],
            divide_denominator=[_parse_measure_str(m) for m in raw.divide_denominator],
        )

    @staticmethod
    def _extract_dimensions(
        raw_dims: list[dict[str, str]],
    ) -> list[DimensionMember]:
        """Extract dimension members from raw segment/scenario dicts."""
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

    @staticmethod
    def _classify_facts(
        fact_store: object,
        taxonomy: TaxonomyModel,
    ) -> None:
        """Classify FactReferences using taxonomy concept definitions.

        Updates ``is_numeric``, ``period_type``, and ``balance_type``
        on each :class:`FactReference` in the store.

        Args:
            fact_store: The :class:`FactStore` from the streaming parser.
            taxonomy: Taxonomy model for concept lookup.
        """
        try:
            iterator = fact_store.iter_all()  # type: ignore[union-attr]
        except AttributeError:
            logger.debug("FactStore does not support iter_all; skipping classification")
            return

        classified = 0
        for ref in iterator:
            concept_def = taxonomy.concepts.get(ref.concept)
            if concept_def is not None:
                ref.is_numeric = concept_def.type_is_numeric
                ref.period_type = concept_def.period_type
                ref.balance_type = concept_def.balance_type
                classified += 1

        logger.debug("Classified %d fact references from taxonomy", classified)
