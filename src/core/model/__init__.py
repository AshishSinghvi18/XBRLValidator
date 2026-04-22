"""XBRL core data-model package — XBRL 2.1 §4–§5.

Re-exports every public model class so callers can write::

    from src.core.model import Concept, Fact, Context, Unit, XBRLInstance

References:
    - XBRL 2.1 §4 (instance model)
    - XBRL 2.1 §5 (taxonomy model)
"""

from __future__ import annotations

from src.core.model.concept import Concept
from src.core.model.context import Context, Entity, ExplicitDimension, Period, TypedDimension
from src.core.model.fact import Fact
from src.core.model.instance import ValidationMessage, XBRLInstance
from src.core.model.unit import Unit

__all__: list[str] = [
    "Concept",
    "Context",
    "Entity",
    "ExplicitDimension",
    "Fact",
    "Period",
    "TypedDimension",
    "Unit",
    "ValidationMessage",
    "XBRLInstance",
]
