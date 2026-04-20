"""XBRL Validator core type definitions.

Enumerations and type aliases used throughout the validation engine.
Spec references:

- XBRL 2.1 §4.7 (PeriodType), §4.6 (BalanceType)
- XBRL Dimensions 1.0 §2 (DimensionKey)
- Inline XBRL 1.1 §4 (InputFormat.IXBRL_HTML)
"""

from enum import Enum


class PeriodType(Enum):
    """XBRL period types as defined in XBRL 2.1 §4.7.

    Controls whether a concept reports a point-in-time value (INSTANT),
    a value over a span of time (DURATION), or applies regardless of
    time (FOREVER).
    """

    INSTANT = "instant"
    DURATION = "duration"
    FOREVER = "forever"


class BalanceType(Enum):
    """XBRL balance types as defined in XBRL 2.1 §4.6.

    Indicates whether a monetary concept normally carries a debit
    or credit balance.
    """

    DEBIT = "debit"
    CREDIT = "credit"


class Severity(Enum):
    """Severity level for validation findings.

    ERROR: spec violation that must be fixed.
    WARNING: likely issue that should be reviewed.
    INCONSISTENCY: cross-check mismatch (e.g., calculation inconsistency).
    INFO: informational finding, not necessarily an issue.
    """

    ERROR = "error"
    WARNING = "warning"
    INCONSISTENCY = "inconsistency"
    INFO = "info"


class InputFormat(Enum):
    """Supported XBRL input formats.

    Covers all standard XBRL formats plus taxonomy schema and linkbase
    files that may be validated independently.
    """

    XBRL_XML = "xbrl_xml"
    IXBRL_HTML = "ixbrl_html"
    XBRL_JSON = "xbrl_json"
    XBRL_CSV = "xbrl_csv"
    TAXONOMY_SCHEMA = "taxonomy_schema"
    LINKBASE = "linkbase"
    UNKNOWN = "unknown"


class ParserStrategy(Enum):
    """Parser strategy selection.

    DOM: full in-memory parse via lxml etree; best for files that fit
         comfortably in memory.
    STREAMING: SAX/iterparse-based parse for large files that exceed
               the memory budget.
    """

    DOM = "dom"
    STREAMING = "streaming"


class LinkbaseType(Enum):
    """XBRL linkbase types as defined in XBRL 2.1 §5.

    Each linkbase type contributes a different class of relationships
    to the Discoverable Taxonomy Set (DTS).
    """

    CALCULATION = "calculation"
    PRESENTATION = "presentation"
    DEFINITION = "definition"
    LABEL = "label"
    REFERENCE = "reference"
    FORMULA = "formula"


class SpillState(Enum):
    """Fact-index spill state for memory management.

    IN_MEMORY: all facts fit within the configured memory budget.
    SPILLING: facts are being flushed from memory to disk.
    ON_DISK: fact index has been fully spilled to disk-backed storage.
    """

    IN_MEMORY = "in_memory"
    SPILLING = "spilling"
    ON_DISK = "on_disk"


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

QName = str
"""A qualified name in ``prefix:localName`` or Clark ``{namespace}localName`` form."""

ContextID = str
"""Identifier for an XBRL context element (``@id`` attribute)."""

UnitID = str
"""Identifier for an XBRL unit element (``@id`` attribute)."""

FactID = str
"""Identifier for an XBRL fact (``@id`` attribute or synthetic key)."""

ByteOffset = int
"""Byte offset within a file, used by the streaming parser."""

DimensionKey = tuple[tuple[str, str], ...]
"""Immutable, hashable representation of a dimensional combination.

Each inner tuple is ``(dimension_qname, member_qname)`` sorted by
dimension QName for deterministic hashing.
"""
