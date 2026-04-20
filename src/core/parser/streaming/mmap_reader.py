"""Memory-mapped random-access reader for SSD-backed XBRL source files.

Uses Python's ``mmap`` module with read-only access to allow the OS
page-cache to handle caching transparently.  Best suited for SSD storage
where random I/O has low latency.
"""

from __future__ import annotations

import logging
import mmap
import os
from pathlib import Path
from types import TracebackType
from typing import Optional

logger = logging.getLogger(__name__)


class MMapReader:
    """Memory-mapped, read-only random-access reader.

    Parameters
    ----------
    file_path:
        Path to the XBRL source file.
    """

    def __init__(self, file_path: str) -> None:
        self._file_path: str = file_path
        self._fd: Optional[int] = None
        self._mm: Optional[mmap.mmap] = None

        try:
            self._fd = os.open(file_path, os.O_RDONLY)
            file_size = os.fstat(self._fd).st_size
            if file_size == 0:
                # mmap requires length > 0
                self._mm = None
                logger.debug("File %s is empty; mmap not created", file_path)
            else:
                self._mm = mmap.mmap(
                    self._fd, length=0, access=mmap.ACCESS_READ
                )
        except OSError:
            self._cleanup()
            raise

        logger.debug(
            "MMapReader opened %s (%s bytes)", file_path, file_size if self._mm else 0
        )

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def read_value(self, byte_offset: int, value_length: int) -> bytes:
        """Read *value_length* bytes starting at *byte_offset*.

        Returns
        -------
        bytes:
            The raw bytes from the mapped file.

        Raises
        ------
        ValueError:
            If the requested region is out of bounds or the file is empty.
        """
        if self._mm is None:
            raise ValueError("Cannot read from an empty or closed file")
        if byte_offset < 0 or value_length < 0:
            raise ValueError("byte_offset and value_length must be >= 0")
        if byte_offset + value_length > len(self._mm):
            raise ValueError(
                f"Requested region [{byte_offset}:{byte_offset + value_length}] "
                f"exceeds file size {len(self._mm)}"
            )
        return self._mm[byte_offset : byte_offset + value_length]

    def read_values_batch(
        self, locations: list[tuple[int, int]]
    ) -> list[bytes]:
        """Read multiple (offset, length) pairs in page-cache-friendly order.

        The locations are internally sorted by offset before reading so
        that sequential page faults are more likely to be served from the
        OS page cache.

        Parameters
        ----------
        locations:
            A list of ``(byte_offset, value_length)`` tuples.

        Returns
        -------
        list[bytes]:
            Values in the **original** (caller-supplied) order.
        """
        if not locations:
            return []

        # Build (original_index, offset, length) then sort by offset
        indexed = [
            (i, offset, length) for i, (offset, length) in enumerate(locations)
        ]
        indexed.sort(key=lambda t: t[1])

        results: list[Optional[bytes]] = [None] * len(locations)
        for orig_idx, offset, length in indexed:
            results[orig_idx] = self.read_value(offset, length)

        return results  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # SSD detection
    # ------------------------------------------------------------------

    @staticmethod
    def is_ssd(file_path: str) -> bool:
        """Heuristically determine whether *file_path* resides on an SSD.

        On Linux, checks ``/sys/block/<dev>/queue/rotational``.  A value
        of ``"0"`` means non-rotational (SSD/NVMe).  On other platforms
        or if detection fails, the method optimistically returns ``True``.
        """
        try:
            real = os.path.realpath(file_path)
            st = os.stat(real)
            major = os.major(st.st_dev)
            minor = os.minor(st.st_dev)

            # Try to find the block device in /sys/block
            sys_block = Path("/sys/block")
            if not sys_block.exists():
                return True  # Not Linux or sysfs unavailable

            for dev_dir in sys_block.iterdir():
                dev_file = dev_dir / "dev"
                if not dev_file.exists():
                    continue
                try:
                    dev_content = dev_file.read_text().strip()
                    dev_major, dev_minor = dev_content.split(":")
                    if int(dev_major) == major:
                        rotational_file = dev_dir / "queue" / "rotational"
                        if rotational_file.exists():
                            return (
                                rotational_file.read_text().strip() == "0"
                            )
                except (ValueError, OSError):
                    continue
        except (OSError, ValueError):
            pass

        # Fallback: assume SSD
        return True

    # ------------------------------------------------------------------
    # Cleanup & context manager
    # ------------------------------------------------------------------

    def _cleanup(self) -> None:
        """Internal cleanup; safe to call multiple times."""
        if self._mm is not None:
            try:
                self._mm.close()
            except Exception:  # noqa: BLE001
                pass
            self._mm = None
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def close(self) -> None:
        """Close the memory-mapped file and release resources."""
        self._cleanup()

    def __enter__(self) -> MMapReader:
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.close()
