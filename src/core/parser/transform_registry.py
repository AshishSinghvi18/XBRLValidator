"""Transform function registry for iXBRL inline transformations.

Manages registration and lookup of transformation functions indexed
by format QName (namespace + local name). Supports ixt-1 through ixt-5
and ixt-sec transformation registries.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

from src.core.constants import NS_IXT_PREFIX
from src.core.exceptions import IXBRLParseError
from src.utils.decimal_utils import XBRL_DECIMAL_CONTEXT

logger = structlog.get_logger(__name__)

# Type alias for transform functions
TransformFn = Callable[[str], str]


@dataclass
class TransformResult:
    """Result of applying an iXBRL transformation."""
    value: str
    success: bool = True
    error_message: str = ""
    source_format: str = ""


class TransformRegistry:
    """Registry of iXBRL transformation functions.

    Transform functions convert display-format values (as shown in the
    HTML document) to canonical XBRL values. Each transform is identified
    by a QName (namespace + local name).
    """

    def __init__(self) -> None:
        self._transforms: dict[str, TransformFn] = {}
        self._log = logger.bind(component="transform_registry")
        self._register_builtin_transforms()

    def register(self, namespace: str, local_name: str, fn: TransformFn) -> None:
        """Register a transform function for a given QName."""
        key = f"{{{namespace}}}{local_name}"
        self._transforms[key] = fn
        self._log.debug("transform_registered", key=key)

    def get(self, namespace: str, local_name: str) -> TransformFn | None:
        """Look up a transform function by QName."""
        key = f"{{{namespace}}}{local_name}"
        return self._transforms.get(key)

    def has(self, namespace: str, local_name: str) -> bool:
        """Check if a transform is registered."""
        key = f"{{{namespace}}}{local_name}"
        return key in self._transforms

    def apply(self, namespace: str, local_name: str, value: str) -> TransformResult:
        """Apply a registered transform to a value."""
        fn = self.get(namespace, local_name)
        if fn is None:
            return TransformResult(
                value=value,
                success=False,
                error_message=f"Unknown transform: {{{namespace}}}{local_name}",
                source_format=f"{{{namespace}}}{local_name}",
            )
        try:
            result = fn(value)
            return TransformResult(
                value=result,
                success=True,
                source_format=f"{{{namespace}}}{local_name}",
            )
        except Exception as exc:
            return TransformResult(
                value=value,
                success=False,
                error_message=str(exc),
                source_format=f"{{{namespace}}}{local_name}",
            )

    @property
    def registered_count(self) -> int:
        """Number of registered transforms."""
        return len(self._transforms)

    def _register_builtin_transforms(self) -> None:
        """Register all built-in iXBRL transformation functions."""
        # Common ixt namespaces (versioned)
        ixt_namespaces = [
            f"{NS_IXT_PREFIX}/2010-04-20",   # ixt-1
            f"{NS_IXT_PREFIX}/2011-07-31",   # ixt-2
            f"{NS_IXT_PREFIX}/2015-02-26",   # ixt-3
            f"{NS_IXT_PREFIX}/2020-02-12",   # ixt-4
            f"{NS_IXT_PREFIX}/2022-02-16",   # ixt-5
        ]
        # SEC-specific namespace
        sec_ns = "http://www.sec.gov/inlineXBRL/transformation/2015-08-31"

        for ns in ixt_namespaces:
            self._register_numeric_transforms(ns)
            self._register_date_transforms(ns)
            self._register_boolean_transforms(ns)
            self._register_string_transforms(ns)

        # SEC-specific transforms
        self._register_numeric_transforms(sec_ns)
        self._register_sec_transforms(sec_ns)

    def _register_numeric_transforms(self, ns: str) -> None:
        """Register numeric transformation functions."""
        self.register(ns, "numcommadot", _transform_numcommadot)
        self.register(ns, "numdotcomma", _transform_numdotcomma)
        self.register(ns, "numcommadecimal", _transform_numcommadot)
        self.register(ns, "numdotdecimal", _transform_numdotcomma)
        self.register(ns, "numspacedot", _transform_numspacedot)
        self.register(ns, "numspacecomma", _transform_numspacecomma)
        self.register(ns, "numdash", _transform_numdash)
        self.register(ns, "numunitdecimal", _transform_numunitdecimal)
        self.register(ns, "zerodash", _transform_zerodash)
        self.register(ns, "nocontent", _transform_nocontent)
        self.register(ns, "fixedzero", _transform_fixedzero)
        self.register(ns, "num-dot-decimal", _transform_numdotdecimal)
        self.register(ns, "num-comma-decimal", _transform_numcommadecimal)
        self.register(ns, "num-unit-decimal", _transform_numunitdecimal)

    def _register_date_transforms(self, ns: str) -> None:
        """Register date transformation functions."""
        self.register(ns, "datedoteu", _transform_datedoteu)
        self.register(ns, "datedotus", _transform_datedotus)
        self.register(ns, "dateslasheu", _transform_dateslasheu)
        self.register(ns, "dateslashus", _transform_dateslashus)
        self.register(ns, "datelonguk", _transform_datelonguk)
        self.register(ns, "datelongus", _transform_datelongus)
        self.register(ns, "dateshortuk", _transform_dateshortuk)
        self.register(ns, "dateshortus", _transform_dateshortus)
        self.register(ns, "datedaymonthyear", _transform_datedoteu)
        self.register(ns, "datemonthyear", _transform_datemonthyear)
        self.register(ns, "dateyearmonthday", _transform_dateyearmonthday)

    def _register_boolean_transforms(self, ns: str) -> None:
        """Register boolean transformation functions."""
        self.register(ns, "booleantrue", _transform_booleantrue)
        self.register(ns, "booleanfalse", _transform_booleanfalse)

    def _register_string_transforms(self, ns: str) -> None:
        """Register string transformation functions."""
        self.register(ns, "nocontent", _transform_nocontent)
        self.register(ns, "fixedempty", _transform_fixedempty)

    def _register_sec_transforms(self, ns: str) -> None:
        """Register SEC-specific transforms."""
        self.register(ns, "duryear", _transform_duryear)
        self.register(ns, "durmonth", _transform_durmonth)
        self.register(ns, "durwordsen", _transform_durwordsen)
        self.register(ns, "numwordsen", _transform_numwordsen)
        self.register(ns, "datequarterend", _transform_datequarterend)
        self.register(ns, "boolballotbox", _transform_boolballotbox)
        self.register(ns, "exchnameen", _transform_exchnameen)
        self.register(ns, "stateprovnameen", _transform_stateprovnameen)
        self.register(ns, "countrynameen", _transform_countrynameen)
        self.register(ns, "edabordomainadr", _transform_edgardomainname)
        self.register(ns, "entityfilercategoryen", _transform_entityfilercategory)


# ---------------------------------------------------------------------------
# Numeric transform functions
# ---------------------------------------------------------------------------

_COMMA_RE = re.compile(r",")
_DOT_RE = re.compile(r"\.")
_SPACE_RE = re.compile(r"\s")
_PAREN_RE = re.compile(r"^\s*\((.+)\)\s*$")


def _clean_numeric(text: str) -> str:
    """Remove parentheses (treat as negative) and whitespace."""
    stripped = text.strip()
    m = _PAREN_RE.match(stripped)
    if m:
        return "-" + m.group(1).strip()
    return stripped


def _transform_numcommadot(value: str) -> str:
    """1,234,567.89 -> 1234567.89"""
    cleaned = _clean_numeric(value)
    return _COMMA_RE.sub("", cleaned)


def _transform_numdotcomma(value: str) -> str:
    """1.234.567,89 -> 1234567.89"""
    cleaned = _clean_numeric(value)
    result = _DOT_RE.sub("", cleaned)
    return result.replace(",", ".")


def _transform_numspacedot(value: str) -> str:
    """1 234 567.89 -> 1234567.89"""
    cleaned = _clean_numeric(value)
    return _SPACE_RE.sub("", cleaned)


def _transform_numspacecomma(value: str) -> str:
    """1 234 567,89 -> 1234567.89"""
    cleaned = _clean_numeric(value)
    result = _SPACE_RE.sub("", cleaned)
    return result.replace(",", ".")


def _transform_numdash(value: str) -> str:
    """Dash (—, -, etc.) -> 0"""
    stripped = value.strip()
    if stripped in ("-", "—", "–", ""):
        return "0"
    return stripped


def _transform_numunitdecimal(value: str) -> str:
    """1234,56 (single comma as decimal) -> 1234.56"""
    cleaned = _clean_numeric(value)
    return cleaned.replace(",", ".")


def _transform_zerodash(value: str) -> str:
    """Any content -> 0"""
    return "0"


def _transform_nocontent(value: str) -> str:
    """Empty/whitespace -> empty string."""
    return ""


def _transform_fixedzero(value: str) -> str:
    """Any content -> 0"""
    return "0"


def _transform_fixedempty(value: str) -> str:
    """Any content -> empty string."""
    return ""


def _transform_numdotdecimal(value: str) -> str:
    """Handle num-dot-decimal: comma thousands, dot decimal."""
    return _transform_numcommadot(value)


def _transform_numcommadecimal(value: str) -> str:
    """Handle num-comma-decimal: dot thousands, comma decimal."""
    return _transform_numdotcomma(value)


# ---------------------------------------------------------------------------
# Date transform functions
# ---------------------------------------------------------------------------

_MONTH_MAP: dict[str, str] = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08", "sep": "09",
    "sept": "09", "oct": "10", "nov": "11", "dec": "12",
}


def _normalize_month(text: str) -> str:
    """Convert month name/number to two-digit month string."""
    lower = text.strip().lower().rstrip(".")
    if lower in _MONTH_MAP:
        return _MONTH_MAP[lower]
    if lower.isdigit():
        return lower.zfill(2)
    raise ValueError(f"Unknown month: {text!r}")


def _transform_datedoteu(value: str) -> str:
    """DD.MM.YYYY -> YYYY-MM-DD"""
    parts = value.strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"Expected DD.MM.YYYY format: {value!r}")
    day, month, year = parts[0].strip().zfill(2), parts[1].strip().zfill(2), parts[2].strip()
    return f"{year}-{month}-{day}"


def _transform_datedotus(value: str) -> str:
    """MM.DD.YYYY -> YYYY-MM-DD"""
    parts = value.strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"Expected MM.DD.YYYY format: {value!r}")
    month, day, year = parts[0].strip().zfill(2), parts[1].strip().zfill(2), parts[2].strip()
    return f"{year}-{month}-{day}"


def _transform_dateslasheu(value: str) -> str:
    """DD/MM/YYYY -> YYYY-MM-DD"""
    parts = value.strip().split("/")
    if len(parts) != 3:
        raise ValueError(f"Expected DD/MM/YYYY format: {value!r}")
    day, month, year = parts[0].strip().zfill(2), parts[1].strip().zfill(2), parts[2].strip()
    return f"{year}-{month}-{day}"


def _transform_dateslashus(value: str) -> str:
    """MM/DD/YYYY -> YYYY-MM-DD"""
    parts = value.strip().split("/")
    if len(parts) != 3:
        raise ValueError(f"Expected MM/DD/YYYY format: {value!r}")
    month, day, year = parts[0].strip().zfill(2), parts[1].strip().zfill(2), parts[2].strip()
    return f"{year}-{month}-{day}"


def _transform_datelonguk(value: str) -> str:
    """DD Month YYYY -> YYYY-MM-DD"""
    parts = re.split(r"[\s,]+", value.strip())
    if len(parts) < 3:
        raise ValueError(f"Expected 'DD Month YYYY' format: {value!r}")
    day = parts[0].strip().zfill(2)
    month = _normalize_month(parts[1])
    year = parts[2].strip()
    return f"{year}-{month}-{day}"


def _transform_datelongus(value: str) -> str:
    """Month DD, YYYY -> YYYY-MM-DD"""
    parts = re.split(r"[\s,]+", value.strip())
    if len(parts) < 3:
        raise ValueError(f"Expected 'Month DD, YYYY' format: {value!r}")
    month = _normalize_month(parts[0])
    day = parts[1].strip().zfill(2)
    year = parts[2].strip()
    return f"{year}-{month}-{day}"


def _transform_dateshortuk(value: str) -> str:
    """DD Mon YYYY -> YYYY-MM-DD"""
    return _transform_datelonguk(value)


def _transform_dateshortus(value: str) -> str:
    """Mon DD, YYYY -> YYYY-MM-DD"""
    return _transform_datelongus(value)


def _transform_datemonthyear(value: str) -> str:
    """Month YYYY or Mon YYYY -> YYYY-MM (last day of month)"""
    parts = re.split(r"[\s,]+", value.strip())
    if len(parts) < 2:
        raise ValueError(f"Expected 'Month YYYY' format: {value!r}")
    month = _normalize_month(parts[0])
    year = parts[1].strip()
    return f"{year}-{month}"


def _transform_dateyearmonthday(value: str) -> str:
    """YYYY-MM-DD passthrough (already canonical)."""
    return value.strip()


# ---------------------------------------------------------------------------
# Boolean transform functions
# ---------------------------------------------------------------------------


def _transform_booleantrue(value: str) -> str:
    """Any content -> true"""
    return "true"


def _transform_booleanfalse(value: str) -> str:
    """Any content -> false"""
    return "false"


# ---------------------------------------------------------------------------
# SEC-specific transform functions
# ---------------------------------------------------------------------------


def _transform_duryear(value: str) -> str:
    """'3' or '3 years' -> P3Y"""
    stripped = value.strip()
    num = re.match(r"(\d+)", stripped)
    if num:
        return f"P{num.group(1)}Y"
    raise ValueError(f"Cannot parse duration years: {value!r}")


def _transform_durmonth(value: str) -> str:
    """'6' or '6 months' -> P6M"""
    stripped = value.strip()
    num = re.match(r"(\d+)", stripped)
    if num:
        return f"P{num.group(1)}M"
    raise ValueError(f"Cannot parse duration months: {value!r}")


_WORD_NUMS: dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100,
}


def _transform_durwordsen(value: str) -> str:
    """'three years' -> P3Y, 'six months' -> P6M"""
    stripped = value.strip().lower()
    parts = re.split(r"[\s,]+", stripped)
    if len(parts) >= 2:
        num_word = parts[0]
        unit_word = parts[-1].rstrip("s")
        num_val = _WORD_NUMS.get(num_word)
        if num_val is not None:
            if unit_word in ("year",):
                return f"P{num_val}Y"
            if unit_word in ("month",):
                return f"P{num_val}M"
            if unit_word in ("day",):
                return f"P{num_val}D"
    raise ValueError(f"Cannot parse duration words: {value!r}")


def _transform_numwordsen(value: str) -> str:
    """'three' -> 3, 'twenty-one' -> 21"""
    stripped = value.strip().lower()
    if stripped in _WORD_NUMS:
        return str(_WORD_NUMS[stripped])
    # Handle compound numbers like 'twenty-one'
    parts = re.split(r"[-\s]+", stripped)
    if len(parts) == 2:
        tens = _WORD_NUMS.get(parts[0], 0)
        ones = _WORD_NUMS.get(parts[1], 0)
        return str(tens + ones)
    raise ValueError(f"Cannot parse number words: {value!r}")


def _transform_datequarterend(value: str) -> str:
    """'Q1 2024' -> 2024-03-31"""
    parts = re.split(r"[\s,]+", value.strip())
    quarter_str = ""
    year_str = ""
    for p in parts:
        if p.upper().startswith("Q"):
            quarter_str = p[1:]
        elif p.isdigit() and len(p) == 4:
            year_str = p
    if not quarter_str or not year_str:
        raise ValueError(f"Cannot parse quarter end: {value!r}")
    quarter = int(quarter_str)
    quarter_ends = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
    end = quarter_ends.get(quarter)
    if end is None:
        raise ValueError(f"Invalid quarter number: {quarter}")
    return f"{year_str}-{end}"


def _transform_boolballotbox(value: str) -> str:
    """Ballot box characters -> true/false"""
    stripped = value.strip()
    # ☑ (U+2611) or ✓ (U+2713) or ✔ (U+2714) -> true
    if any(c in stripped for c in "☑✓✔☒"):
        return "true"
    # ☐ (U+2610) -> false
    if "☐" in stripped:
        return "false"
    # Fallback: non-empty -> true
    return "true" if stripped else "false"


def _transform_exchnameen(value: str) -> str:
    """Exchange name passthrough (normalized)."""
    return value.strip()


def _transform_stateprovnameen(value: str) -> str:
    """State/province name passthrough (normalized)."""
    return value.strip()


def _transform_countrynameen(value: str) -> str:
    """Country name passthrough (normalized)."""
    return value.strip()


def _transform_edgardomainname(value: str) -> str:
    """EDGAR domain name passthrough."""
    return value.strip()


def _transform_entityfilercategory(value: str) -> str:
    """Entity filer category passthrough."""
    return value.strip()
