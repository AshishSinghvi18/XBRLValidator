"""XBRL-JSON parser (OIM format).

Parses xBRL-JSON documents per the OIM specification into the
canonical XBRLInstance model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from src.core.exceptions import JSONParseError
from src.core.model.builder_oim import OIMFact, OIMModelBuilder
from src.core.model.xbrl_model import TaxonomyModel, XBRLInstance
from src.core.types import InputFormat

logger = structlog.get_logger(__name__)


class JSONParser:
    """Parse xBRL-JSON documents into XBRLInstance."""

    def __init__(self) -> None:
        self._log = logger.bind(component="json_parser")
        self._builder = OIMModelBuilder()

    def parse(
        self,
        file_path: str | Path,
        taxonomy: TaxonomyModel | None = None,
    ) -> XBRLInstance:
        """Parse an xBRL-JSON file.

        Args:
            file_path: Path to the JSON file.
            taxonomy: Optional resolved taxonomy.

        Returns:
            XBRLInstance with the parsed data.

        Raises:
            JSONParseError: If the document is malformed.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        self._log.info("json_parse_start", path=str(path))

        try:
            import orjson
            raw = path.read_bytes()
            data = orjson.loads(raw)
        except Exception as exc:
            raise JSONParseError(
                message=f"Failed to parse JSON: {exc}",
                code="PARSE-0060",
                file_path=str(path),
            ) from exc

        if not isinstance(data, dict):
            raise JSONParseError(
                message="xBRL-JSON root must be an object",
                code="PARSE-0061",
                file_path=str(path),
            )

        prefixes = self._extract_prefixes(data)
        oim_facts = self._extract_facts(data, str(path))

        instance = self._builder.build_from_facts(
            oim_facts,
            source_file=str(path),
            format_type=InputFormat.XBRL_JSON,
            taxonomy=taxonomy,
            prefixes=prefixes,
        )

        self._log.info("json_parse_complete", facts=len(instance.facts))
        return instance

    def _extract_prefixes(self, data: dict[str, Any]) -> dict[str, str]:
        """Extract namespace prefix mappings from documentInfo."""
        doc_info = data.get("documentInfo", {})
        if not isinstance(doc_info, dict):
            return {}
        ns_map = doc_info.get("namespaces", {})
        return dict(ns_map) if isinstance(ns_map, dict) else {}

    def _extract_facts(
        self, data: dict[str, Any], source_file: str
    ) -> list[OIMFact]:
        """Extract facts from the JSON structure."""
        facts_obj = data.get("facts", {})
        if not isinstance(facts_obj, dict):
            return []

        oim_facts: list[OIMFact] = []
        for fact_id, fact_data in facts_obj.items():
            if not isinstance(fact_data, dict):
                continue
            oim_fact = self._parse_fact(fact_id, fact_data)
            if oim_fact is not None:
                oim_facts.append(oim_fact)

        return oim_facts

    def _parse_fact(
        self, fact_id: str, data: dict[str, Any]
    ) -> OIMFact | None:
        """Parse a single fact from JSON."""
        concept = data.get("value", {})
        if isinstance(concept, dict):
            return None

        dims = data.get("dimensions", {})
        if not isinstance(dims, dict):
            dims = {}

        concept_name = dims.pop("concept", "")
        entity = dims.pop("entity", "")
        period = dims.pop("period", "")
        unit = dims.pop("unit", "")
        language = dims.pop("language", None)

        period_instant = ""
        period_start = ""
        period_end = ""
        if isinstance(period, str):
            if "/" in period:
                parts = period.split("/", 1)
                period_start = parts[0]
                period_end = parts[1]
            else:
                period_instant = period

        value = data.get("value")
        decimals_raw = data.get("decimals")
        decimals: int | str | None = None
        if decimals_raw is not None:
            if isinstance(decimals_raw, str) and decimals_raw.upper() == "INF":
                decimals = "INF"
            elif isinstance(decimals_raw, int):
                decimals = decimals_raw

        return OIMFact(
            id=fact_id,
            concept=concept_name,
            entity=entity,
            period_instant=period_instant,
            period_start=period_start,
            period_end=period_end,
            unit=unit,
            value=value,
            decimals=decimals,
            dimensions=dict(dims),
            language=language,
            is_nil=value is None,
        )
