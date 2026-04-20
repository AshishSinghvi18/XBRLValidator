"""XBRL model dataclasses and builders.

Provides the core data model for XBRL instances: facts, contexts, units,
taxonomy concepts, linkbases, and the top-level XBRLInstance container.
"""

from __future__ import annotations

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
    LinkbaseRef,
    Period,
    SchemaRef,
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
    "LinkbaseRef",
    "Period",
    "SchemaRef",
    "TaxonomyModel",
    "Unit",
    "UnitMeasure",
    "ValidationMessage",
    "XBRLInstance",
]
