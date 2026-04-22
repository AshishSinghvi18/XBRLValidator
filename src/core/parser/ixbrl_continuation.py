"""Inline XBRL continuation element resolver.

Implements the ix:continuation chain-following algorithm defined in the
Inline XBRL specification.  Continuation elements allow a single XBRL fact
to span multiple non-contiguous locations in an HTML document.  This module
reassembles those fragments into a single resolved text value per fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.exceptions import IXBRLParseError


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ContinuationFact:
    """A fact element that may have one or more continuation fragments.

    Attributes:
        fact_id: The ``id`` attribute of the fact element.
        initial_value: The text value contained directly in the fact element
            (before any continuation content is appended).
        continuation_ids: Ordered list of ``continuationAt`` identifiers
            originating from the fact element and any chained continuations.
    """

    fact_id: str
    initial_value: str
    continuation_ids: list[str] = field(default_factory=list)


@dataclass
class ContinuationFragment:
    """A single ``ix:continuation`` element.

    Attributes:
        fragment_id: The ``id`` attribute of the continuation element.
        value: The text content carried by this fragment.
        continuation_at: Optional ``continuationAt`` attribute pointing to
            the next fragment in the chain, or ``None`` if this is the
            terminal fragment.
    """

    fragment_id: str
    value: str
    continuation_at: str | None = None


@dataclass
class ResolvedFact:
    """The result of assembling a fact with all of its continuations.

    Attributes:
        fact_id: The ``id`` of the originating fact element.
        resolved_value: Fully assembled text after all continuation
            fragments have been concatenated.
        fragment_count: Total number of text segments including the
            initial fact value.
        warnings: Human-readable warnings encountered during resolution
            (e.g. broken chains).
    """

    fact_id: str
    resolved_value: str
    fragment_count: int
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class ContinuationResolver:
    """Resolves ``ix:continuation`` chains for Inline XBRL facts.

    Parameters:
        max_chain_depth: Maximum number of continuation hops allowed before
            the resolver raises an error.  This guards against malformed
            documents that would otherwise cause unbounded recursion.
    """

    def __init__(self, max_chain_depth: int = 1000) -> None:
        self._max_chain_depth = max_chain_depth

    # -- public API ---------------------------------------------------------

    def resolve(
        self,
        facts: list[ContinuationFact],
        continuations: list[ContinuationFragment],
    ) -> list[ResolvedFact]:
        """Assemble each fact's full text by following continuation chains.

        Args:
            facts: Fact elements that may reference continuation fragments.
            continuations: All ``ix:continuation`` elements present in the
                document.

        Returns:
            A list of :class:`ResolvedFact` instances – one per input fact,
            in the same order.

        Raises:
            IXBRLParseError: On circular references (``IXBRL-0003``) or
                when the chain depth exceeds *max_chain_depth*
                (``IXBRL-0004``).
        """
        fragments = self._build_lookup(continuations)
        results: list[ResolvedFact] = []

        for fact in facts:
            values: list[str] = [fact.initial_value]
            warnings: list[str] = []

            for cont_id in fact.continuation_ids:
                chain_values, chain_warnings = self._follow_chain(
                    cont_id, fragments, fact.fact_id
                )
                values.extend(chain_values)
                warnings.extend(chain_warnings)

            results.append(
                ResolvedFact(
                    fact_id=fact.fact_id,
                    resolved_value="".join(values),
                    fragment_count=len(values),
                    warnings=warnings,
                )
            )

        return results

    def validate_continuations(
        self,
        facts: list[ContinuationFact],
        continuations: list[ContinuationFragment],
    ) -> list[str]:
        """Validate continuation structures without fully resolving facts.

        Checks performed:
        * Orphaned continuations – fragments not referenced by any fact or
          by another fragment's ``continuationAt``.
        * Broken chains – a ``continuationAt`` that points to a
          non-existent fragment.
        * Circular references – a chain that loops back on itself.

        Returns:
            A list of human-readable diagnostic messages.  An empty list
            indicates a clean document.
        """
        fragments = self._build_lookup(continuations)
        messages: list[str] = []

        # Collect all fragment IDs that are actually referenced.
        referenced_ids: set[str] = set()
        for fact in facts:
            for cont_id in fact.continuation_ids:
                referenced_ids.add(cont_id)
        for frag in continuations:
            if frag.continuation_at is not None:
                referenced_ids.add(frag.continuation_at)

        # Orphaned continuations
        all_fragment_ids = set(fragments.keys())
        orphaned = all_fragment_ids - referenced_ids
        for oid in sorted(orphaned):
            messages.append(
                f"Orphaned continuation: fragment '{oid}' is not referenced "
                f"by any fact or continuation chain."
            )

        # Walk each fact's chains to find broken / circular issues.
        for fact in facts:
            for cont_id in fact.continuation_ids:
                try:
                    _, chain_warnings = self._follow_chain(
                        cont_id, fragments, fact.fact_id
                    )
                    messages.extend(chain_warnings)
                except IXBRLParseError as exc:
                    messages.append(f"[{exc.code}] {exc.message}")

        return messages

    # -- private helpers ----------------------------------------------------

    def _follow_chain(
        self,
        start_continuation_at: str | None,
        fragments: dict[str, ContinuationFragment],
        fact_id: str,
    ) -> tuple[list[str], list[str]]:
        """Follow a single continuation chain starting from *start_continuation_at*.

        Args:
            start_continuation_at: The first ``continuationAt`` identifier
                to look up.  If ``None`` the chain is empty.
            fragments: Lookup dictionary mapping fragment IDs to their
                :class:`ContinuationFragment` objects.
            fact_id: The originating fact's ``id``, used for error messages.

        Returns:
            A two-element tuple of ``(values, warnings)`` where *values* is
            an ordered list of text segments and *warnings* contains any
            non-fatal messages produced during traversal.

        Raises:
            IXBRLParseError: ``IXBRL-0003`` for circular references,
                ``IXBRL-0004`` if the chain exceeds *max_chain_depth*.
        """
        values: list[str] = []
        warnings: list[str] = []
        visited: set[str] = set()
        current: str | None = start_continuation_at
        depth = 0

        while current is not None:
            # Depth guard
            if depth >= self._max_chain_depth:
                raise IXBRLParseError(
                    code="IXBRL-0004",
                    message=(
                        f"Continuation chain for fact '{fact_id}' exceeds "
                        f"the maximum allowed depth of {self._max_chain_depth}."
                    ),
                    context={"fact_id": fact_id, "depth": depth},
                )

            # Circular-reference guard
            if current in visited:
                raise IXBRLParseError(
                    code="IXBRL-0003",
                    message=(
                        f"Circular continuation reference detected for "
                        f"fact '{fact_id}': fragment '{current}' was "
                        f"already visited."
                    ),
                    context={
                        "fact_id": fact_id,
                        "fragment_id": current,
                        "visited": sorted(visited),
                    },
                )

            visited.add(current)

            # Missing fragment
            fragment = fragments.get(current)
            if fragment is None:
                warnings.append(
                    f"IXBRL-0002: Broken continuation chain for fact "
                    f"'{fact_id}': fragment '{current}' not found."
                )
                break

            values.append(fragment.value)
            current = fragment.continuation_at
            depth += 1

        return values, warnings

    # -- static helpers -----------------------------------------------------

    @staticmethod
    def _build_lookup(
        continuations: list[ContinuationFragment],
    ) -> dict[str, ContinuationFragment]:
        """Create a dict mapping fragment IDs to their objects."""
        return {frag.fragment_id: frag for frag in continuations}
