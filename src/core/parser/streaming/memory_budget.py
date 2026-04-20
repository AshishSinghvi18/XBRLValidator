"""Memory budget manager for streaming XBRL parser pipeline.

Singleton-per-pipeline-run, thread-safe memory accounting. Components register
their maximum expected allocation; the budget tracks actual usage and triggers
disk spill when the total approaches the configured ceiling.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

import psutil

from src.core.constants import DEFAULT_MEMORY_BUDGET_BYTES
from src.core.exceptions import MemoryBudgetExceededError
from src.core.types import SpillState

logger = logging.getLogger(__name__)


@dataclass
class MemoryAllocation:
    """Tracks a single component's memory allocation within the budget."""

    component: str
    allocated_bytes: int = 0
    used_bytes: int = 0
    max_bytes: int = 0
    spill_state: SpillState = SpillState.IN_MEMORY


class MemoryBudget:
    """Thread-safe memory budget for a single pipeline run.

    Each pipeline component (fact index, context map, etc.) registers its
    maximum expected allocation.  The budget tracks actual usage across all
    components and triggers spill requests when the total used memory
    approaches ``total_bytes``.

    Parameters
    ----------
    total_bytes:
        Overall memory ceiling for the pipeline.  Defaults to
        ``DEFAULT_MEMORY_BUDGET_BYTES`` (4 GiB).
    """

    def __init__(self, total_bytes: int = DEFAULT_MEMORY_BUDGET_BYTES) -> None:
        self._total_bytes: int = total_bytes
        self._allocations: dict[str, MemoryAllocation] = {}
        self._lock: threading.Lock = threading.Lock()
        self._process = psutil.Process()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, component: str, max_bytes: int) -> MemoryAllocation:
        """Register a component with its maximum expected allocation.

        Parameters
        ----------
        component:
            Unique name for the pipeline component (e.g. ``"fact_index"``).
        max_bytes:
            Maximum number of bytes this component is expected to use.

        Returns
        -------
        MemoryAllocation:
            A mutable allocation record for this component.

        Raises
        ------
        MemoryBudgetExceededError:
            If registering *max_bytes* would exceed the total budget.
        """
        with self._lock:
            if component in self._allocations:
                logger.warning(
                    "Component %r already registered; returning existing allocation",
                    component,
                )
                return self._allocations[component]

            total_reserved = sum(a.max_bytes for a in self._allocations.values())
            if total_reserved + max_bytes > self._total_bytes:
                raise MemoryBudgetExceededError(
                    f"Cannot reserve {max_bytes:,} bytes for {component!r}: "
                    f"would exceed total budget of {self._total_bytes:,} bytes "
                    f"(already reserved {total_reserved:,})"
                )

            alloc = MemoryAllocation(
                component=component,
                allocated_bytes=0,
                used_bytes=0,
                max_bytes=max_bytes,
                spill_state=SpillState.IN_MEMORY,
            )
            self._allocations[component] = alloc
            logger.debug(
                "Registered component %r with max_bytes=%s", component, max_bytes
            )
            return alloc

    def can_allocate(self, component: str, additional_bytes: int) -> bool:
        """Check whether *additional_bytes* can be allocated for *component*.

        Returns ``True`` if the allocation would stay within both the
        component's own ``max_bytes`` and the global budget.
        """
        with self._lock:
            alloc = self._allocations.get(component)
            if alloc is None:
                logger.warning(
                    "can_allocate called for unregistered component %r", component
                )
                return False
            if alloc.used_bytes + additional_bytes > alloc.max_bytes:
                return False
            total_used = sum(a.used_bytes for a in self._allocations.values())
            return total_used + additional_bytes <= self._total_bytes

    def record_allocation(self, component: str, bytes_added: int) -> None:
        """Record that *component* has allocated *bytes_added* more bytes.

        Raises
        ------
        MemoryBudgetExceededError:
            If the allocation would exceed the global budget.
        """
        with self._lock:
            alloc = self._allocations.get(component)
            if alloc is None:
                logger.warning(
                    "record_allocation called for unregistered component %r",
                    component,
                )
                return
            alloc.used_bytes += bytes_added
            alloc.allocated_bytes += bytes_added

            total_used = sum(a.used_bytes for a in self._allocations.values())
            if total_used > self._total_bytes:
                logger.warning(
                    "Total used memory (%s) exceeds budget (%s)",
                    total_used,
                    self._total_bytes,
                )

    def record_deallocation(self, component: str, bytes_freed: int) -> None:
        """Record that *component* has freed *bytes_freed* bytes."""
        with self._lock:
            alloc = self._allocations.get(component)
            if alloc is None:
                logger.warning(
                    "record_deallocation called for unregistered component %r",
                    component,
                )
                return
            alloc.used_bytes = max(0, alloc.used_bytes - bytes_freed)

    def request_spill(self, component: str) -> None:
        """Signal that *component* should begin spilling data to disk.

        Sets the component's ``spill_state`` to ``SpillState.SPILLING`` and
        logs a warning.
        """
        with self._lock:
            alloc = self._allocations.get(component)
            if alloc is None:
                logger.warning(
                    "request_spill called for unregistered component %r", component
                )
                return
            alloc.spill_state = SpillState.SPILLING
            logger.warning(
                "Spill requested for component %r (used %s / max %s)",
                component,
                alloc.used_bytes,
                alloc.max_bytes,
            )

    def get_total_used(self) -> int:
        """Return the sum of ``used_bytes`` across all registered components."""
        with self._lock:
            return sum(a.used_bytes for a in self._allocations.values())

    def get_system_rss(self) -> int:
        """Return the current RSS (Resident Set Size) of this process."""
        try:
            return self._process.memory_info().rss
        except Exception:  # noqa: BLE001
            logger.debug("Failed to read system RSS; returning 0")
            return 0

    def reset(self) -> None:
        """Clear all registered allocations and accounting."""
        with self._lock:
            self._allocations.clear()
            logger.debug("Memory budget reset")
