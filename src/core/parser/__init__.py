"""XBRL parser modules — format detection, XML/iXBRL/JSON/CSV parsing.

Re-exports the primary parser classes for convenient access::

    from src.core.parser import FormatDetector, XMLParser, IXBRLParser
"""

from src.core.parser.csv_parser import XBRLCSVDocument, XBRLCSVParser
from src.core.parser.datetime_parser import (
    Period,
    parse_xbrl_period,
    parse_xml_date,
    parse_xml_datetime,
    parse_xml_duration,
    period_contains,
    periods_equal,
)
from src.core.parser.decimal_parser import (
    apply_scale,
    parse_decimals,
    parse_precision,
    parse_scale,
    parse_xbrl_decimal,
    parse_xbrl_double,
    round_to_decimals,
)
from src.core.parser.format_detector import (
    DetectionResult,
    FormatDetector,
    PackageDetectionResult,
)
from src.core.parser.ixbrl_continuation import (
    ContinuationFact,
    ContinuationFragment,
    ContinuationResolver,
    ResolvedFact,
)
from src.core.parser.ixbrl_parser import (
    InlineFact,
    InlineFootnote,
    InlineRelationship,
    InlineXBRLDocument,
    IXBRLParser,
)
from src.core.parser.ixbrl_transforms import IXBRLTransformEngine, TransformResult
from src.core.parser.json_parser import XBRLJSONDocument, XBRLJSONParser
from src.core.parser.package_parser import (
    FilingZip,
    PackageParser,
    ReportPackage,
    TaxonomyPackage,
)
from src.core.parser.transform_registry import TransformRegistry
from src.core.parser.xml_parser import RawXBRLDocument, XMLParser

__all__ = [
    # Format detection
    "DetectionResult",
    "FormatDetector",
    "PackageDetectionResult",
    # XML
    "RawXBRLDocument",
    "XMLParser",
    # Decimal / numeric
    "apply_scale",
    "parse_decimals",
    "parse_precision",
    "parse_scale",
    "parse_xbrl_decimal",
    "parse_xbrl_double",
    "round_to_decimals",
    # Date / time
    "Period",
    "parse_xbrl_period",
    "parse_xml_date",
    "parse_xml_datetime",
    "parse_xml_duration",
    "period_contains",
    "periods_equal",
    # iXBRL
    "ContinuationFact",
    "ContinuationFragment",
    "ContinuationResolver",
    "IXBRLParser",
    "IXBRLTransformEngine",
    "InlineFact",
    "InlineFootnote",
    "InlineRelationship",
    "InlineXBRLDocument",
    "ResolvedFact",
    "TransformRegistry",
    "TransformResult",
    # JSON
    "XBRLJSONDocument",
    "XBRLJSONParser",
    # CSV
    "XBRLCSVDocument",
    "XBRLCSVParser",
    # Packages
    "FilingZip",
    "PackageParser",
    "ReportPackage",
    "TaxonomyPackage",
]
