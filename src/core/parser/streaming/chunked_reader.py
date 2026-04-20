"""Chunked sequential reader for HDD or network-backed XBRL source files.

Unlike ``MMapReader``, this reader performs large sequential reads in fixed
chunks (default 64 MiB) and extracts requested values as each chunk passes
over their byte offsets.  This access pattern is friendlier to rotational
media and high-latency network storage where random I/O is expensive.
"""

from __future__ import annotations

import logging
import os
from types import TracebackType
from typing import Optional

from src.core.constants import DEFAULT_IO_CHUNK_SIZE

logger = logging.getLogger(__name__)


class ChunkedReader:
    """Sequential chunked reader optimised for HDD / network storage.

    Parameters
    ----------
    file_path:
        Path to the XBRL source file.
    chunk_size:
        Number of bytes to read per sequential I/O operation.
    """

    def __init__(
        self,
        file_path: str,
        chunk_size: int = DEFAULT_IO_CHUNK_SIZE,
    ) -> None:
        self._file_path: str = file_path
        self._chunk_size: int = chunk_size
        self._fp: Optional[object] = None

        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.debug(
            "ChunkedReader initialised for %s (chunk_size=%s)",
            file_path,
            chunk_size,
        )

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def read_values(
        self, locations: list[tuple[int, int]]
    ) -> dict[int, bytes]:
        """Read values at the given ``(byte_offset, value_length)`` pairs.

        Algorithm
        ---------
        1. Sort locations by offset.
        2. Open the file and read in *chunk_size* blocks sequentially.
        3. As each chunk is read, extract any values whose byte range
           falls within the current window.
        4. Values that span a chunk boundary are handled by buffering
           the tail of the previous chunk.

        Parameters
        ----------
        locations:
            A list of ``(byte_offset, value_length)`` tuples.

        Returns
        -------
        dict[int, bytes]:
            Mapping from ``byte_offset`` → raw bytes for each
            requested location.
        """
        if not locations:
            return {}

        # Deduplicate and sort by offset
        sorted_locs = sorted(set(locations), key=lambda t: t[0])

        results: dict[int, bytes] = {}
        loc_idx = 0  # pointer into sorted_locs
        total_locs = len(sorted_locs)

        # Values spanning a boundary: offset -> accumulated bytes so far
        partial: dict[int, bytearray] = {}
        # How many bytes remain to be collected for a partial value
        partial_remaining: dict[int, int] = {}

        try:
            with open(self._file_path, "rb") as fh:
                file_offset = 0

                while loc_idx < total_locs or partial:
                    chunk = fh.read(self._chunk_size)
                    if not chunk:
                        break
                    chunk_start = file_offset
                    chunk_end = file_offset + len(chunk)

                    # ---- continue filling any partial values ----
                    completed_partials: list[int] = []
                    for p_offset in list(partial.keys()):
                        needed = partial_remaining[p_offset]
                        # How much of this chunk overlaps with the remaining
                        # data?  The partial value continues from the start
                        # of this chunk.
                        available = min(needed, len(chunk))
                        partial[p_offset].extend(chunk[:available])
                        partial_remaining[p_offset] -= available
                        if partial_remaining[p_offset] <= 0:
                            results[p_offset] = bytes(partial[p_offset])
                            completed_partials.append(p_offset)

                    for p_offset in completed_partials:
                        del partial[p_offset]
                        del partial_remaining[p_offset]

                    # ---- scan sorted_locs for values starting in this chunk ----
                    while loc_idx < total_locs:
                        offset, length = sorted_locs[loc_idx]

                        if offset >= chunk_end:
                            # This and all subsequent locations are beyond
                            # this chunk; move to the next chunk.
                            break

                        if offset < chunk_start:
                            # Should not happen with sorted order and
                            # sequential reading, but guard defensively.
                            loc_idx += 1
                            continue

                        rel_start = offset - chunk_start
                        rel_end = rel_start + length

                        if rel_end <= len(chunk):
                            # Value fits entirely within this chunk
                            results[offset] = chunk[rel_start:rel_end]
                        else:
                            # Value spans into the next chunk(s)
                            partial[offset] = bytearray(chunk[rel_start:])
                            partial_remaining[offset] = length - (
                                len(chunk) - rel_start
                            )

                        loc_idx += 1

                    file_offset = chunk_end

        except OSError:
            logger.exception(
                "I/O error reading %s", self._file_path
            )

        # Any remaining partials are truncated (file ended early) – log
        for p_offset in partial:
            logger.warning(
                "Value at offset %s truncated (file ended before value was "
                "fully read)",
                p_offset,
            )
            results[p_offset] = bytes(partial[p_offset])

        return results

    # ------------------------------------------------------------------
    # Cleanup & context manager
    # ------------------------------------------------------------------

    def close(self) -> None:
        """No-op; file handles are opened/closed per ``read_values`` call."""

    def __enter__(self) -> ChunkedReader:
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.close()
