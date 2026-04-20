"""Parser for xBRL-JSON format documents.

Parses xBRL-JSON documents conforming to the OIM (Open Information Model)
JSON representation into a ``RawXBRLDocument``.

The xBRL-JSON format consists of:
- ``documentInfo``: metadata including documentType, namespaces, taxonomy
- ``facts``: a flat dictionary of factId → fact objects

Spec references:
- xBRL-JSON 1.0 §2 (document structure)
- xBRL-JSON 1.0 §3 (documentInfo)
- xBRL-JSON 1.0 §4 (facts)
- OIM 1.0 (Open Information Model)
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import orjson

from src.core.exceptions import ParseError
from src.core.parser.xml_parser import (
    RawContext,
    RawFact,
    RawUnit,
    RawXBRLDocument,
    SchemaRef,
)

logger = logging.getLogger(__name__)

# xBRL-JSON document type URIs
_JSON_DOC_TYPES = frozenset({
    "https://xbrl.org/2021/xbrl-json",
    "https://xbrl.org/CR/2021-02-03/xbrl-json",
    "http://www.xbrl.org/WGWD/YYYY-MM-DD/xbrl-json",
})

# OIM dimension prefixes
_CONCEPT_DIM = "xbrl:concept"
_ENTITY_DIM = "xbrl:entity"
_PERIOD_DIM = "xbrl:period"
_UNIT_DIM = "xbrl:unit"
_LANGUAGE_DIM = "xbrl:language"
_NOTE_ID_DIM = "xbrl:noteId"


class JSONParser:
    """Parser for xBRL-JSON format documents.

    Uses ``orjson`` for fast JSON parsing. Converts the xBRL-JSON
    structure into a ``RawXBRLDocument`` for downstream validation.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, file_path: str) -> RawXBRLDocument:
        """Parse an xBRL-JSON file into a ``RawXBRLDocument``.

        Parameters
        ----------
        file_path:
            Path to the xBRL-JSON file.

        Returns
        -------
        RawXBRLDocument

        Raises
        ------
        ParseError
            On JSON syntax errors or missing required structure.
        """
        doc = RawXBRLDocument(file_path=file_path)

        try:
            with open(file_path, "rb") as fh:
                data = orjson.loads(fh.read())
        except orjson.JSONDecodeError as exc:
            raise ParseError(
                f"JSON syntax error: {exc}",
                file_path=file_path,
                line=0,
                column=0,
            ) from exc
        except OSError as exc:
            raise ParseError(
                f"Cannot read file: {exc}",
                file_path=file_path,
                line=0,
                column=0,
            ) from exc

        if not isinstance(data, dict):
            raise ParseError(
                "xBRL-JSON root must be a JSON object",
                file_path=file_path,
                line=0,
                column=0,
            )

        self._extract_document_info(data, doc)
        self._extract_facts(data, doc)

        return doc

    def parse_bytes(self, data: bytes, source_name: str = "<bytes>") -> RawXBRLDocument:
        """Parse xBRL-JSON from in-memory bytes.

        Parameters
        ----------
        data:
            Raw JSON bytes.
        source_name:
            Descriptive label for error messages.

        Returns
        -------
        RawXBRLDocument
        """
        doc = RawXBRLDocument(file_path=source_name)

        try:
            parsed = orjson.loads(data)
        except orjson.JSONDecodeError as exc:
            raise ParseError(
                f"JSON syntax error: {exc}",
                file_path=source_name,
                line=0,
                column=0,
            ) from exc

        if not isinstance(parsed, dict):
            raise ParseError(
                "xBRL-JSON root must be a JSON object",
                file_path=source_name,
                line=0,
                column=0,
            )

        self._extract_document_info(parsed, doc)
        self._extract_facts(parsed, doc)

        return doc

    # ------------------------------------------------------------------
    # Internal extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_document_info(
        data: dict[str, Any], doc: RawXBRLDocument
    ) -> None:
        """Extract documentInfo section.

        Expected structure:
        {
            "documentInfo": {
                "documentType": "https://xbrl.org/2021/xbrl-json",
                "namespaces": {"prefix": "uri", ...},
                "taxonomy": ["schema_url_1", ...],
                "linkTypes": {...},
                "features": {...}
            }
        }
        """
        doc_info = data.get("documentInfo", {})
        if not isinstance(doc_info, dict):
            doc.parse_errors.append(
                "Missing or invalid 'documentInfo' section"
            )
            return

        # Document type validation
        doc_type = doc_info.get("documentType", "")
        if doc_type and doc_type not in _JSON_DOC_TYPES:
            doc.parse_errors.append(
                f"Unrecognised documentType: {doc_type}"
            )

        # Namespaces
        namespaces = doc_info.get("namespaces", {})
        if isinstance(namespaces, dict):
            doc.namespaces = {
                str(k): str(v) for k, v in namespaces.items()
            }

        # Taxonomy (schema references)
        taxonomy = doc_info.get("taxonomy", [])
        if isinstance(taxonomy, list):
            for href in taxonomy:
                if isinstance(href, str):
                    doc.schema_refs.append(SchemaRef(href=href))

    def _extract_facts(
        self, data: dict[str, Any], doc: RawXBRLDocument
    ) -> None:
        """Extract facts from the xBRL-JSON facts section.

        Expected structure:
        {
            "facts": {
                "factId1": {
                    "value": "...",
                    "decimals": ...,
                    "dimensions": {
                        "xbrl:concept": "prefix:ConceptName",
                        "xbrl:entity": "scheme:id",
                        "xbrl:period": "2024-01-01T00:00:00/2024-12-31T00:00:00",
                        "xbrl:unit": "iso4217:USD",
                        ...
                    }
                },
                ...
            }
        }
        """
        facts = data.get("facts", {})
        if not isinstance(facts, dict):
            doc.parse_errors.append("Missing or invalid 'facts' section")
            return

        # Track unique contexts and units for synthesis
        context_counter = 0
        unit_counter = 0
        context_cache: dict[str, str] = {}
        unit_cache: dict[str, str] = {}

        for fact_id, fact_data in facts.items():
            if not isinstance(fact_data, dict):
                doc.parse_errors.append(
                    f"Fact '{fact_id}' is not a JSON object"
                )
                continue

            try:
                dimensions = fact_data.get("dimensions", {})
                if not isinstance(dimensions, dict):
                    doc.parse_errors.append(
                        f"Fact '{fact_id}' has invalid dimensions"
                    )
                    continue

                # Extract concept
                concept = dimensions.get(_CONCEPT_DIM, "")
                concept_resolved = self._resolve_json_qname(concept, doc.namespaces)

                # Extract and synthesise context
                context_key = self._build_context_key(dimensions)
                if context_key in context_cache:
                    context_ref = context_cache[context_key]
                else:
                    context_counter += 1
                    context_ref = f"_ctx_{context_counter}"
                    ctx = self._synthesize_context(
                        context_ref, dimensions
                    )
                    doc.contexts[context_ref] = ctx
                    context_cache[context_key] = context_ref

                # Extract and synthesise unit
                unit_qname = dimensions.get(_UNIT_DIM, "")
                unit_ref: Optional[str] = None
                if unit_qname:
                    if unit_qname in unit_cache:
                        unit_ref = unit_cache[unit_qname]
                    else:
                        unit_counter += 1
                        unit_ref = f"_unit_{unit_counter}"
                        unit = self._synthesize_unit(unit_ref, unit_qname)
                        doc.units[unit_ref] = unit
                        unit_cache[unit_qname] = unit_ref

                # Value
                value = fact_data.get("value", "")
                if value is None:
                    value = ""
                else:
                    value = str(value)

                # Decimals
                decimals_raw = fact_data.get("decimals")
                decimals: Optional[str] = None
                if decimals_raw is not None:
                    decimals = str(decimals_raw)

                # Nil
                is_nil = value == "" and fact_data.get("value") is None

                raw_fact = RawFact(
                    concept=concept_resolved,
                    context_ref=context_ref,
                    unit_ref=unit_ref,
                    value=value,
                    decimals=decimals,
                    id=str(fact_id),
                    is_nil=is_nil,
                )
                doc.facts.append(raw_fact)

            except Exception as exc:  # noqa: BLE001
                doc.parse_errors.append(
                    f"Error parsing fact '{fact_id}': {exc}"
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_json_qname(
        qname: str, namespaces: dict[str, str]
    ) -> str:
        """Resolve a prefixed QName to Clark notation using the namespace map.

        Parameters
        ----------
        qname:
            QName string (e.g. ``us-gaap:Assets``).
        namespaces:
            Prefix → URI mapping from documentInfo.

        Returns
        -------
        str
            Clark notation ``{namespace}localName`` or the original
            string if resolution fails.
        """
        if not qname or ":" not in qname:
            return qname

        prefix, local = qname.split(":", maxsplit=1)
        ns_uri = namespaces.get(prefix, "")
        if ns_uri:
            return f"{{{ns_uri}}}{local}"
        return qname

    @staticmethod
    def _build_context_key(dimensions: dict[str, Any]) -> str:
        """Build a hashable key from context-relevant dimensions."""
        parts: list[str] = []
        for dim in (_ENTITY_DIM, _PERIOD_DIM):
            val = dimensions.get(dim, "")
            parts.append(f"{dim}={val}")
        # Add explicit dimensions (non-core)
        for k, v in sorted(dimensions.items()):
            if k not in (_CONCEPT_DIM, _ENTITY_DIM, _PERIOD_DIM, _UNIT_DIM,
                         _LANGUAGE_DIM, _NOTE_ID_DIM):
                parts.append(f"{k}={v}")
        return "|".join(parts)

    @staticmethod
    def _synthesize_context(
        ctx_id: str, dimensions: dict[str, Any]
    ) -> RawContext:
        """Create a ``RawContext`` from xBRL-JSON dimensions."""
        ctx = RawContext(id=ctx_id)

        # Entity
        entity_val = str(dimensions.get(_ENTITY_DIM, ""))
        if entity_val:
            # Format: "scheme:identifier" or "scheme://authority identifier"
            if " " in entity_val:
                parts = entity_val.split(" ", maxsplit=1)
                ctx.entity_scheme = parts[0]
                ctx.entity_id = parts[1]
            elif ":" in entity_val:
                scheme, eid = entity_val.split(":", maxsplit=1)
                ctx.entity_scheme = scheme
                ctx.entity_id = eid
            else:
                ctx.entity_id = entity_val

        # Period
        period_val = str(dimensions.get(_PERIOD_DIM, ""))
        if period_val:
            if "/" in period_val:
                # Duration: "startDate/endDate"
                parts = period_val.split("/", maxsplit=1)
                ctx.period_type = "duration"
                ctx.start_date = parts[0]
                ctx.end_date = parts[1]
            elif period_val.lower() == "forever":
                ctx.period_type = "forever"
            else:
                ctx.period_type = "instant"
                ctx.instant = period_val

        return ctx

    @staticmethod
    def _synthesize_unit(
        unit_id: str, unit_qname: str
    ) -> RawUnit:
        """Create a ``RawUnit`` from an xBRL-JSON unit QName."""
        unit = RawUnit(id=unit_id)

        if "/" in unit_qname:
            # Divide: "numerator/denominator"
            parts = unit_qname.split("/", maxsplit=1)
            unit.divide_numerator = [parts[0].strip()]
            unit.divide_denominator = [parts[1].strip()]
        else:
            unit.measures = [unit_qname.strip()]

        return unit
