"""XBRL instance model and builders.

Provides:
- Core dataclasses: :class:`XBRLInstance`, :class:`Fact`, :class:`Context`, etc.
- :class:`ModelBuilder` – DOM-based model builder
- :class:`StreamingModelBuilder` – streaming/store-backed model builder
- :class:`ModelMerger` – multi-document merger
- :class:`ModelIndexes` – secondary query indexes
"""

from src.core.model.xbrl_model import (
    ArcModel,
    ConceptDefinition,
    Context,
    DimensionMember,
    EntityIdentifier,
    Fact,
    Footnote,
    HypercubeModel,
    LinkbaseModel,
    Period,
    TaxonomyModel,
    Unit,
    UnitMeasure,
    ValidationMessage,
    XBRLInstance,
)

__all__ = [
    "ArcModel",
    "ConceptDefinition",
    "Context",
    "DimensionMember",
    "EntityIdentifier",
    "Fact",
    "Footnote",
    "HypercubeModel",
    "LinkbaseModel",
    "Period",
    "TaxonomyModel",
    "Unit",
    "UnitMeasure",
    "ValidationMessage",
    "XBRLInstance",
]
