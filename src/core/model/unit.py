"""XBRL unit element — XBRL 2.1 §4.8.

A :class:`Unit` captures the numerator and (optional) denominator
measures declared in an ``<xbrli:unit>`` element.  Measures are stored
as Clark-notation QNames.

References:
    - XBRL 2.1 §4.8   (unit element)
    - XBRL 2.1 §4.8.2 (monetary items & ISO 4217)
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.constants import NS_ISO4217, NS_XBRLI


@dataclass(frozen=True, slots=True)
class Unit:
    """XBRL unit declaration — XBRL 2.1 §4.8.

    Attributes:
        unit_id: The ``id`` attribute of the ``<xbrli:unit>`` element
            (serves as :pydata:`src.core.types.UnitID`).
        numerators: Tuple of Clark-notation QNames for the numerator
            measures (e.g. ``("{http://www.xbrl.org/2003/iso4217}USD",)``).
        denominators: Tuple of Clark-notation QNames for the denominator
            measures.  Empty for simple (non-divide) units.
    """

    unit_id: str
    numerators: tuple[str, ...]
    denominators: tuple[str, ...] = ()

    @property
    def is_monetary(self) -> bool:
        """Return ``True`` if this is a single-measure ISO 4217 currency unit.

        A monetary unit has exactly one numerator whose namespace is the
        ISO 4217 namespace and no denominators — XBRL 2.1 §4.8.2.

        Returns:
            ``True`` for monetary units, ``False`` otherwise.

        References:
            - XBRL 2.1 §4.8.2
        """
        if len(self.numerators) != 1 or self.denominators:
            return False
        qn = self.numerators[0]
        return qn.startswith(f"{{{NS_ISO4217}}}")

    @property
    def is_pure(self) -> bool:
        """Return ``True`` if this unit is ``xbrli:pure``.

        Returns:
            ``True`` when the sole numerator is
            ``{http://www.xbrl.org/2003/instance}pure`` and there are
            no denominators.

        References:
            - XBRL 2.1 §4.8.2
        """
        return (
            len(self.numerators) == 1
            and not self.denominators
            and self.numerators[0] == f"{{{NS_XBRLI}}}pure"
        )

    @property
    def is_divide(self) -> bool:
        """Return ``True`` if this is a divide unit (has denominators).

        Returns:
            ``True`` when one or more denominator measures are present.

        References:
            - XBRL 2.1 §4.8.1
        """
        return len(self.denominators) > 0
