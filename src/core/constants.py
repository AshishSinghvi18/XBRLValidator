"""XBRL constants: namespaces, arcroles, standard roles, and thresholds.

All string constants use full URIs as defined in the relevant W3C and
XBRL International specifications.  Thresholds are configurable at
runtime via ``PipelineConfig``; values here are the *defaults*.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# NAMESPACES
# ---------------------------------------------------------------------------

NS_XBRLI: str = "http://www.xbrl.org/2003/instance"
NS_LINK: str = "http://www.xbrl.org/2003/linkbase"
NS_XLINK: str = "http://www.w3.org/1999/xlink"
NS_XSD: str = "http://www.w3.org/2001/XMLSchema"
NS_XSI: str = "http://www.w3.org/2001/XMLSchema-instance"
NS_IX: str = "http://www.xbrl.org/2013/inlineXBRL"
NS_IXT_PREFIX: str = "http://www.xbrl.org/inlineXBRL/transformation"
NS_ISO4217: str = "http://www.xbrl.org/2003/iso4217"
NS_XBRLDI: str = "http://xbrl.org/2006/xbrldi"
NS_XBRLDT: str = "http://xbrl.org/2005/xbrldt"
NS_XL: str = "http://www.xbrl.org/2003/XLink"
NS_GEN: str = "http://xbrl.org/2008/generic"
NS_FORMULA: str = "http://xbrl.org/2008/formula"
NS_VARIABLE: str = "http://xbrl.org/2008/variable"
NS_VALIDATION: str = "http://xbrl.org/2008/validation"
NS_ASSERTION: str = "http://xbrl.org/2008/assertion"
NS_VA: str = "http://xbrl.org/2008/assertion/value"
NS_EA: str = "http://xbrl.org/2008/assertion/existence"
NS_CA: str = "http://xbrl.org/2008/assertion/consistency"
NS_TABLE: str = "http://xbrl.org/2014/table"
NS_ENUM2: str = "http://xbrl.org/2020/extensible-enumerations-2.0"
NS_ESEF_TAXONOMY: str = "http://www.esma.europa.eu/taxonomy/"
NS_ESEF_ARCROLE: str = "http://www.esma.europa.eu/xbrl/esef/arcrole/"
NS_UTR: str = "http://www.xbrl.org/2009/utr"
NS_LRR: str = "http://www.xbrl.org/2005/lrr"
NS_OIM: str = "https://xbrl.org/2021"

# Convenience set of all XBRL-standard namespaces for quick membership tests.
STANDARD_NAMESPACES: frozenset[str] = frozenset(
    {
        NS_XBRLI,
        NS_LINK,
        NS_XLINK,
        NS_XSD,
        NS_XSI,
        NS_IX,
        NS_ISO4217,
        NS_XBRLDI,
        NS_XBRLDT,
        NS_XL,
        NS_GEN,
        NS_FORMULA,
        NS_VARIABLE,
        NS_VALIDATION,
        NS_ASSERTION,
        NS_VA,
        NS_EA,
        NS_CA,
        NS_TABLE,
        NS_ENUM2,
        NS_UTR,
        NS_LRR,
        NS_OIM,
    }
)

# ---------------------------------------------------------------------------
# ARCROLES — Core XBRL 2.1
# ---------------------------------------------------------------------------

ARCROLE_SUMMATION_ITEM: str = "http://www.xbrl.org/2003/arcrole/summation-item"
ARCROLE_SUMMATION_ITEM_1_1: str = "https://xbrl.org/2023/arcrole/summation-item"
ARCROLE_PARENT_CHILD: str = "http://www.xbrl.org/2003/arcrole/parent-child"
ARCROLE_CONCEPT_LABEL: str = "http://www.xbrl.org/2003/arcrole/concept-label"
ARCROLE_CONCEPT_REFERENCE: str = "http://www.xbrl.org/2003/arcrole/concept-reference"
ARCROLE_FACT_FOOTNOTE: str = "http://www.xbrl.org/2003/arcrole/fact-footnote"
ARCROLE_GENERAL_SPECIAL: str = "http://www.xbrl.org/2003/arcrole/general-special"
ARCROLE_ESSENCE_ALIAS: str = "http://www.xbrl.org/2003/arcrole/essence-alias"
ARCROLE_SIMILAR_TUPLES: str = "http://www.xbrl.org/2003/arcrole/similar-tuples"
ARCROLE_REQUIRES_ELEMENT: str = "http://www.xbrl.org/2003/arcrole/requires-element"

# ---------------------------------------------------------------------------
# ARCROLES — Dimensions
# ---------------------------------------------------------------------------

ARCROLE_DOMAIN_MEMBER: str = "http://xbrl.org/int/dim/arcrole/domain-member"
ARCROLE_DIMENSION_DOMAIN: str = "http://xbrl.org/int/dim/arcrole/dimension-domain"
ARCROLE_DIMENSION_DEFAULT: str = "http://xbrl.org/int/dim/arcrole/dimension-default"
ARCROLE_HYPERCUBE_DIM: str = "http://xbrl.org/int/dim/arcrole/hypercube-dimension"
ARCROLE_ALL: str = "http://xbrl.org/int/dim/arcrole/all"
ARCROLE_NOT_ALL: str = "http://xbrl.org/int/dim/arcrole/notAll"

# ---------------------------------------------------------------------------
# ARCROLES — ESEF
# ---------------------------------------------------------------------------

ARCROLE_WIDER_NARROWER: str = (
    "http://www.esma.europa.eu/xbrl/esef/arcrole/wider-narrower"
)

# ---------------------------------------------------------------------------
# ARCROLES — Formula
# ---------------------------------------------------------------------------

ARCROLE_VARIABLE_SET: str = "http://xbrl.org/arcrole/2008/variable-set"
ARCROLE_VARIABLE_FILTER: str = "http://xbrl.org/arcrole/2008/variable-filter"
ARCROLE_VARIABLE_SET_FILTER: str = (
    "http://xbrl.org/arcrole/2008/variable-set-filter"
)
ARCROLE_VARIABLE_SET_PRECOND: str = (
    "http://xbrl.org/arcrole/2008/variable-set-precondition"
)
ARCROLE_CONSISTENCY_ASSERT: str = (
    "http://xbrl.org/arcrole/2008/consistency-assertion-formula"
)
ARCROLE_ASSERTION_SET: str = "http://xbrl.org/arcrole/2008/assertion-set"

# ---------------------------------------------------------------------------
# ARCROLES — Table
# ---------------------------------------------------------------------------

ARCROLE_TABLE_BREAKDOWN: str = "http://xbrl.org/arcrole/2014/table-breakdown"
ARCROLE_BREAKDOWN_TREE: str = "http://xbrl.org/arcrole/2014/breakdown-tree"
ARCROLE_TABLE_FILTER: str = "http://xbrl.org/arcrole/2014/table-filter"
ARCROLE_TABLE_PARAMETER: str = "http://xbrl.org/arcrole/2014/table-parameter"

# ---------------------------------------------------------------------------
# ARCROLES — Generic Links
# ---------------------------------------------------------------------------

ARCROLE_ELEMENT_LABEL: str = "http://xbrl.org/arcrole/2008/element-label"
ARCROLE_ELEMENT_REFERENCE: str = "http://xbrl.org/arcrole/2008/element-reference"

# ---------------------------------------------------------------------------
# STANDARD ROLES
# ---------------------------------------------------------------------------

ROLE_LABEL_STANDARD: str = "http://www.xbrl.org/2003/role/label"
ROLE_LABEL_TERSE: str = "http://www.xbrl.org/2003/role/terseLabel"
ROLE_LABEL_VERBOSE: str = "http://www.xbrl.org/2003/role/verboseLabel"
ROLE_LABEL_DOCUMENTATION: str = "http://www.xbrl.org/2003/role/documentation"
ROLE_LABEL_DEFINITION: str = "http://www.xbrl.org/2003/role/definitionGuidance"
ROLE_LABEL_NEGATED: str = "http://www.xbrl.org/2009/role/negatedLabel"
ROLE_LABEL_NEGATED_TERSE: str = "http://www.xbrl.org/2009/role/negatedTerseLabel"
ROLE_LABEL_PERIOD_START: str = "http://www.xbrl.org/2003/role/periodStartLabel"
ROLE_LABEL_PERIOD_END: str = "http://www.xbrl.org/2003/role/periodEndLabel"
ROLE_FOOTNOTE: str = "http://www.xbrl.org/2003/role/footnote"
ROLE_LINK: str = "http://www.xbrl.org/2003/role/link"
ROLE_REFERENCE: str = "http://www.xbrl.org/2003/role/reference"
ROLE_LABEL_TOTAL: str = "http://www.xbrl.org/2009/role/totalLabel"
ROLE_LABEL_NET: str = "http://www.xbrl.org/2009/role/netLabel"
ROLE_LABEL_NEGATED_TOTAL: str = "http://www.xbrl.org/2009/role/negatedTotalLabel"
ROLE_LABEL_NEGATED_NET: str = "http://www.xbrl.org/2009/role/negatedNetLabel"
ROLE_LABEL_NEGATED_PERIOD_START: str = (
    "http://www.xbrl.org/2009/role/negatedPeriodStartLabel"
)
ROLE_LABEL_NEGATED_PERIOD_END: str = (
    "http://www.xbrl.org/2009/role/negatedPeriodEndLabel"
)

# ---------------------------------------------------------------------------
# THRESHOLDS — all configurable via PipelineConfig
# ---------------------------------------------------------------------------

DEFAULT_MEMORY_BUDGET_BYTES: int = 4 * 1024 * 1024 * 1024  # 4 GB
DEFAULT_LARGE_FILE_THRESHOLD_BYTES: int = 100 * 1024 * 1024  # 100 MB
DEFAULT_HUGE_FILE_THRESHOLD_BYTES: int = 1024 * 1024 * 1024  # 1 GB
DEFAULT_FACT_INDEX_SPILL_FACT_COUNT: int = 5_000_000  # 5 M facts
DEFAULT_FACT_INDEX_SPILL_BYTES: int = 500 * 1024 * 1024  # 500 MB
DEFAULT_ERROR_BUFFER_LIMIT: int = 10_000
DEFAULT_MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024 * 1024  # 10 GB
DEFAULT_IO_CHUNK_SIZE: int = 64 * 1024 * 1024  # 64 MB
DEFAULT_SAX_BUFFER_SIZE: int = 8 * 1024 * 1024  # 8 MB
DEFAULT_TAXONOMY_FETCH_TIMEOUT_S: int = 30
DEFAULT_MAX_ENTITY_EXPANSIONS: int = 100
DEFAULT_MAX_ZIP_UNCOMPRESSED_BYTES: int = 5 * 1024 * 1024 * 1024  # 5 GB
DEFAULT_MAX_ZIP_RATIO: int = 100
DEFAULT_MAX_ZIP_FILES: int = 10_000
DEFAULT_MAX_CONTINUATION_DEPTH: int = 1000  # iXBRL safety
DEFAULT_MAX_HYPERCUBE_DEPTH: int = 100  # infinite-loop guard
DEFAULT_FORMULA_TIMEOUT_S: int = 600  # per variable set
DEFAULT_XULE_TIMEOUT_S: int = 300  # per XULE rule
