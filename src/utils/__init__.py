"""Utility modules for the XBRL Validator.

Re-exports commonly used helpers so callers can do::

    from src.utils import sha256_hex, safe_decimal, format_bytes
"""

from __future__ import annotations

from src.utils.datetime_utils import (
    duration_days,
    format_xsd_date,
    format_xsd_datetime,
    instant_to_date,
    is_same_instant,
    parse_xsd_date,
    parse_xsd_date_or_datetime,
    parse_xsd_datetime,
)
from src.utils.decimal_utils import (
    compute_tolerance,
    decimals_to_precision,
    effective_value,
    infer_decimals,
    precision_to_decimals,
    round_decimal,
    safe_compare,
    safe_decimal,
)
from src.utils.hash_utils import cache_key, content_fingerprint, sha256_file, sha256_hex
from src.utils.locale_utils import (
    extract_primary_language,
    find_best_match,
    is_valid_language_tag,
    language_matches,
    normalise_language_tag,
)
from src.utils.logging_config import configure_logging, get_logger
from src.utils.size_utils import check_file_size, format_bytes, parse_size
from src.utils.xml_utils import (
    build_nsmap,
    element_text,
    element_text_recursive,
    get_attr,
    get_attr_bool,
    get_clark_name,
    get_local_name,
    get_namespace,
    safe_parse_xml,
)
from src.utils.zip_utils import (
    list_entries,
    safe_extract_all,
    safe_read_entry,
    validate_zip_safety,
)

__all__ = [
    # decimal_utils
    "safe_decimal",
    "safe_compare",
    "round_decimal",
    "infer_decimals",
    "precision_to_decimals",
    "decimals_to_precision",
    "compute_tolerance",
    "effective_value",
    # xml_utils
    "get_namespace",
    "get_local_name",
    "get_clark_name",
    "element_text",
    "element_text_recursive",
    "get_attr",
    "get_attr_bool",
    "build_nsmap",
    "safe_parse_xml",
    # hash_utils
    "sha256_hex",
    "sha256_file",
    "cache_key",
    "content_fingerprint",
    # size_utils
    "format_bytes",
    "parse_size",
    "check_file_size",
    # datetime_utils
    "parse_xsd_date",
    "parse_xsd_datetime",
    "parse_xsd_date_or_datetime",
    "instant_to_date",
    "duration_days",
    "is_same_instant",
    "format_xsd_date",
    "format_xsd_datetime",
    # zip_utils
    "validate_zip_safety",
    "safe_extract_all",
    "safe_read_entry",
    "list_entries",
    # logging_config
    "configure_logging",
    "get_logger",
    # locale_utils
    "is_valid_language_tag",
    "normalise_language_tag",
    "language_matches",
    "extract_primary_language",
    "find_best_match",
]
