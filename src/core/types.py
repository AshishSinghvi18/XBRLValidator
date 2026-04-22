"""XBRL type system: enumerations, type aliases, and protocol classes.

Defines all value-types used throughout the validator.  Every numeric XBRL
value is represented as ``decimal.Decimal`` – **never** ``float``.

References:
    - XBRL 2.1 §4 (instance model)
    - XBRL Dimensions 1.0 §2
    - Inline XBRL 1.1 §4
    - XBRL Formula 1.0 §2
    - xBRL-JSON 1.0 / xBRL-CSV 1.0 (OIM)
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum, unique
from typing import Protocol, runtime_checkable

# ===========================================================================
# Enumerations
# ===========================================================================


@unique
class PeriodType(Enum):
    """XBRL period types as defined in XBRL 2.1 §4.7.2.

    Attributes:
        INSTANT:  Point-in-time period.
        DURATION: Start/end date range period.
        FOREVER:  Unbounded duration (''forever'' context).
    """

    INSTANT = "instant"
    DURATION = "duration"
    FOREVER = "forever"


@unique
class BalanceType(Enum):
    """Concept balance attribute – XBRL 2.1 §5.1.1.

    Attributes:
        DEBIT:  Normal debit balance.
        CREDIT: Normal credit balance.
        NONE:   No balance attribute declared.
    """

    DEBIT = "debit"
    CREDIT = "credit"
    NONE = "none"


@unique
class Severity(Enum):
    """Validation message severity levels.

    Attributes:
        ERROR:          Fatal – violates a MUST-level rule.
        WARNING:        Advisory – violates a SHOULD-level rule.
        INCONSISTENCY:  Calculation inconsistency (non-fatal by spec).
        INFO:           Informational observation.
    """

    ERROR = "error"
    WARNING = "warning"
    INCONSISTENCY = "inconsistency"
    INFO = "info"


@unique
class InputFormat(Enum):
    """Recognised input formats for the validator pipeline.

    Attributes:
        XBRL_XML:          Traditional XBRL 2.1 XML instance.
        IXBRL_HTML:        Inline XBRL embedded in HTML5.
        IXBRL_XHTML:       Inline XBRL embedded in XHTML.
        XBRL_JSON:         xBRL-JSON (OIM) format.
        XBRL_CSV:          xBRL-CSV (OIM) format.
        TAXONOMY_SCHEMA:   Standalone taxonomy schema (.xsd).
        LINKBASE:          Standalone linkbase document.
        TAXONOMY_PACKAGE:  Taxonomy package (.zip per spec).
        REPORT_PACKAGE:    Report package (.zip per ESEF RTS).
        UNKNOWN:           Format could not be determined.
    """

    XBRL_XML = "xbrl_xml"
    IXBRL_HTML = "ixbrl_html"
    IXBRL_XHTML = "ixbrl_xhtml"
    XBRL_JSON = "xbrl_json"
    XBRL_CSV = "xbrl_csv"
    TAXONOMY_SCHEMA = "taxonomy_schema"
    LINKBASE = "linkbase"
    TAXONOMY_PACKAGE = "taxonomy_package"
    REPORT_PACKAGE = "report_package"
    UNKNOWN = "unknown"


@unique
class ParserStrategy(Enum):
    """XML parser strategy selection.

    Attributes:
        DOM:       Full in-memory DOM tree (lxml).
        STREAMING: SAX/pull-parser for large files.
        HYBRID:    DOM for taxonomy, streaming for instances.
    """

    DOM = "dom"
    STREAMING = "streaming"
    HYBRID = "hybrid"


@unique
class LinkbaseType(Enum):
    """Linkbase document types – XBRL 2.1 §5.

    Attributes:
        CALCULATION:   Calculation linkbase (summation-item).
        PRESENTATION:  Presentation linkbase (parent-child).
        DEFINITION:    Definition linkbase (dimensions, general-special).
        LABEL:         Label linkbase (concept-label).
        REFERENCE:     Reference linkbase (concept-reference).
        FORMULA:       Formula linkbase (assertions / variables).
        TABLE:         Table linkbase.
        GENERIC:       Generic linkbase (generic links/arcs).
    """

    CALCULATION = "calculation"
    PRESENTATION = "presentation"
    DEFINITION = "definition"
    LABEL = "label"
    REFERENCE = "reference"
    FORMULA = "formula"
    TABLE = "table"
    GENERIC = "generic"


@unique
class SpillState(Enum):
    """Fact-store memory state – governs spill-to-disk transitions.

    Attributes:
        IN_MEMORY: All facts reside in RAM.
        SPILLING:  Currently flushing facts to disk.
        ON_DISK:   Majority of facts are on-disk; RAM holds hot-set.
    """

    IN_MEMORY = "in_memory"
    SPILLING = "spilling"
    ON_DISK = "on_disk"


@unique
class StorageType(Enum):
    """Underlying storage medium (used for I/O budget heuristics).

    Attributes:
        SSD:     Solid-state drive.
        HDD:     Spinning-disk hard drive.
        NETWORK: Network-attached storage.
        UNKNOWN: Could not be determined.
    """

    SSD = "ssd"
    HDD = "hdd"
    NETWORK = "network"
    UNKNOWN = "unknown"


@unique
class ConceptType(Enum):
    """Taxonomy concept item types.

    Attributes:
        ITEM:            Regular item concept – XBRL 2.1 §5.1.1.
        TUPLE:           Tuple concept – XBRL 2.1 §5.1.2.
        ABSTRACT:        Abstract concept (presentation only).
        DOMAIN:          Domain member head – XDT 1.0.
        HYPERCUBE:       Hypercube element – XDT 1.0.
        DIMENSION:       Explicit dimension element – XDT 1.0.
        TYPED_DIMENSION: Typed dimension element – XDT 1.0.
    """

    ITEM = "item"
    TUPLE = "tuple"
    ABSTRACT = "abstract"
    DOMAIN = "domain"
    HYPERCUBE = "hypercube"
    DIMENSION = "dimension"
    TYPED_DIMENSION = "typed_dimension"


@unique
class FactType(Enum):
    """Fact value categories.

    Attributes:
        NUMERIC:      Numeric simple fact (monetary, shares, pure, etc.).
        NON_NUMERIC:  Non-numeric simple fact (string, date, etc.).
        NIL:          Fact with xsi:nil='true'.
        FRACTION:     Fraction item fact.
        TUPLE:        Tuple container fact.
    """

    NUMERIC = "numeric"
    NON_NUMERIC = "non_numeric"
    NIL = "nil"
    FRACTION = "fraction"
    TUPLE = "tuple"


@unique
class AssertionType(Enum):
    """Formula assertion categories – Formula 1.0 §2.

    Attributes:
        VALUE:       Value assertion – evaluates an XPath expression.
        EXISTENCE:   Existence assertion – tests fact existence.
        CONSISTENCY: Consistency assertion – cross-validates fact sets.
    """

    VALUE = "value"
    EXISTENCE = "existence"
    CONSISTENCY = "consistency"


@unique
class RegulatorId(Enum):
    """Supported regulatory filing profiles.

    Attributes:
        EFM:    SEC EDGAR Filing Manual.
        ESEF:   European Single Electronic Format.
        FERC:   Federal Energy Regulatory Commission.
        HMRC:   UK HMRC iXBRL.
        CIPC:   South Africa CIPC.
        MCA:    India Ministry of Corporate Affairs.
        CUSTOM: User-defined custom profile.
    """

    EFM = "efm"
    ESEF = "esef"
    FERC = "ferc"
    HMRC = "hmrc"
    CIPC = "cipc"
    MCA = "mca"
    CUSTOM = "custom"


@unique
class CalculationMode(Enum):
    """Calculation validation mode.

    Attributes:
        CLASSIC:   XBRL 2.1 §5.2.5.2 calculation linkbase validation.
        CALC_1_1:  XBRL Calculations 1.1 specification validation.
    """

    CLASSIC = "classic"
    CALC_1_1 = "calc_1_1"


# ===========================================================================
# Type Aliases
# ===========================================================================

QName = str
"""Clark-notation QName: ``{namespace}localName``."""

ContextID = str
"""XBRL context ``id`` attribute value."""

UnitID = str
"""XBRL unit ``id`` attribute value."""

FactID = str
"""Unique fact identifier (``id`` attribute or synthetic)."""

ByteOffset = int
"""Byte offset into a file – used by streaming parsers."""

DimensionKey = tuple[tuple[str, str], ...]
"""Sorted tuple of (dimension-QName, member-QName) pairs for a context."""

RoleURI = str
"""An XBRL role URI string."""

ArcroleURI = str
"""An XBRL arcrole URI string."""

TaxonomyURL = str
"""Absolute URL for a taxonomy schema or linkbase document."""


# ===========================================================================
# Protocol Classes
# ===========================================================================


@runtime_checkable
class FactSource(Protocol):
    """Protocol for objects that can supply XBRL facts.

    Any fact-store implementation (in-memory list, spill-backed store,
    database-backed store) must satisfy this protocol.
    """

    def fact_count(self) -> int:
        """Return total number of facts available.

        Returns:
            Total fact count across all storage tiers.
        """
        ...

    def iter_fact_ids(self) -> list[FactID]:
        """Return a list of all fact identifiers.

        Returns:
            Ordered list of fact IDs.
        """
        ...


@runtime_checkable
class ValueReader(Protocol):
    """Protocol for reading typed XBRL fact values.

    Implementations must convert raw textual values to typed Python
    values.  Numeric values MUST be returned as ``Decimal``.
    """

    def read_decimal(self, raw: str) -> Decimal:
        """Parse a raw string into a Decimal value.

        Args:
            raw: The raw text content of a numeric fact.

        Returns:
            Parsed ``Decimal`` value.

        Raises:
            ValueError: If *raw* cannot be parsed as a valid decimal.
        """
        ...

    def read_string(self, raw: str) -> str:
        """Return a normalised string value.

        Args:
            raw: The raw text content of a non-numeric fact.

        Returns:
            Whitespace-normalised string value.
        """
        ...
