"""iXBRL Transformation Registry.

Provides a registry of inline XBRL transformation functions that convert
human-readable formatted values into canonical XBRL fact values.
"""

from __future__ import annotations

import calendar
import re
from typing import Callable

from src.core.constants import NS_IXT_PREFIX

# ---------------------------------------------------------------------------
# Month-name lookup tables
# ---------------------------------------------------------------------------

_MONTH_FULL: dict[str, str] = {
    name.lower(): f"{idx:02d}" for idx, name in enumerate(calendar.month_name) if name
}

_MONTH_ABBR: dict[str, str] = {
    name.lower(): f"{idx:02d}" for idx, name in enumerate(calendar.month_abbr) if name
}

# Combine both for flexible matching
_MONTH_LOOKUP: dict[str, str] = {**_MONTH_FULL, **_MONTH_ABBR}

# ---------------------------------------------------------------------------
# Individual transform implementations
# ---------------------------------------------------------------------------

_CLARK_RE = re.compile(r"^\{(.+)\}(.+)$")


def _boolean_false(_v: str) -> str:
    return "false"


def _boolean_true(_v: str) -> str:
    return "true"


def _numdotdecimal(v: str) -> str:
    """Remove commas (thousands separators) from a dot-decimal number."""
    v = v.strip()
    return v.replace(",", "").replace(" ", "")


def _numcommadecimal(v: str) -> str:
    """Convert European-style number (dot=thousands, comma=decimal) to canonical."""
    v = v.strip()
    v = v.replace(" ", "").replace(".", "").replace(",", ".")
    return v


def _zerodash(_v: str) -> str:
    return "0"


def _nocontent(_v: str) -> str:
    return ""


def _fixedzero(_v: str) -> str:
    return "0"


def _fixedempty(_v: str) -> str:
    return ""


def _identity(v: str) -> str:
    return v


# ---------------------------------------------------------------------------
# Date transforms
# ---------------------------------------------------------------------------

def _dateslashus(v: str) -> str:
    """MM/DD/YYYY -> YYYY-MM-DD"""
    v = v.strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", v)
    if not m:
        return v
    month, day, year = m.group(1), m.group(2), m.group(3)
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _dateslasheu(v: str) -> str:
    """DD/MM/YYYY -> YYYY-MM-DD"""
    v = v.strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", v)
    if not m:
        return v
    day, month, year = m.group(1), m.group(2), m.group(3)
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _datedotus(v: str) -> str:
    """MM.DD.YYYY -> YYYY-MM-DD"""
    v = v.strip()
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", v)
    if not m:
        return v
    month, day, year = m.group(1), m.group(2), m.group(3)
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _datedoteu(v: str) -> str:
    """DD.MM.YYYY -> YYYY-MM-DD"""
    v = v.strip()
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", v)
    if not m:
        return v
    day, month, year = m.group(1), m.group(2), m.group(3)
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _datelongus(v: str) -> str:
    """'January 1, 2024' -> '2024-01-01'"""
    v = v.strip()
    m = re.match(
        r"^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})$", v
    )
    if not m:
        return v
    month_str = m.group(1).lower()
    day = int(m.group(2))
    year = m.group(3)
    month_num = _MONTH_LOOKUP.get(month_str)
    if month_num is None:
        return v
    return f"{year}-{month_num}-{day:02d}"


def _datelonguk(v: str) -> str:
    """'1 January 2024' -> '2024-01-01'"""
    v = v.strip()
    m = re.match(
        r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$", v
    )
    if not m:
        return v
    day = int(m.group(1))
    month_str = m.group(2).lower()
    year = m.group(3)
    month_num = _MONTH_LOOKUP.get(month_str)
    if month_num is None:
        return v
    return f"{year}-{month_num}-{day:02d}"


def _dateshortus(v: str) -> str:
    """'Jan 1, 2024' -> '2024-01-01'"""
    v = v.strip()
    m = re.match(
        r"^([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})$", v
    )
    if not m:
        return v
    month_str = m.group(1).lower().rstrip(".")
    day = int(m.group(2))
    year = m.group(3)
    month_num = _MONTH_LOOKUP.get(month_str)
    if month_num is None:
        return v
    return f"{year}-{month_num}-{day:02d}"


def _dateshortuk(v: str) -> str:
    """'1 Jan 2024' -> '2024-01-01'"""
    v = v.strip()
    m = re.match(
        r"^(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})$", v
    )
    if not m:
        return v
    day = int(m.group(1))
    month_str = m.group(2).lower().rstrip(".")
    year = m.group(3)
    month_num = _MONTH_LOOKUP.get(month_str)
    if month_num is None:
        return v
    return f"{year}-{month_num}-{day:02d}"


# ---------------------------------------------------------------------------
# Duration transforms
# ---------------------------------------------------------------------------

def _durday(v: str) -> str:
    """Convert display days to xsd:duration PnD format (e.g. '30' -> 'P30D')."""
    v = v.strip()
    m = re.match(r"^(\d+)\s*(?:days?)?$", v, re.IGNORECASE)
    if not m:
        return v
    return f"P{m.group(1)}D"


def _durmonth(v: str) -> str:
    """Convert display months to xsd:duration PnM format (e.g. '6' -> 'P6M')."""
    v = v.strip()
    m = re.match(r"^(\d+)\s*(?:months?)?$", v, re.IGNORECASE)
    if not m:
        return v
    return f"P{m.group(1)}M"


def _duryear(v: str) -> str:
    """Convert display years to xsd:duration PnY format (e.g. '3' -> 'P3Y')."""
    v = v.strip()
    m = re.match(r"^(\d+)\s*(?:years?)?$", v, re.IGNORECASE)
    if not m:
        return v
    return f"P{m.group(1)}Y"


# ---------------------------------------------------------------------------
# SEC-specific transforms
# ---------------------------------------------------------------------------

_BALLOT_TRUE = {"\u2611", "\u2612", "☑", "☒"}
_BALLOT_FALSE = {"\u2610", "☐"}


def _boolballotbox(v: str) -> str:
    """Convert ballot-box characters to 'true'/'false'."""
    v = v.strip()
    if v in _BALLOT_TRUE:
        return "true"
    if v in _BALLOT_FALSE:
        return "false"
    return v


_QUARTER_END: dict[str, str] = {
    "1": ("03", "31"),
    "2": ("06", "30"),
    "3": ("09", "30"),
    "4": ("12", "31"),
}


def _datequarterend(v: str) -> str:
    """Convert 'Q1 2024' (or similar) to quarter-end date '2024-03-31'."""
    v = v.strip()
    m = re.match(r"^[Qq](\d)\s+(\d{4})$", v)
    if not m:
        return v
    quarter = m.group(1)
    year = m.group(2)
    end = _QUARTER_END.get(quarter)
    if end is None:
        return v
    return f"{year}-{end[0]}-{end[1]}"


# ---------------------------------------------------------------------------
# Standard transform sets
# ---------------------------------------------------------------------------

_IXT_COMMON: dict[str, Callable[[str], str]] = {
    "booleanfalse": _boolean_false,
    "booleantrue": _boolean_true,
    "numdotdecimal": _numdotdecimal,
    "numcommadecimal": _numcommadecimal,
    "zerodash": _zerodash,
    "nocontent": _nocontent,
    "fixedzero": _fixedzero,
    "fixedempty": _fixedempty,
    "numwordsen": _identity,
    "dateslashus": _dateslashus,
    "dateslasheu": _dateslasheu,
    "datedotus": _datedotus,
    "datedoteu": _datedoteu,
    "datelongus": _datelongus,
    "datelonguk": _datelonguk,
    "dateshortus": _dateshortus,
    "dateshortuk": _dateshortuk,
    "durday": _durday,
    "durmonth": _durmonth,
    "duryear": _duryear,
}

_IXT_SEC: dict[str, Callable[[str], str]] = {
    "duryear": _duryear,
    "durmonth": _durmonth,
    "durwordsen": _identity,
    "numwordsen": _identity,
    "boolballotbox": _boolballotbox,
    "datequarterend": _datequarterend,
}


# ---------------------------------------------------------------------------
# Registry class
# ---------------------------------------------------------------------------

class TransformRegistry:
    """Registry for iXBRL transformation functions.

    Maintains a mapping of namespace URI -> {transform_name -> callable} and
    provides look-up by Clark-notation QName ``{namespace}localName``.
    """

    def __init__(self) -> None:
        self._transforms: dict[str, dict[str, Callable[[str], str]]] = {}
        self._load_standard_transforms()

    # -- public API ---------------------------------------------------------

    def register(
        self, namespace: str, transforms: dict[str, Callable[[str], str]]
    ) -> None:
        """Register a dict of ``{name: callable}`` under *namespace*.

        Merges with any transforms already registered for that namespace.
        """
        if namespace not in self._transforms:
            self._transforms[namespace] = {}
        self._transforms[namespace].update(transforms)

    def get_transform(self, qname: str) -> Callable[[str], str] | None:
        """Return the transform callable for a Clark-notation *qname*.

        *qname* must be in the form ``{namespace}localName``.
        Returns ``None`` if the transform is not registered.
        """
        namespace, local_name = self._parse_clark(qname)
        if namespace is None:
            return None
        ns_transforms = self._transforms.get(namespace)
        if ns_transforms is None:
            return None
        return ns_transforms.get(local_name)

    def is_registered(self, qname: str) -> bool:
        """Return ``True`` if *qname* (Clark notation) is registered."""
        return self.get_transform(qname) is not None

    def list_namespaces(self) -> list[str]:
        """Return a list of all registered namespace URIs."""
        return list(self._transforms.keys())

    def list_transforms(self, namespace: str) -> list[str]:
        """Return a list of transform names registered under *namespace*."""
        return list(self._transforms.get(namespace, {}).keys())

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _parse_clark(qname: str) -> tuple[str | None, str | None]:
        """Parse ``{namespace}localName`` into ``(namespace, localName)``."""
        m = _CLARK_RE.match(qname)
        if m is None:
            return None, None
        return m.group(1), m.group(2)

    def _load_standard_transforms(self) -> None:
        """Pre-populate the registry with standard iXBRL transforms."""
        ixt_namespaces = [
            f"{NS_IXT_PREFIX}/2010-04-20",  # ixt (v1)
            f"{NS_IXT_PREFIX}/2011-07-31",  # ixt-2
            f"{NS_IXT_PREFIX}/2015-02-26",  # ixt-3
            f"{NS_IXT_PREFIX}/2020-02-12",  # ixt-4
            f"{NS_IXT_PREFIX}/2022-02-01",  # ixt-5
        ]
        for ns in ixt_namespaces:
            self.register(ns, dict(_IXT_COMMON))

        # SEC-specific transforms
        self.register(
            "http://www.sec.gov/inlineXBRL/transformation/2015-08-31",
            dict(_IXT_SEC),
        )
