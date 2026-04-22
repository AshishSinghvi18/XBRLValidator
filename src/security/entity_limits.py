"""Entity expansion guard for billion-laughs attack prevention.

Tracks entity expansions during a parse operation and raises when the
configured limit is exceeded.
"""

from __future__ import annotations

from src.core.constants import DEFAULT_MAX_ENTITY_EXPANSION
from src.core.exceptions import BillionLaughsError


class EntityExpansionGuard:
    """Tracks XML entity expansions and enforces a configurable ceiling.

    Usage::

        guard = EntityExpansionGuard()
        for event in stream:
            if is_entity_expansion(event):
                guard.record_expansion()
        # After parsing a document, reset for the next one:
        guard.reset()

    Args:
        max_expansions: Upper bound on the number of entity expansions
            allowed per parse operation.  Defaults to
            :data:`~src.core.constants.DEFAULT_MAX_ENTITY_EXPANSION`.
    """

    def __init__(
        self,
        max_expansions: int = DEFAULT_MAX_ENTITY_EXPANSION,
    ) -> None:
        if max_expansions < 0:
            raise ValueError("max_expansions must be non-negative")
        self._max_expansions = max_expansions
        self._count: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset the expansion counter to zero.

        Call this at the start of each new parse operation.
        """
        self._count = 0

    def record_expansion(self) -> None:
        """Record a single entity expansion event.

        Raises:
            BillionLaughsError: If the expansion count exceeds the
                configured limit.
        """
        self._count += 1
        if self._count > self._max_expansions:
            raise BillionLaughsError(
                message=(
                    f"Entity expansion limit exceeded: "
                    f"{self._count} expansions "
                    f"(limit: {self._max_expansions})"
                ),
                context={
                    "expansion_count": self._count,
                    "limit": self._max_expansions,
                },
            )

    @property
    def count(self) -> int:
        """Current number of recorded entity expansions."""
        return self._count
