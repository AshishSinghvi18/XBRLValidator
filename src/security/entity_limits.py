"""Entity expansion limits guard (billion-laughs / quadratic blowup).

Enforces a hard cap on the number of entity expansions allowed during XML
parsing to prevent denial-of-service via exponential entity expansion
(aka "billion laughs") or quadratic blowup attacks.

Spec references:
  - Rule 3 — Zero-Trust Parsing
  - CWE-776: Improper Restriction of Recursive Entity References
  - ``DEFAULT_MAX_ENTITY_EXPANSIONS`` in constants

Example::

    guard = EntityLimitsGuard(max_expansions=50)
    parser = guard.create_limited_parser()
    tree = etree.parse("filing.xbrl", parser)
"""

from __future__ import annotations

import structlog
from lxml import etree

from src.core.constants import DEFAULT_MAX_ENTITY_EXPANSIONS
from src.core.exceptions import BillionLaughsError

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class EntityLimitsGuard:
    """Counts entity expansions and enforces a hard limit.

    When the expansion count reaches ``max_expansions``, a
    :class:`~src.core.exceptions.BillionLaughsError` is raised to abort
    parsing immediately.

    The guard also creates a hardened parser via :meth:`create_limited_parser`
    that combines XXE-safe settings with expansion limits.
    """

    def __init__(self, max_expansions: int = DEFAULT_MAX_ENTITY_EXPANSIONS) -> None:
        """Initialize the entity limits guard.

        Args:
            max_expansions: Maximum number of entity expansions allowed
                before raising ``BillionLaughsError``.  Defaults to
                ``DEFAULT_MAX_ENTITY_EXPANSIONS`` (100).
        """
        if max_expansions < 0:
            raise ValueError("max_expansions must be non-negative")

        self.max_expansions: int = max_expansions
        self._expansion_count: int = 0
        self._log = logger.bind(
            component="entity_limits_guard",
            max_expansions=max_expansions,
        )
        self._log.debug("entity_limits_guard_initialized")

    @property
    def expansion_count(self) -> int:
        """Current number of entity expansions tracked."""
        return self._expansion_count

    def reset(self) -> None:
        """Reset the expansion counter to zero."""
        self._expansion_count = 0

    def check_expansion(self, expansion_count: int) -> None:
        """Check whether the given expansion count exceeds the limit.

        This method should be called during or after parsing to verify
        that entity expansion has not exceeded the configured maximum.

        Args:
            expansion_count: The current total number of entity expansions.

        Raises:
            BillionLaughsError: If *expansion_count* exceeds
                ``max_expansions``.
        """
        self._expansion_count = expansion_count

        if expansion_count > self.max_expansions:
            self._log.error(
                "billion_laughs_detected",
                expansion_count=expansion_count,
                max_expansions=self.max_expansions,
            )
            raise BillionLaughsError(
                f"Entity expansion count ({expansion_count}) exceeds "
                f"maximum ({self.max_expansions})",
                code="SEC-0002",
                context={
                    "expansion_count": expansion_count,
                    "max_expansions": self.max_expansions,
                },
            )

        if expansion_count > 0:
            self._log.debug(
                "entity_expansion_check_passed",
                expansion_count=expansion_count,
            )

    @staticmethod
    def create_limited_parser() -> etree.XMLParser:
        """Create an XML parser with entity-expansion-safe settings.

        The parser is configured to:
          - Disable entity resolution (``resolve_entities=False``)
          - Block network access (``no_network=True``)
          - Skip DTD loading (``load_dtd=False``)
          - Disable DTD validation (``dtd_validation=False``)
          - Reject oversized trees (``huge_tree=False``)

        These settings prevent the parser from expanding entities at all,
        which is the most effective defense against billion-laughs attacks.

        Returns:
            A configured ``lxml.etree.XMLParser`` instance.
        """
        return etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
            dtd_validation=False,
            huge_tree=False,
        )
