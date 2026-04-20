"""XBRL parsers — format detection, XML/iXBRL/JSON/CSV parsing.

All parsers produce the canonical model dataclasses defined in
``src.core.model``.
"""

from __future__ import annotations

from src.core.parser.format_detector import DetectionResult, FormatDetector
from src.core.parser.xml_parser import RawXBRLDocument, XMLParser
from src.core.parser.ixbrl_parser import InlineXBRLDocument, IXBRLParser
from src.core.parser.decimal_parser import (
    apply_scale,
    parse_decimals,
    parse_precision,
    parse_scale,
    parse_xbrl_decimal,
    parse_xbrl_double,
    round_to_decimals,
)
from src.core.parser.datetime_parser import (
    parse_xbrl_period,
    parse_xml_date,
    parse_xml_datetime,
    parse_xml_duration,
    period_contains,
    periods_equal,
)

__all__ = [
    "DetectionResult",
    "FormatDetector",
    "IXBRLParser",
    "InlineXBRLDocument",
    "RawXBRLDocument",
    "XMLParser",
    "apply_scale",
    "parse_decimals",
    "parse_precision",
    "parse_scale",
    "parse_xbrl_decimal",
    "parse_xbrl_double",
    "parse_xml_date",
    "parse_xml_datetime",
    "parse_xml_duration",
    "parse_xbrl_period",
    "period_contains",
    "periods_equal",
    "round_to_decimals",
]
