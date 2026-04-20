"""XBRL namespace URIs, arcrole URIs, standard roles, and threshold constants.

All constants follow the XBRL 2.1 specification (https://www.xbrl.org/Specification/XBRL-2.1/),
Inline XBRL 1.1 (https://www.xbrl.org/Specification/inlineXBRL-part1/),
XBRL Dimensions 1.0 (https://www.xbrl.org/Specification/XDT-REC-2006-09-18+Corrected-Errata-2009-09-07.htm),
XBRL Formula 1.0 (https://www.xbrl.org/Specification/formula/),
XBRL Table Linkbase 1.0, and the OIM specification.

References:
    - XBRL 2.1 §3 Namespaces
    - XBRL Dimensions 1.0 §1.2
    - XBRL Formula 1.0 §1.2
    - ESEF Reporting Manual Annex II
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

# ---------------------------------------------------------------------------
# XBRL Core Namespaces (XBRL 2.1 §3)
# ---------------------------------------------------------------------------
NS_XBRLI: Final[str] = "http://www.xbrl.org/2003/instance"
"""XBRL Instance namespace – XBRL 2.1 §3."""

NS_LINK: Final[str] = "http://www.xbrl.org/2003/linkbase"
"""XBRL Linkbase namespace – XBRL 2.1 §3.5."""

NS_XLINK: Final[str] = "http://www.w3.org/1999/xlink"
"""W3C XLink namespace used in XBRL linkbases."""

NS_XSD: Final[str] = "http://www.w3.org/2001/XMLSchema"
"""W3C XML Schema namespace."""

NS_XSI: Final[str] = "http://www.w3.org/2001/XMLSchema-instance"
"""W3C XML Schema Instance namespace."""

NS_XML: Final[str] = "http://www.w3.org/XML/1998/namespace"
"""W3C XML namespace."""

# ---------------------------------------------------------------------------
# Inline XBRL Namespaces (Inline XBRL 1.1 §2)
# ---------------------------------------------------------------------------
NS_IX: Final[str] = "http://www.xbrl.org/2013/inlineXBRL"
"""Inline XBRL 1.1 namespace."""

NS_IXT_PREFIX: Final[str] = "http://www.xbrl.org/inlineXBRL/transformation"
"""Base URI prefix for Inline XBRL Transformation Rules registries."""

# ---------------------------------------------------------------------------
# ISO / Unit Namespaces
# ---------------------------------------------------------------------------
NS_ISO4217: Final[str] = "http://www.xbrl.org/2003/iso4217"
"""ISO 4217 currency code namespace – XBRL 2.1 §4.8.2."""

NS_UTR: Final[str] = "http://www.xbrl.org/2009/utr"
"""XBRL Units Registry namespace."""

# ---------------------------------------------------------------------------
# XBRL Dimensions Namespaces (XDT 1.0 §1.2)
# ---------------------------------------------------------------------------
NS_XBRLDI: Final[str] = "http://xbrl.org/2006/xbrldi"
"""XBRL Dimensions instance namespace – XDT 1.0 §1.2."""

NS_XBRLDT: Final[str] = "http://xbrl.org/2005/xbrldt"
"""XBRL Dimensions taxonomy namespace – XDT 1.0 §1.2."""

# ---------------------------------------------------------------------------
# Generic / Extended Link Namespaces
# ---------------------------------------------------------------------------
NS_XL: Final[str] = "http://www.xbrl.org/2003/XLink"
"""XBRL XLink extended namespace for typed extended links."""

NS_GEN: Final[str] = "http://xbrl.org/2008/generic"
"""Generic linkbase namespace."""

# ---------------------------------------------------------------------------
# Formula / Variables / Assertions Namespaces (Formula 1.0)
# ---------------------------------------------------------------------------
NS_FORMULA: Final[str] = "http://xbrl.org/2008/formula"
"""XBRL Formula 1.0 namespace."""

NS_VARIABLE: Final[str] = "http://xbrl.org/2008/variable"
"""XBRL Variables 1.0 namespace."""

NS_VALIDATION: Final[str] = "http://xbrl.org/2008/validation"
"""XBRL Validation namespace."""

NS_ASSERTION: Final[str] = "http://xbrl.org/2008/assertion"
"""XBRL Assertion namespace (general)."""

NS_VA: Final[str] = "http://xbrl.org/2008/assertion/value"
"""XBRL Value Assertion namespace."""

NS_EA: Final[str] = "http://xbrl.org/2008/assertion/existence"
"""XBRL Existence Assertion namespace."""

NS_CA: Final[str] = "http://xbrl.org/2008/assertion/consistency"
"""XBRL Consistency Assertion namespace."""

# ---------------------------------------------------------------------------
# Table Linkbase Namespace (Table 1.0)
# ---------------------------------------------------------------------------
NS_TABLE: Final[str] = "http://xbrl.org/2014/table"
"""XBRL Table Linkbase 1.0 namespace."""

# ---------------------------------------------------------------------------
# Extensible Enumerations 2.0
# ---------------------------------------------------------------------------
NS_ENUM2: Final[str] = "http://xbrl.org/2020/extensible-enumerations-2.0"
"""XBRL Extensible Enumerations 2.0 namespace."""

# ---------------------------------------------------------------------------
# ESEF Namespaces (ESEF Reporting Manual 2023)
# ---------------------------------------------------------------------------
NS_ESEF_TAXONOMY: Final[str] = "http://www.esma.europa.eu/taxonomy/2022"
"""ESEF ESMA base taxonomy namespace."""

NS_ESEF_ARCROLE: Final[str] = "http://www.esma.europa.eu/xbrl/esef/arcrole"
"""ESEF-specific arcrole namespace."""

# ---------------------------------------------------------------------------
# Label / Reference / Link Role Registry
# ---------------------------------------------------------------------------
NS_LRR: Final[str] = "http://www.xbrl.org/2008/roleref"
"""Link Role Registry namespace."""

# ---------------------------------------------------------------------------
# Open Information Model (OIM) Namespace
# ---------------------------------------------------------------------------
NS_OIM: Final[str] = "https://xbrl.org/2021/oim"
"""Open Information Model namespace – xBRL-JSON / xBRL-CSV."""


# ===========================================================================
# Arcrole URIs
# ===========================================================================

# XBRL 2.1 Arcroles (§5.2.6)
ARCROLE_CONCEPT_LABEL: Final[str] = "http://www.xbrl.org/2003/arcrole/concept-label"
"""Arcrole: concept → label – XBRL 2.1 §5.2.6.2."""

ARCROLE_CONCEPT_REFERENCE: Final[str] = "http://www.xbrl.org/2003/arcrole/concept-reference"
"""Arcrole: concept → reference – XBRL 2.1 §5.2.6.2."""

ARCROLE_PARENT_CHILD: Final[str] = "http://www.xbrl.org/2003/arcrole/parent-child"
"""Arcrole: parent-child presentation – XBRL 2.1 §5.2.6.2."""

ARCROLE_SUMMATION_ITEM: Final[str] = "http://www.xbrl.org/2003/arcrole/summation-item"
"""Arcrole: summation-item calculation – XBRL 2.1 §5.2.6.2."""

ARCROLE_GENERAL_SPECIAL: Final[str] = "http://www.xbrl.org/2003/arcrole/general-special"
"""Arcrole: general-special definition – XBRL 2.1 §5.2.6.2."""

ARCROLE_ESSENCE_ALIAS: Final[str] = "http://www.xbrl.org/2003/arcrole/essence-alias"
"""Arcrole: essence-alias definition – XBRL 2.1 §5.2.6.2."""

ARCROLE_SIMILAR_TUPLES: Final[str] = "http://www.xbrl.org/2003/arcrole/similar-tuples"
"""Arcrole: similar-tuples definition – XBRL 2.1 §5.2.6.2."""

ARCROLE_REQUIRES_ELEMENT: Final[str] = "http://www.xbrl.org/2003/arcrole/requires-element"
"""Arcrole: requires-element definition – XBRL 2.1 §5.2.6.2."""

ARCROLE_FACT_FOOTNOTE: Final[str] = "http://www.xbrl.org/2003/arcrole/fact-footnote"
"""Arcrole: fact → footnote – XBRL 2.1 §4.11.1."""

# Dimensions Arcroles (XDT 1.0 §2)
ARCROLE_DIMENSION_DOMAIN: Final[str] = "http://xbrl.org/int/dim/arcrole/dimension-domain"
"""Arcrole: dimension → domain – XDT 1.0 §2.2.1."""

ARCROLE_DOMAIN_MEMBER: Final[str] = "http://xbrl.org/int/dim/arcrole/domain-member"
"""Arcrole: domain → member – XDT 1.0 §2.2.2."""

ARCROLE_HYPERCUBE_DIMENSION: Final[str] = "http://xbrl.org/int/dim/arcrole/hypercube-dimension"
"""Arcrole: hypercube → dimension – XDT 1.0 §2.2.3."""

ARCROLE_ALL: Final[str] = "http://xbrl.org/int/dim/arcrole/all"
"""Arcrole: has-hypercube (all) – XDT 1.0 §2.2.4."""

ARCROLE_NOT_ALL: Final[str] = "http://xbrl.org/int/dim/arcrole/notAll"
"""Arcrole: has-hypercube (notAll) – XDT 1.0 §2.2.5."""

ARCROLE_DIMENSION_DEFAULT: Final[str] = "http://xbrl.org/int/dim/arcrole/dimension-default"
"""Arcrole: dimension → default member – XDT 1.0 §2.6.1."""

# Formula Arcroles (Formula 1.0)
ARCROLE_VARIABLE_SET: Final[str] = "http://xbrl.org/arcrole/2008/variable-set"
"""Arcrole: variable-set – Formula 1.0."""

ARCROLE_VARIABLE_FILTER: Final[str] = "http://xbrl.org/arcrole/2008/variable-filter"
"""Arcrole: variable-filter – Formula 1.0."""

ARCROLE_VARIABLE_SET_FILTER: Final[str] = "http://xbrl.org/arcrole/2008/variable-set-filter"
"""Arcrole: variable-set-filter – Formula 1.0."""

ARCROLE_VARIABLE_SET_PRECONDITION: Final[str] = (
    "http://xbrl.org/arcrole/2008/variable-set-precondition"
)
"""Arcrole: variable-set-precondition – Formula 1.0."""

ARCROLE_CONSISTENCY_ASSERTION_FORMULA: Final[str] = (
    "http://xbrl.org/arcrole/2008/consistency-assertion-formula"
)
"""Arcrole: consistency-assertion-formula – Formula 1.0."""

ARCROLE_ASSERTION_SET: Final[str] = "http://xbrl.org/arcrole/2008/assertion-set"
"""Arcrole: assertion-set – Formula 1.0."""

# Table Arcroles (Table 1.0)
ARCROLE_TABLE_BREAKDOWN: Final[str] = "http://xbrl.org/arcrole/2014/table-breakdown"
"""Arcrole: table → breakdown – Table 1.0."""

ARCROLE_BREAKDOWN_TREE: Final[str] = "http://xbrl.org/arcrole/2014/breakdown-tree"
"""Arcrole: breakdown → tree – Table 1.0."""

ARCROLE_TABLE_FILTER: Final[str] = "http://xbrl.org/arcrole/2014/table-filter"
"""Arcrole: table → filter – Table 1.0."""

ARCROLE_TABLE_PARAMETER: Final[str] = "http://xbrl.org/arcrole/2014/table-parameter"
"""Arcrole: table → parameter – Table 1.0."""

# Generic Link Arcroles
ARCROLE_ELEMENT_LABEL: Final[str] = "http://xbrl.org/arcrole/2008/element-label"
"""Arcrole: element-label – Generic Links 1.0."""

ARCROLE_ELEMENT_REFERENCE: Final[str] = "http://xbrl.org/arcrole/2008/element-reference"
"""Arcrole: element-reference – Generic Links 1.0."""


# ===========================================================================
# Standard Label Roles (XBRL 2.1 §5.2.6.2)
# ===========================================================================
ROLE_LABEL_STANDARD: Final[str] = "http://www.xbrl.org/2003/role/label"
"""Standard label role – XBRL 2.1 §5.2.6.2."""

ROLE_LABEL_TERSE: Final[str] = "http://www.xbrl.org/2003/role/terseLabel"
"""Terse label role – XBRL 2.1 §5.2.6.2."""

ROLE_LABEL_VERBOSE: Final[str] = "http://www.xbrl.org/2003/role/verboseLabel"
"""Verbose label role – XBRL 2.1 §5.2.6.2."""

ROLE_LABEL_DOCUMENTATION: Final[str] = "http://www.xbrl.org/2003/role/documentation"
"""Documentation label role – XBRL 2.1 §5.2.6.2."""

ROLE_LABEL_PERIOD_START: Final[str] = "http://www.xbrl.org/2003/role/periodStartLabel"
"""Period-start label role – XBRL 2.1 §5.2.6.2."""

ROLE_LABEL_PERIOD_END: Final[str] = "http://www.xbrl.org/2003/role/periodEndLabel"
"""Period-end label role – XBRL 2.1 §5.2.6.2."""

ROLE_LABEL_TOTAL: Final[str] = "http://www.xbrl.org/2003/role/totalLabel"
"""Total label role – XBRL 2.1 §5.2.6.2."""

ROLE_LABEL_NEGATED: Final[str] = "http://www.xbrl.org/2003/role/negatedLabel"
"""Negated label role – XBRL 2.1 §5.2.6.2."""

ROLE_LABEL_NEGATED_TERSE: Final[str] = "http://www.xbrl.org/2003/role/negatedTerseLabel"
"""Negated terse label role."""

ROLE_LABEL_NEGATED_TOTAL: Final[str] = "http://www.xbrl.org/2003/role/negatedTotalLabel"
"""Negated total label role."""

ROLE_LABEL_NET: Final[str] = "http://www.xbrl.org/2009/role/netLabel"
"""Net label role – Label Role Registry."""

ROLE_LABEL_POSITIVEVERBOSE: Final[str] = "http://www.xbrl.org/2003/role/positiveVerboseLabel"
"""Positive verbose label role."""

ROLE_LABEL_NEGATIVETERSE: Final[str] = "http://www.xbrl.org/2003/role/negativeTerseLabel"
"""Negative terse label role."""

# Standard Link Roles
ROLE_LINK: Final[str] = "http://www.xbrl.org/2003/role/link"
"""Default link role – XBRL 2.1 §5.2.6.2."""

ROLE_REFERENCE: Final[str] = "http://www.xbrl.org/2003/role/reference"
"""Standard reference role – XBRL 2.1 §5.2.6.2."""


# ===========================================================================
# Default Threshold / Budget Constants
# ===========================================================================

DEFAULT_MAX_FILE_SIZE_BYTES: Final[int] = 100 * 1024 * 1024  # 100 MB
"""Maximum individual file size before rejection – security guard."""

DEFAULT_MAX_TAXONOMY_DOWNLOAD_BYTES: Final[int] = 1 * 1024 * 1024 * 1024  # 1 GB
"""Maximum total taxonomy download budget – prevents runaway fetches."""

DEFAULT_MEMORY_BUDGET_BYTES: Final[int] = 4 * 1024 * 1024 * 1024  # 4 GB
"""In-process memory budget before triggering spill-to-disk."""

DEFAULT_FACT_SPILL_THRESHOLD: Final[int] = 5_000_000
"""Number of in-memory facts before spilling to disk-backed storage."""

DEFAULT_MAX_ENTITY_EXPANSION: Final[int] = 10_000
"""Maximum XML entity expansions – prevents billion-laughs attacks."""

DEFAULT_MAX_ELEMENT_DEPTH: Final[int] = 512
"""Maximum XML element nesting depth – prevents stack-overflow attacks."""

DEFAULT_HTTP_TIMEOUT_SECONDS: Final[int] = 30
"""Default HTTP request timeout for taxonomy fetches."""

DEFAULT_HTTP_MAX_REDIRECTS: Final[int] = 5
"""Maximum HTTP redirects allowed."""

DEFAULT_CACHE_TTL_SECONDS: Final[int] = 86400  # 24 hours
"""Default taxonomy cache TTL in seconds."""

DEFAULT_CALC_TOLERANCE: Final[Decimal] = Decimal("0.01")
"""Default tolerance for calculation linkbase consistency checks.

Per XBRL 2.1 §5.2.5.2, rounding is performed before comparison; this
tolerance accounts for accumulated rounding in multi-level rollups.
"""

DEFAULT_MAX_WORKERS: Final[int] = 4
"""Default parallelism for taxonomy resolution and validation passes."""

DEFAULT_MAX_ZIP_ENTRIES: Final[int] = 10_000
"""Maximum entries in a taxonomy/report ZIP package – prevents zip-bombs."""

DEFAULT_MAX_ZIP_RATIO: Final[int] = 100
"""Maximum compression ratio allowed for ZIP entries – zip-bomb guard."""

DEFAULT_MAX_ZIP_TOTAL_SIZE: Final[int] = 2 * 1024 * 1024 * 1024  # 2 GB
"""Maximum total uncompressed size of ZIP contents."""

DEFAULT_STREAMING_CHUNK_SIZE: Final[int] = 64 * 1024  # 64 KB
"""Chunk size for streaming XML parsing – balances latency and throughput."""

DEFAULT_DISK_SPILL_DIR: Final[str] = ".xbrl_validator_spill"
"""Default directory name for spill-to-disk storage."""

DEFAULT_LOG_LEVEL: Final[str] = "INFO"
"""Default logging level."""
