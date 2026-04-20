"""XBRL-JSON (OIM) parser.

Parses xBRL-JSON documents conforming to the Open Information Model (OIM)
specification (https://www.xbrl.org/Specification/xbrl-json/REC-2021-10-13/
xbrl-json-REC-2021-10-13.html).

**Rule 16 compliance**: numeric fact values are *always* kept as ``str`` –
they are never decoded into ``float`` to avoid precision loss.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Fast JSON: prefer orjson, fall back to stdlib json.
try:
    import orjson

    def _loads(data: bytes | str) -> Any:
        if isinstance(data, str):
            data = data.encode("utf-8")
        return orjson.loads(data)

except ImportError:  # pragma: no cover
    import json

    def _loads(data: bytes | str) -> Any:  # type: ignore[misc]
        return json.loads(data)


from src.core.constants import NS_OIM
from src.core.exceptions import JSONParseError
from src.core.types import InputFormat

__all__ = [
    "JSONDocumentInfo",
    "JSONFact",
    "XBRLJSONDocument",
    "XBRLJSONParser",
]

logger = logging.getLogger(__name__)

# Recognised xBRL-JSON document type URIs.
_RECOGNISED_DOCUMENT_TYPES: frozenset[str] = frozenset(
    {
        "https://xbrl.org/2021/xbrl-json",
        "https://xbrl.org/CR/2021-07-07/xbrl-json",
    }
)

# Core OIM dimension names that map to dedicated JSONFact fields.
_CORE_DIMENSIONS: frozenset[str] = frozenset(
    {"concept", "entity", "period", "unit", "language"}
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JSONDocumentInfo:
    """Parsed ``documentInfo`` section of an xBRL-JSON document."""

    document_type: str
    """Document type URI (e.g. ``"https://xbrl.org/2021/xbrl-json"``)."""

    namespaces: dict[str, str]
    """Prefix → namespace URI mapping declared in ``documentInfo``."""

    taxonomy: list[str]
    """Taxonomy entry-point URLs."""

    features: dict[str, str | bool]
    """Optional features map."""

    base_url: str = ""
    """Base URL for relative URI resolution."""


@dataclass
class JSONFact:
    """A single fact extracted from an xBRL-JSON document.

    Numeric values are stored as **strings** (Rule 16 compliance) to prevent
    any floating-point precision loss.
    """

    fact_id: str
    """Unique fact identifier (the JSON object key)."""

    concept: str
    """Concept in Clark notation ``{namespaceURI}localName``."""

    value: str | None
    """Fact value.  Always ``str`` for numerics (Rule 16).  ``None`` for nil."""

    entity: str | None
    """Entity identifier, if present."""

    period: dict[str, str] | None
    """Period information dict (``instant`` or ``startDate``/``endDate``)."""

    unit: str | None
    """Unit string, if present."""

    decimals: str | None
    """Decimals as string (``"INF"`` or integer string), if present."""

    dimensions: dict[str, str]
    """Non-core dimension → member mappings."""

    is_nil: bool = False
    """``True`` when the fact's value is ``null`` (nil)."""

    links: dict[str, list[str]] | None = None
    """Optional link groups referencing other facts."""


@dataclass
class XBRLJSONDocument:
    """Complete parsed representation of an xBRL-JSON file."""

    source_file: str
    """Original file path or source name."""

    source_size: int
    """Size of the source data in bytes."""

    document_info: JSONDocumentInfo
    """Parsed document info section."""

    facts: list[JSONFact]
    """All facts extracted from the document."""

    format: InputFormat = InputFormat.XBRL_JSON
    """Format discriminator."""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class XBRLJSONParser:
    """Parser for xBRL-JSON (OIM) documents.

    Usage::

        parser = XBRLJSONParser()
        doc = parser.parse("report.json")
        for fact in doc.facts:
            print(fact.concept, fact.value)
    """

    # ---- public API -------------------------------------------------------

    def parse(self, file_path: str) -> XBRLJSONDocument:
        """Parse an xBRL-JSON file from disk.

        Args:
            file_path: Path to the ``.json`` file.

        Returns:
            Fully parsed :class:`XBRLJSONDocument`.

        Raises:
            JSONParseError: On any structural or validation error.
        """
        path = Path(file_path)
        if not path.is_file():
            raise JSONParseError(
                "JSON-0001",
                f"File not found: {file_path}",
                file_path=file_path,
            )

        try:
            raw_bytes = path.read_bytes()
        except OSError as exc:
            raise JSONParseError(
                "JSON-0002",
                f"Cannot read file: {exc}",
                file_path=file_path,
            ) from exc

        source_size = len(raw_bytes)
        raw = self._decode_json(raw_bytes, file_path)
        return self._build_document(raw, file_path, source_size)

    def parse_bytes(
        self, data: bytes, source_name: str = "<bytes>"
    ) -> XBRLJSONDocument:
        """Parse xBRL-JSON from an in-memory byte string.

        Args:
            data: Raw JSON bytes.
            source_name: Human-readable source label for error messages.

        Returns:
            Fully parsed :class:`XBRLJSONDocument`.

        Raises:
            JSONParseError: On any structural or validation error.
        """
        raw = self._decode_json(data, source_name)
        return self._build_document(raw, source_name, len(data))

    # ---- internal ---------------------------------------------------------

    def _decode_json(self, data: bytes | str, source: str) -> dict[str, Any]:
        """Deserialise raw bytes/str into a Python dict."""
        try:
            result = _loads(data)
        except Exception as exc:
            raise JSONParseError(
                "JSON-0003",
                f"Invalid JSON: {exc}",
                file_path=source,
            ) from exc

        if not isinstance(result, dict):
            raise JSONParseError(
                "JSON-0004",
                "Top-level JSON value must be an object",
                file_path=source,
            )
        return result

    def _build_document(
        self, raw: dict[str, Any], source: str, source_size: int
    ) -> XBRLJSONDocument:
        """Construct an :class:`XBRLJSONDocument` from a decoded JSON dict."""
        if "documentInfo" not in raw:
            raise JSONParseError(
                "JSON-0010",
                "Missing required top-level key 'documentInfo'",
                file_path=source,
            )

        doc_info = self._parse_document_info(raw["documentInfo"], source)
        namespaces = doc_info.namespaces

        raw_facts: dict[str, Any] = raw.get("facts", {})
        if not isinstance(raw_facts, dict):
            raise JSONParseError(
                "JSON-0020",
                "'facts' must be a JSON object",
                file_path=source,
            )

        facts: list[JSONFact] = []
        for fact_id, fact_raw in raw_facts.items():
            if not isinstance(fact_raw, dict):
                raise JSONParseError(
                    "JSON-0021",
                    f"Fact '{fact_id}' must be a JSON object",
                    file_path=source,
                )
            facts.append(self._parse_fact(fact_id, fact_raw, namespaces, source))

        return XBRLJSONDocument(
            source_file=source,
            source_size=source_size,
            document_info=doc_info,
            facts=facts,
        )

    # ---- documentInfo -----------------------------------------------------

    def _parse_document_info(
        self, raw: Any, source: str
    ) -> JSONDocumentInfo:
        """Extract and validate the ``documentInfo`` section.

        Args:
            raw: The decoded ``documentInfo`` JSON value.
            source: Source label for error messages.

        Returns:
            A validated :class:`JSONDocumentInfo`.

        Raises:
            JSONParseError: If required fields are missing or malformed.
        """
        if not isinstance(raw, dict):
            raise JSONParseError(
                "JSON-0011",
                "'documentInfo' must be a JSON object",
                file_path=source,
            )

        # -- documentType (required) ----------------------------------------
        doc_type = raw.get("documentType")
        if not isinstance(doc_type, str) or not doc_type:
            raise JSONParseError(
                "JSON-0012",
                "Missing or invalid 'documentInfo.documentType'",
                file_path=source,
            )
        if doc_type not in _RECOGNISED_DOCUMENT_TYPES:
            logger.warning(
                "Unrecognised xBRL-JSON documentType '%s' in %s – "
                "proceeding with best-effort parsing",
                doc_type,
                source,
            )

        # -- namespaces (required) ------------------------------------------
        namespaces_raw = raw.get("namespaces", {})
        if not isinstance(namespaces_raw, dict):
            raise JSONParseError(
                "JSON-0013",
                "'documentInfo.namespaces' must be a JSON object",
                file_path=source,
            )
        namespaces: dict[str, str] = {}
        for prefix, uri in namespaces_raw.items():
            if not isinstance(uri, str):
                raise JSONParseError(
                    "JSON-0014",
                    f"Namespace URI for prefix '{prefix}' must be a string",
                    file_path=source,
                )
            namespaces[prefix] = uri

        # -- taxonomy (required) --------------------------------------------
        taxonomy_raw = raw.get("taxonomy", [])
        if not isinstance(taxonomy_raw, list):
            raise JSONParseError(
                "JSON-0015",
                "'documentInfo.taxonomy' must be a JSON array",
                file_path=source,
            )
        taxonomy: list[str] = []
        for idx, entry in enumerate(taxonomy_raw):
            if not isinstance(entry, str):
                raise JSONParseError(
                    "JSON-0016",
                    f"taxonomy[{idx}] must be a string",
                    file_path=source,
                )
            taxonomy.append(entry)

        # -- features (optional) --------------------------------------------
        features_raw = raw.get("features", {})
        if not isinstance(features_raw, dict):
            raise JSONParseError(
                "JSON-0017",
                "'documentInfo.features' must be a JSON object",
                file_path=source,
            )
        features: dict[str, str | bool] = {}
        for key, val in features_raw.items():
            if isinstance(val, (str, bool)):
                features[key] = val
            else:
                features[key] = str(val)

        # -- baseURL (optional) ---------------------------------------------
        base_url = raw.get("baseURL", "")
        if not isinstance(base_url, str):
            base_url = str(base_url)

        return JSONDocumentInfo(
            document_type=doc_type,
            namespaces=namespaces,
            taxonomy=taxonomy,
            features=features,
            base_url=base_url,
        )

    # ---- facts ------------------------------------------------------------

    def _parse_fact(
        self,
        fact_id: str,
        raw: dict[str, Any],
        namespaces: dict[str, str],
        source: str,
    ) -> JSONFact:
        """Parse a single fact from its decoded JSON representation.

        **Rule 16**: the ``value`` field is always stored as ``str``.  If the
        JSON decoder materialised a numeric Python type (``int`` / ``float``),
        we convert it back to its string representation immediately.

        Args:
            fact_id: The fact's identifier (JSON object key).
            raw: Decoded JSON object for this fact.
            namespaces: Namespace prefix map from documentInfo.
            source: Source label for error messages.

        Returns:
            A populated :class:`JSONFact`.
        """
        # -- value (Rule 16: keep as str) -----------------------------------
        raw_value = raw.get("value")
        is_nil = raw_value is None
        if is_nil:
            value: str | None = None
        elif isinstance(raw_value, str):
            value = raw_value
        elif isinstance(raw_value, (int, float)):
            # Shouldn't happen in valid xBRL-JSON, but be safe.
            logger.debug(
                "Fact '%s': numeric value decoded by JSON parser – "
                "converting to str for Rule 16 compliance",
                fact_id,
            )
            value = str(raw_value)
        elif isinstance(raw_value, bool):
            # bool is subclass of int in Python – handle before int check.
            value = "true" if raw_value else "false"
        else:
            value = str(raw_value)

        # -- dimensions -----------------------------------------------------
        dims_raw: dict[str, Any] = raw.get("dimensions", {})
        if not isinstance(dims_raw, dict):
            raise JSONParseError(
                "JSON-0022",
                f"Fact '{fact_id}': 'dimensions' must be a JSON object",
                file_path=source,
            )

        # Core dimensions
        concept_raw = dims_raw.get("concept")
        concept: str
        if isinstance(concept_raw, str) and concept_raw:
            concept = self._resolve_prefixed_name(concept_raw, namespaces)
        else:
            raise JSONParseError(
                "JSON-0023",
                f"Fact '{fact_id}': missing or invalid 'concept' dimension",
                file_path=source,
            )

        entity: str | None = None
        entity_raw = dims_raw.get("entity")
        if isinstance(entity_raw, str):
            entity = entity_raw

        period: dict[str, str] | None = None
        period_raw = dims_raw.get("period")
        if isinstance(period_raw, str):
            # Instant period supplied as a plain date string.
            period = {"instant": period_raw}
        elif isinstance(period_raw, dict):
            period = {k: str(v) for k, v in period_raw.items()}

        unit: str | None = None
        unit_raw = dims_raw.get("unit")
        if isinstance(unit_raw, str):
            unit = unit_raw

        # Non-core (custom) dimensions
        custom_dims: dict[str, str] = {}
        for dim_key, dim_val in dims_raw.items():
            if dim_key in _CORE_DIMENSIONS:
                continue
            if isinstance(dim_val, str):
                custom_dims[dim_key] = self._resolve_prefixed_name(
                    dim_val, namespaces
                )
            else:
                custom_dims[dim_key] = str(dim_val)

        # -- decimals (keep as str) -----------------------------------------
        decimals: str | None = None
        decimals_raw = raw.get("decimals")
        if decimals_raw is not None:
            decimals = str(decimals_raw)

        # -- links (optional) -----------------------------------------------
        links: dict[str, list[str]] | None = None
        links_raw = raw.get("links")
        if isinstance(links_raw, dict):
            links = {}
            for group, targets in links_raw.items():
                if isinstance(targets, list):
                    links[group] = [str(t) for t in targets]
                else:
                    links[group] = [str(targets)]

        return JSONFact(
            fact_id=fact_id,
            concept=concept,
            value=value,
            entity=entity,
            period=period,
            unit=unit,
            decimals=decimals,
            dimensions=custom_dims,
            is_nil=is_nil,
            links=links,
        )

    # ---- helpers ----------------------------------------------------------

    @staticmethod
    def _resolve_prefixed_name(
        name: str, namespaces: dict[str, str]
    ) -> str:
        """Convert a prefixed name to Clark notation.

        ``"prefix:localName"`` → ``"{namespaceURI}localName"``

        If *name* contains no colon it is returned unchanged.  If the prefix
        is not found in *namespaces* the name is also returned as-is with a
        warning logged.

        Args:
            name: Potentially prefixed name.
            namespaces: Prefix → namespace URI mapping.

        Returns:
            Name in Clark notation, or the original name if no prefix
            resolution is possible.
        """
        if ":" not in name:
            return name

        prefix, _, local = name.partition(":")
        uri = namespaces.get(prefix)
        if uri is None:
            logger.warning(
                "Unresolvable namespace prefix '%s' in name '%s'",
                prefix,
                name,
            )
            return name

        return f"{{{uri}}}{local}"
