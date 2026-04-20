"""Registry for iXBRL transformation functions.

Manages the mapping from iXBRL ``@format`` QNames to callable
transformation functions that convert human-readable display values
into XBRL-canonical values.

Built-in transforms cover the XBRL International Transformation Registry
(ixt namespace) and SEC-specific extensions (ixt-sec namespace).

Spec references:
- Inline XBRL Transformation Registry 4 (ixt:*)
- SEC EDGAR iXBRL Transformation Extensions (ixt-sec:*)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Month name mappings
# ---------------------------------------------------------------------------

_MONTH_NAMES: dict[str, str] = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08", "sep": "09",
    "oct": "10", "nov": "11", "dec": "12",
}

_WORD_NUMBERS: dict[str, str] = {
    "no": "0", "none": "0", "zero": "0",
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
    "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40",
    "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80",
    "ninety": "90", "hundred": "100",
}


# ---------------------------------------------------------------------------
# Built-in transform functions
# ---------------------------------------------------------------------------


def _ixt_numdotdecimal(value: str) -> str:
    """ixt:numdotdecimal — strip grouping commas, keep dot decimal."""
    cleaned = value.strip().replace(",", "").replace(" ", "")
    # Validate it's a valid decimal
    Decimal(cleaned)
    return cleaned


def _ixt_numcommadecimal(value: str) -> str:
    """ixt:numcommadecimal — European style: dot grouping, comma decimal."""
    cleaned = value.strip().replace(".", "").replace(" ", "")
    cleaned = cleaned.replace(",", ".")
    Decimal(cleaned)
    return cleaned


def _ixt_zerodash(value: str) -> str:
    """ixt:zerodash — dash/hyphen/em-dash to '0'."""
    stripped = value.strip()
    if stripped in ("-", "\u2014", "\u2013", "\u2012", "\u2015"):
        return "0"
    raise ValueError(f"zerodash expects a dash character, got {stripped!r}")


def _ixt_nocontent(value: str) -> str:
    """ixt:nocontent — empty display value maps to empty string."""
    return ""


def _ixt_fixedzero(value: str) -> str:
    """ixt:fixedzero — any display value maps to '0'."""
    return "0"


def _ixt_booleanfalse(value: str) -> str:
    """ixt:booleanfalse — display value maps to 'false'."""
    return "false"


def _ixt_booleantrue(value: str) -> str:
    """ixt:booleantrue — display value maps to 'true'."""
    return "true"


def _ixt_dateslashus(value: str) -> str:
    """ixt:dateslashus — MM/DD/YYYY → YYYY-MM-DD."""
    parts = value.strip().split("/")
    if len(parts) != 3:
        raise ValueError(f"dateslashus expects MM/DD/YYYY, got {value!r}")
    mm, dd, yyyy = parts
    return f"{yyyy.zfill(4)}-{mm.zfill(2)}-{dd.zfill(2)}"


def _ixt_dateslasheu(value: str) -> str:
    """ixt:dateslasheu — DD/MM/YYYY → YYYY-MM-DD."""
    parts = value.strip().split("/")
    if len(parts) != 3:
        raise ValueError(f"dateslasheu expects DD/MM/YYYY, got {value!r}")
    dd, mm, yyyy = parts
    return f"{yyyy.zfill(4)}-{mm.zfill(2)}-{dd.zfill(2)}"


def _ixt_datedoteu(value: str) -> str:
    """ixt:datedoteu — DD.MM.YYYY → YYYY-MM-DD."""
    parts = value.strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"datedoteu expects DD.MM.YYYY, got {value!r}")
    dd, mm, yyyy = parts
    return f"{yyyy.zfill(4)}-{mm.zfill(2)}-{dd.zfill(2)}"


def _parse_long_date(value: str, us_order: bool) -> str:
    """Parse 'Month DD, YYYY' or 'DD Month YYYY' → YYYY-MM-DD."""
    cleaned = re.sub(r"[,.]", " ", value.strip())
    parts = cleaned.split()
    if len(parts) < 3:
        raise ValueError(f"Cannot parse long date: {value!r}")

    if us_order:
        # Month DD YYYY
        month_str = parts[0].lower()
        day_str = parts[1]
        year_str = parts[2]
    else:
        # DD Month YYYY
        day_str = parts[0]
        month_str = parts[1].lower()
        year_str = parts[2]

    mm = _MONTH_NAMES.get(month_str)
    if mm is None:
        raise ValueError(f"Unknown month name: {month_str!r}")

    return f"{year_str.zfill(4)}-{mm}-{day_str.zfill(2)}"


def _ixt_datelongus(value: str) -> str:
    """ixt:datelongus — 'January 1, 2024' → '2024-01-01'."""
    return _parse_long_date(value, us_order=True)


def _ixt_datelonguk(value: str) -> str:
    """ixt:datelonguk — '1 January 2024' → '2024-01-01'."""
    return _parse_long_date(value, us_order=False)


def _ixt_durday(value: str) -> str:
    """ixt:durday — number of days → ISO 8601 duration 'PnD'."""
    n = int(value.strip())
    return f"P{n}D"


def _ixt_durmonth(value: str) -> str:
    """ixt:durmonth — number of months → ISO 8601 duration 'PnM'."""
    n = int(value.strip())
    return f"P{n}M"


def _ixt_duryear(value: str) -> str:
    """ixt:duryear — number of years → ISO 8601 duration 'PnY'."""
    n = int(value.strip())
    return f"P{n}Y"


def _ixt_sec_duryear(value: str) -> str:
    """ixt-sec:duryear — SEC variant: number of years → 'PnY'.

    Same as ixt:duryear but handles additional SEC patterns.
    """
    cleaned = value.strip().rstrip(" years").rstrip(" year")
    n = int(cleaned)
    return f"P{n}Y"


def _ixt_sec_durmonth(value: str) -> str:
    """ixt-sec:durmonth — SEC variant: number of months → 'PnM'."""
    cleaned = value.strip().rstrip(" months").rstrip(" month")
    n = int(cleaned)
    return f"P{n}M"


def _ixt_sec_numwordsen(value: str) -> str:
    """ixt-sec:numwordsen — English number words → numeric string.

    Handles simple cases: 'one', 'twenty', 'thirty-five', etc.
    Complex cases (e.g. 'one hundred twenty-three') are handled
    by accumulation.
    """
    cleaned = value.strip().lower().replace("-", " ").replace(",", " ")
    tokens = cleaned.split()

    if not tokens:
        raise ValueError(f"numwordsen: empty input: {value!r}")

    # Handle "no" / "none" / "zero"
    if len(tokens) == 1 and tokens[0] in _WORD_NUMBERS:
        return _WORD_NUMBERS[tokens[0]]

    total = 0
    current = 0
    for token in tokens:
        if token == "and":
            continue
        num = _WORD_NUMBERS.get(token)
        if num is None:
            raise ValueError(f"numwordsen: unknown word '{token}' in {value!r}")
        n = int(num)
        if n == 100:
            current = current * 100 if current > 0 else 100
        else:
            current += n

    total += current
    return str(total)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TransformRegistry:
    """Registry for iXBRL transformation functions.

    Maintains a mapping from iXBRL ``@format`` QNames (e.g.
    ``ixt:numdotdecimal``) to callable transformation functions.

    Parameters
    ----------
    registry_paths:
        Optional list of paths to JSON files containing additional
        transform definitions. Each JSON file should map format
        QNames to transform specifications.
    """

    def __init__(
        self, registry_paths: list[str] | None = None
    ) -> None:
        self._transforms: dict[str, Callable[[str], str]] = {}
        self._register_builtins()

        if registry_paths:
            for path in registry_paths:
                self._load_from_json(path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_transform(
        self, format_qname: str
    ) -> Optional[Callable[[str], str]]:
        """Look up a transform function by its format QName.

        Parameters
        ----------
        format_qname:
            The ``@format`` attribute value (e.g. ``ixt:numdotdecimal``).

        Returns
        -------
        Optional[Callable[[str], str]]
            The transform function, or ``None`` if not registered.
        """
        return self._transforms.get(format_qname)

    def apply_transform(
        self, format_qname: str, display_value: str
    ) -> tuple[str, Optional[str]]:
        """Apply a transform and return the result.

        Parameters
        ----------
        format_qname:
            The ``@format`` attribute value.
        display_value:
            The human-readable display value to transform.

        Returns
        -------
        tuple[str, Optional[str]]
            ``(transformed_value, error_message_or_None)``.
            If the transform is unknown or fails, returns the
            original *display_value* and an error message.
        """
        fn = self._transforms.get(format_qname)
        if fn is None:
            return display_value, f"Unknown transform: {format_qname}"

        try:
            result = fn(display_value)
            return result, None
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Transform %s failed for value %r: %s",
                format_qname, display_value, exc,
            )
            return display_value, f"Transform {format_qname} failed: {exc}"

    def register(
        self, format_qname: str, fn: Callable[[str], str]
    ) -> None:
        """Register a custom transform function.

        Parameters
        ----------
        format_qname:
            The format QName to register.
        fn:
            A callable that takes a display string and returns the
            XBRL-canonical string.
        """
        self._transforms[format_qname] = fn

    @property
    def registered_formats(self) -> list[str]:
        """Return a sorted list of all registered format QNames."""
        return sorted(self._transforms.keys())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _register_builtins(self) -> None:
        """Register all built-in iXBRL transforms."""
        builtins: dict[str, Callable[[str], str]] = {
            # Numeric
            "ixt:numdotdecimal": _ixt_numdotdecimal,
            "ixt:numcommadecimal": _ixt_numcommadecimal,
            # Zero/nil
            "ixt:zerodash": _ixt_zerodash,
            "ixt:nocontent": _ixt_nocontent,
            "ixt:fixedzero": _ixt_fixedzero,
            # Boolean
            "ixt:booleanfalse": _ixt_booleanfalse,
            "ixt:booleantrue": _ixt_booleantrue,
            # Dates
            "ixt:dateslashus": _ixt_dateslashus,
            "ixt:dateslasheu": _ixt_dateslasheu,
            "ixt:datedoteu": _ixt_datedoteu,
            "ixt:datelongus": _ixt_datelongus,
            "ixt:datelonguk": _ixt_datelonguk,
            # Durations
            "ixt:durday": _ixt_durday,
            "ixt:durmonth": _ixt_durmonth,
            "ixt:duryear": _ixt_duryear,
            # SEC extensions
            "ixt-sec:duryear": _ixt_sec_duryear,
            "ixt-sec:durmonth": _ixt_sec_durmonth,
            "ixt-sec:numwordsen": _ixt_sec_numwordsen,
        }
        self._transforms.update(builtins)

    def _load_from_json(self, path: str) -> None:
        """Load additional transforms from a JSON configuration file.

        The JSON file should be an object mapping format QNames to
        transform specifications. Currently supports simple regex-based
        transforms with ``pattern`` and ``replacement`` fields.
        """
        try:
            file_path = Path(path)
            if not file_path.exists():
                logger.warning("Transform registry file not found: %s", path)
                return

            with file_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)

            for qname, spec in data.items():
                if isinstance(spec, dict) and "pattern" in spec and "replacement" in spec:
                    pattern = re.compile(spec["pattern"])
                    replacement = spec["replacement"]
                    self._transforms[qname] = (
                        lambda v, p=pattern, r=replacement: p.sub(r, v.strip())
                    )
                    logger.debug("Loaded regex transform: %s", qname)

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to load transform registry from %s: %s", path, exc
            )
