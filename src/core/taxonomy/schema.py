"""Taxonomy schema — XBRL 2.1 §5.1, §5.2.

Data-classes representing a loaded taxonomy schema document, its roleType
and arcroleType definitions, and all concept declarations.

References:
    - XBRL 2.1 §5.1   (Schema Files)
    - XBRL 2.1 §5.1.3 (roleType)
    - XBRL 2.1 §5.1.4 (arcroleType)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.model.concept import Concept


@dataclass
class RoleType:
    """A roleType definition — XBRL 2.1 §5.1.3.

    Attributes:
        role_uri:   The unique role URI identifier.
        definition: Human-readable description of the role.
        used_on:    Clark-notation QNames of elements this role may appear on
                    (e.g. ``{http://www.xbrl.org/2003/linkbase}presentationLink``).
    """

    role_uri: str
    definition: str
    used_on: list[str] = field(default_factory=list)


@dataclass
class ArcroleType:
    """An arcroleType definition — XBRL 2.1 §5.1.4.

    Attributes:
        arcrole_uri:    The unique arcrole URI identifier.
        definition:     Human-readable description of the arcrole.
        used_on:        Clark-notation QNames of arc elements it may appear on.
        cycles_allowed: Cycle constraint — ``"any"``, ``"undirected"``,
                        or ``"none"`` per XBRL 2.1 §5.1.4.
    """

    arcrole_uri: str
    definition: str
    used_on: list[str] = field(default_factory=list)
    cycles_allowed: str = "none"


@dataclass
class TaxonomySchema:
    """Represents a loaded taxonomy schema document.

    Spec: XBRL 2.1 §5 (Taxonomy Structure)

    Attributes:
        url:              Resolved absolute URL / path of the schema file.
        target_namespace: The ``targetNamespace`` of the XSD document.
        concepts:         Clark QName → :class:`Concept` mapping.
        imported_schemas: URLs of ``xs:import``-ed schema documents.
        linkbase_refs:    URLs of referenced linkbase documents
                          (from ``link:linkbaseRef``).
        role_types:       roleURI → :class:`RoleType` mapping.
        arcrole_types:    arcroleURI → :class:`ArcroleType` mapping.
    """

    url: str
    target_namespace: str
    concepts: dict[str, Concept] = field(default_factory=dict)
    imported_schemas: list[str] = field(default_factory=list)
    linkbase_refs: list[str] = field(default_factory=list)
    role_types: dict[str, RoleType] = field(default_factory=dict)
    arcrole_types: dict[str, ArcroleType] = field(default_factory=dict)
