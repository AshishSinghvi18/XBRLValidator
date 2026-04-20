"""Thread-safe memory budget manager for streaming XBRL processing.

Spec: Rule 12 — Memory Budget.
Pressure thresholds: 0.80=warn, 0.90=force spill, 0.95=abort new allocs, 1.0=error.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from src.core.constants import DEFAULT_MEMORY_BUDGET_BYTES
from src.core.exceptions import MemoryBudgetExceededError

logger = logging.getLogger(__name__)

# Pressure thresholds
PRESSURE_WARN: float = 0.80
PRESSURE_FORCE_SPILL: float = 0.90
PRESSURE_ABORT_NEW: float = 0.95
PRESSURE_ERROR: float = 1.0


@dataclass
class MemoryAllocation:
    """Tracks a single component's memory allocation within the budget."""

    component: str
    max_bytes: int
    current_bytes: int = 0
    spill_callback: Optional[Callable[[], None]] = field(default=None, repr=False)

    @property
    def utilization(self) -> float:
        """Return fraction of this component's max that is used."""
        if self.max_bytes <= 0:
            return 0.0
        return self.current_bytes / self.max_bytes


class MemoryBudget:
    """Thread-safe global memory budget for the streaming pipeline.

    Components register for a slice of the total budget.  The budget
    tracks actual usage, triggers spill callbacks when pressure is high,
    and raises ``MemoryBudgetExceededError`` when the hard limit is hit.
    """

    def __init__(self, total_bytes: int = DEFAULT_MEMORY_BUDGET_BYTES) -> None:
        self._total_bytes: int = total_bytes
        self._lock: threading.Lock = threading.Lock()
        self._allocations: Dict[str, MemoryAllocation] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        component: str,
        max_bytes: int,
        spill_callback: Optional[Callable[[], None]] = None,
    ) -> MemoryAllocation:
        """Register *component* for up to *max_bytes* of the budget."""
        with self._lock:
            alloc = MemoryAllocation(
                component=component,
                max_bytes=max_bytes,
                spill_callback=spill_callback,
            )
            self._allocations[component] = alloc
            return alloc

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def can_allocate(self, component: str, additional_bytes: int) -> bool:
        """Return ``True`` if *additional_bytes* can be allocated."""
        with self._lock:
            total_used = self._total_used_unlocked()
            if total_used + additional_bytes > self._total_bytes:
                return False
            alloc = self._allocations.get(component)
            if alloc is not None:
                if alloc.current_bytes + additional_bytes > alloc.max_bytes:
                    return False
            ratio = (total_used + additional_bytes) / self._total_bytes
            return ratio < PRESSURE_ABORT_NEW

    def record_allocation(self, component: str, bytes_added: int) -> None:
        """Record that *component* consumed *bytes_added* more bytes."""
        with self._lock:
            alloc = self._allocations.get(component)
            if alloc is not None:
                alloc.current_bytes += bytes_added
            self._check_pressure_unlocked()

    def record_deallocation(self, component: str, bytes_freed: int) -> None:
        """Record that *component* freed *bytes_freed* bytes."""
        with self._lock:
            alloc = self._allocations.get(component)
            if alloc is not None:
                alloc.current_bytes = max(0, alloc.current_bytes - bytes_freed)

    def request_spill(self, component: str) -> None:
        """Request that *component* spill to disk immediately."""
        with self._lock:
            alloc = self._allocations.get(component)
        if alloc is not None and alloc.spill_callback is not None:
            alloc.spill_callback()

    def get_total_used(self) -> int:
        """Return total bytes currently allocated across all components."""
        with self._lock:
            return self._total_used_unlocked()

    def get_system_rss(self) -> int:
        """Return the current process RSS in bytes via *psutil*."""
        try:
            import psutil

            proc = psutil.Process()
            return proc.memory_info().rss
        except Exception:
            return 0

    def pressure_ratio(self) -> float:
        """Return current budget pressure as a float in [0.0, …]."""
        with self._lock:
            used = self._total_used_unlocked()
        if self._total_bytes <= 0:
            return 0.0
        return used / self._total_bytes

    def snapshot(self) -> Dict[str, int]:
        """Return ``{component: current_bytes}`` mapping."""
        with self._lock:
            return {
                name: alloc.current_bytes
                for name, alloc in self._allocations.items()
            }

    def enforce(self) -> None:
        """Raise ``MemoryBudgetExceededError`` if over budget."""
        with self._lock:
            used = self._total_used_unlocked()
            if used > self._total_bytes:
                raise MemoryBudgetExceededError(
                    component="global",
                    requested=used,
                    available=self._total_bytes - used,
                )

    # ------------------------------------------------------------------
    # Internal helpers (must be called with lock held)
    # ------------------------------------------------------------------

    def _total_used_unlocked(self) -> int:
        return sum(a.current_bytes for a in self._allocations.values())

    def _check_pressure_unlocked(self) -> None:
        used = self._total_used_unlocked()
        if self._total_bytes <= 0:
            return
        ratio = used / self._total_bytes

        if ratio >= PRESSURE_ERROR:
            raise MemoryBudgetExceededError(
                component="global",
                requested=used,
                available=self._total_bytes - used,
            )

        if ratio >= PRESSURE_FORCE_SPILL:
            # Spill the largest component
            largest = self._find_largest_unlocked()
            if largest is not None and largest.spill_callback is not None:
                # Release lock before callback to avoid deadlock
                cb = largest.spill_callback
                # We call outside the lock via a flag
                threading.Thread(target=cb, daemon=True).start()

        if ratio >= PRESSURE_WARN:
            logger.warning(
                "Memory pressure at %.1f%% (%d / %d bytes)",
                ratio * 100,
                used,
                self._total_bytes,
            )

    def _find_largest_unlocked(self) -> Optional[MemoryAllocation]:
        largest: Optional[MemoryAllocation] = None
        for alloc in self._allocations.values():
            if largest is None or alloc.current_bytes > largest.current_bytes:
                largest = alloc
        return largest
