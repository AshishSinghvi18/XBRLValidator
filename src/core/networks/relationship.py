"""XBRL relationship network — XBRL 2.1 §5.2.

Handles linkbase arcs and relationship graphs for calculation, presentation,
definition, label, and reference linkbases.

The :class:`RelationshipNetwork` implements arc prohibition and overriding
per XBRL 2.1 §3.5.3.9.3 (prohibition) and §3.5.3.9.4 (overriding).

References:
    - XBRL 2.1 §3.5.3.9   (Arc element)
    - XBRL 2.1 §3.5.3.9.3 (Prohibition)
    - XBRL 2.1 §3.5.3.9.4 (Overriding)
    - XBRL 2.1 §5.2       (Linkbases)
    - XBRL 2.1 §5.2.5.2   (Calculation linkbase validation)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class Arc:
    """A single arc in a linkbase — XBRL 2.1 §3.5.3.9.

    Attributes:
        from_qname: Clark QName of the source concept.
        to_qname:   Clark QName of the target concept.
        arcrole:    Arcrole URI identifying the relationship type.
        role:       Extended link role URI.
        order:      Ordering attribute for sibling arcs.
        weight:     Weight attribute for calculation arcs (``None`` for
                    non-calculation arcs).
        priority:   Priority for arc overriding — XBRL 2.1 §3.5.3.9.4.
        use:        ``"optional"`` or ``"prohibited"`` — XBRL 2.1 §3.5.3.9.3.
    """

    from_qname: str
    to_qname: str
    arcrole: str
    role: str
    order: Decimal
    weight: Decimal | None
    priority: int
    use: str


class RelationshipNetwork:
    """Directed graph of XBRL relationships for a specific arcrole.

    Supports arc prohibition and overriding per XBRL 2.1 §3.5.3.9.3
    and §3.5.3.9.4.  Call :meth:`resolve_prohibitions` after adding all
    arcs to apply these rules.

    Args:
        arcrole: The arcrole URI this network is scoped to.
    """

    def __init__(self, arcrole: str) -> None:
        self._arcrole: str = arcrole
        self._arcs: list[Arc] = []
        self._children: dict[str, list[Arc]] = defaultdict(list)
        self._parents: dict[str, list[Arc]] = defaultdict(list)
        self._resolved: bool = False

    @property
    def arcrole(self) -> str:
        """Return the arcrole URI of this network."""
        return self._arcrole

    @property
    def arc_count(self) -> int:
        """Return the number of effective arcs in the network."""
        return len(self._arcs)

    def add_arc(self, arc: Arc) -> None:
        """Add an arc to the network.

        The arc's arcrole must match this network's arcrole.

        Args:
            arc: The :class:`Arc` to add.

        Raises:
            ValueError: If the arc's arcrole does not match.
        """
        if arc.arcrole != self._arcrole:
            raise ValueError(
                f"Arc arcrole {arc.arcrole!r} does not match "
                f"network arcrole {self._arcrole!r}"
            )
        self._arcs.append(arc)
        self._resolved = False

    def resolve_prohibitions(self) -> None:
        """Apply prohibition and override rules to the arc set.

        Per XBRL 2.1 §3.5.3.9.3, an arc with ``use="prohibited"``
        nullifies all equivalent arcs (same from/to/arcrole/role) with
        equal or lower priority.

        Per §3.5.3.9.4, among non-prohibited arcs with the same
        equivalence key, only those with the highest priority survive.
        """
        if self._resolved:
            return

        # Group arcs by their equivalence key: (from, to, arcrole, role)
        groups: dict[tuple[str, str, str, str], list[Arc]] = defaultdict(list)
        for arc in self._arcs:
            key = (arc.from_qname, arc.to_qname, arc.arcrole, arc.role)
            groups[key].append(arc)

        effective: list[Arc] = []
        for arcs_in_group in groups.values():
            max_priority = max(a.priority for a in arcs_in_group)
            highest = [a for a in arcs_in_group if a.priority == max_priority]

            # If any highest-priority arc is prohibited, the entire
            # equivalence group is nullified
            if any(a.use == "prohibited" for a in highest):
                continue

            effective.extend(highest)

        # Rebuild indexes
        self._arcs = effective
        self._children = defaultdict(list)
        self._parents = defaultdict(list)
        for arc in effective:
            self._children[arc.from_qname].append(arc)
            self._parents[arc.to_qname].append(arc)

        # Sort children by order for deterministic traversal
        for arcs_list in self._children.values():
            arcs_list.sort(key=lambda a: a.order)

        self._resolved = True

    def _ensure_resolved(self) -> None:
        """Ensure prohibitions have been resolved before querying."""
        if not self._resolved:
            self.resolve_prohibitions()

    def children(self, qname: str, role: str = "") -> list[Arc]:
        """Return child arcs for a concept.

        Args:
            qname: Clark QName of the parent concept.
            role:  Optional role URI filter.  When empty, returns arcs
                   for all roles.

        Returns:
            List of :class:`Arc` objects ordered by ``order`` attribute.
        """
        self._ensure_resolved()
        arcs = self._children.get(qname, [])
        if role:
            arcs = [a for a in arcs if a.role == role]
        return arcs

    def parents(self, qname: str, role: str = "") -> list[Arc]:
        """Return parent arcs for a concept.

        Args:
            qname: Clark QName of the child concept.
            role:  Optional role URI filter.

        Returns:
            List of :class:`Arc` objects.
        """
        self._ensure_resolved()
        arcs = self._parents.get(qname, [])
        if role:
            arcs = [a for a in arcs if a.role == role]
        return arcs

    def roots(self, role: str = "") -> list[str]:
        """Return root concepts (concepts that appear as ``from`` but not ``to``).

        Args:
            role: Optional role URI filter.

        Returns:
            Sorted list of Clark QName strings for root concepts.
        """
        self._ensure_resolved()

        from_qnames: set[str] = set()
        to_qnames: set[str] = set()
        for arc in self._arcs:
            if role and arc.role != role:
                continue
            from_qnames.add(arc.from_qname)
            to_qnames.add(arc.to_qname)

        return sorted(from_qnames - to_qnames)

    def tree(self, root: str, role: str = "") -> dict[str, Any]:
        """Build a nested tree structure starting from *root*.

        Args:
            root: Clark QName of the root concept.
            role: Optional role URI filter.

        Returns:
            Nested dict with keys ``"qname"``, ``"order"``, ``"weight"``,
            and ``"children"`` (recursive list of the same structure).
        """
        self._ensure_resolved()
        return self._build_tree(root, role, visited=set())

    def _build_tree(
        self,
        qname: str,
        role: str,
        visited: set[str],
    ) -> dict[str, Any]:
        """Recursively build a tree, guarding against cycles."""
        node: dict[str, Any] = {
            "qname": qname,
            "order": Decimal(0),
            "weight": None,
            "children": [],
        }

        if qname in visited:
            return node

        visited = visited | {qname}
        child_arcs = self.children(qname, role)

        for arc in child_arcs:
            child_tree = self._build_tree(arc.to_qname, role, visited)
            child_tree["order"] = arc.order
            child_tree["weight"] = arc.weight
            node["children"].append(child_tree)

        return node
