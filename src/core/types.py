"""Core type definitions: enums, type aliases, and protocols.

All enumerations map directly to XBRL specification terminology.
Type aliases use canonical Clark-notation strings for QNames.
Protocols enable duck-typing for fact sources and value readers.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# ENUMS
# ---------------------------------------------------------------------------


class PeriodType(enum.Enum):
    """XBRL 2.1 §4.7.2 — period type of a concept."""

    INSTANT = "instant"
    DURATION = "duration"
    FOREVER = "forever"


class BalanceType(enum.Enum):
    """XBRL 2.1 §5.1.1.1 — balance attribute on monetary items."""

    DEBIT = "debit"
    CREDIT = "credit"
    NONE = "none"


class Severity(enum.Enum):
    """Severity levels for validation messages."""

    ERROR = "error"
    WARNING = "warning"
    INCONSISTENCY = "inconsistency"
    INFO = "info"


class InputFormat(enum.Enum):
    """Detected format of an input document."""

    XBRL_XML = "xbrl-xml"
    IXBRL_HTML = "ixbrl-html"
    IXBRL_XHTML = "ixbrl-xhtml"
    XBRL_JSON = "xbrl-json"
    XBRL_CSV = "xbrl-csv"
    TAXONOMY_SCHEMA = "taxonomy-schema"
    LINKBASE = "linkbase"
    TAXONOMY_PACKAGE = "taxonomy-package"
    REPORT_PACKAGE = "report-package"
    UNKNOWN = "unknown"


class ParserStrategy(enum.Enum):
    """Parsing strategy selected based on file size and format.

    Spec: Rule 2 — Streaming First.
    """

    DOM = "dom"
    STREAMING = "streaming"
    HYBRID = "hybrid"


class LinkbaseType(enum.Enum):
    """Types of XBRL linkbase documents."""

    CALCULATION = "calculation"
    PRESENTATION = "presentation"
    DEFINITION = "definition"
    LABEL = "label"
    REFERENCE = "reference"
    FORMULA = "formula"
    TABLE = "table"
    GENERIC = "generic"


class SpillState(enum.Enum):
    """Memory-pressure state for fact indices and error buffers.

    Spec: Rule 12 — Memory Budget.
    """

    IN_MEMORY = "in-memory"
    SPILLING = "spilling"
    ON_DISK = "on-disk"


class StorageType(enum.Enum):
    """Detected backing-store type.

    Spec: Rule 17 — conservative storage assumptions (default to HDD).
    """

    SSD = "ssd"
    HDD = "hdd"
    NETWORK = "network"
    UNKNOWN = "unknown"


class ConceptType(enum.Enum):
    """Taxonomy concept substitution group / archetype."""

    ITEM = "item"
    TUPLE = "tuple"
    ABSTRACT = "abstract"
    DOMAIN = "domain"
    HYPERCUBE = "hypercube"
    DIMENSION = "dimension"
    TYPED_DIMENSION = "typed-dimension"


class FactType(enum.Enum):
    """Runtime classification of a reported fact."""

    NUMERIC = "numeric"
    NON_NUMERIC = "non-numeric"
    NIL = "nil"
    FRACTION = "fraction"
    TUPLE = "tuple"


class AssertionType(enum.Enum):
    """XBRL Formula 1.0 assertion kinds."""

    VALUE = "value"
    EXISTENCE = "existence"
    CONSISTENCY = "consistency"


class RegulatorId(enum.Enum):
    """Known regulator profiles.

    Spec: Rule 5 — regulator isolation.
    """

    EFM = "efm"
    ESEF = "esef"
    FERC = "ferc"
    HMRC = "hmrc"
    CIPC = "cipc"
    MCA = "mca"
    CUSTOM = "custom"


class CalculationMode(enum.Enum):
    """Calculation linkbase specification version."""

    CLASSIC = "classic"
    CALC_1_1 = "calc-1.1"


# ---------------------------------------------------------------------------
# TYPE ALIASES
# ---------------------------------------------------------------------------

QName = str
"""Canonical Clark-notation QName: ``{namespace}localName``."""

ContextID = str
"""XBRL context ``id`` attribute."""

UnitID = str
"""XBRL unit ``id`` attribute."""

FactID = str
"""Unique identifier for a reported fact (may be auto-generated)."""

ByteOffset = int
"""Byte offset into a source file (for streaming / disk-spill indices)."""

DimensionKey = tuple[tuple[str, str], ...]
"""Sorted tuple of ``(dimensionQName, memberQName)`` pairs — hashable."""

RoleURI = str
"""A role URI string."""

ArcroleURI = str
"""An arcrole URI string."""

TaxonomyURL = str
"""URL or path to a taxonomy entry point."""


# ---------------------------------------------------------------------------
# PROTOCOLS
# ---------------------------------------------------------------------------


@runtime_checkable
class FactSource(Protocol):
    """Duck-type interface for any store that can supply facts.

    Implementations include in-memory fact lists, SQLite spill stores,
    and streaming iterators.
    """

    def get_facts_by_concept(self, concept: QName) -> Iterable[Any]:
        """Return all facts reporting the given concept."""
        ...

    def get_facts_by_context(self, ctx: ContextID) -> Iterable[Any]:
        """Return all facts sharing the given context id."""
        ...

    def get_all_facts(self) -> Iterable[Any]:
        """Iterate over every reported fact."""
        ...


@runtime_checkable
class ValueReader(Protocol):
    """Duck-type interface for reading raw values by byte offset.

    Used by disk-spill indices and chunked readers (Rule 17).
    """

    def read_value(self, offset: ByteOffset, length: int) -> bytes:
        """Read *length* bytes starting at *offset*."""
        ...
