"""XBRL Validator core constants.

All namespace URIs, arcrole URIs, and threshold values used throughout
the validation engine.
"""

# XML/XBRL Namespaces
NS_XBRLI = "http://www.xbrl.org/2003/instance"
NS_LINK = "http://www.xbrl.org/2003/linkbase"
NS_XLINK = "http://www.w3.org/1999/xlink"
NS_XSD = "http://www.w3.org/2001/XMLSchema"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
NS_IX = "http://www.xbrl.org/2013/inlineXBRL"
NS_IXT_PREFIX = "http://www.xbrl.org/inlineXBRL/transformation"
NS_ISO4217 = "http://www.xbrl.org/2003/iso4217"
NS_XBRLDI = "http://xbrl.org/2006/xbrldi"
NS_XBRLDT = "http://xbrl.org/2005/xbrldt"
NS_XML = "http://www.w3.org/XML/1998/namespace"
NS_XHTML = "http://www.w3.org/1999/xhtml"

# Arcroles
ARCROLE_SUMMATION_ITEM = "http://www.xbrl.org/2003/arcrole/summation-item"
ARCROLE_PARENT_CHILD = "http://www.xbrl.org/2003/arcrole/parent-child"
ARCROLE_DOMAIN_MEMBER = "http://xbrl.org/int/dim/arcrole/domain-member"
ARCROLE_DIMENSION_DOMAIN = "http://xbrl.org/int/dim/arcrole/dimension-domain"
ARCROLE_DIMENSION_DEFAULT = "http://xbrl.org/int/dim/arcrole/dimension-default"
ARCROLE_HYPERCUBE_DIM = "http://xbrl.org/int/dim/arcrole/hypercube-dimension"
ARCROLE_ALL = "http://xbrl.org/int/dim/arcrole/all"
ARCROLE_NOT_ALL = "http://xbrl.org/int/dim/arcrole/notAll"
ARCROLE_WIDER_NARROWER = "http://www.esma.europa.eu/xbrl/esef/arcrole/wider-narrower"
ARCROLE_CONCEPT_LABEL = "http://www.xbrl.org/2003/arcrole/concept-label"
ARCROLE_CONCEPT_REF = "http://www.xbrl.org/2003/arcrole/concept-reference"
ARCROLE_FOOTNOTE = "http://www.xbrl.org/2003/arcrole/fact-footnote"

# Thresholds (all configurable via PipelineConfig)
DEFAULT_LARGE_FILE_THRESHOLD_BYTES = 100 * 1024 * 1024  # 100 MB
DEFAULT_MEMORY_BUDGET_BYTES = 4 * 1024 * 1024 * 1024  # 4 GB
DEFAULT_FACT_INDEX_SPILL_THRESHOLD = 10_000_000  # 10M facts
DEFAULT_ERROR_BUFFER_LIMIT = 10_000
DEFAULT_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB
DEFAULT_IO_CHUNK_SIZE = 64 * 1024 * 1024  # 64 MB
DEFAULT_SAX_BUFFER_SIZE = 8 * 1024 * 1024  # 8 MB
DEFAULT_TAXONOMY_FETCH_TIMEOUT_S = 30
DEFAULT_MAX_ENTITY_EXPANSIONS = 100
