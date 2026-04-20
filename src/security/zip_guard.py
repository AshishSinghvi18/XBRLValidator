"""ZIP-bomb and path-traversal guard for archive extraction.

Validates ZIP archives before extraction to prevent decompression bombs,
path-traversal attacks, and symlink-based escapes.
"""

from __future__ import annotations

import os
import stat
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from src.core.constants import (
    DEFAULT_MAX_ZIP_ENTRIES,
    DEFAULT_MAX_ZIP_RATIO,
    DEFAULT_MAX_ZIP_TOTAL_SIZE,
)
from src.core.exceptions import PathTraversalError, ZipBombError


@dataclass(frozen=True)
class ZipCheckResult:
    """Results from a ZIP archive safety inspection.

    Attributes:
        safe:               ``True`` when no violations were found.
        total_entries:      Number of entries in the archive.
        total_uncompressed: Aggregate uncompressed size in bytes.
        max_ratio:          Highest per-entry compression ratio observed.
        violations:         Human-readable descriptions of each violation.
    """

    safe: bool
    total_entries: int
    total_uncompressed: int
    max_ratio: float
    violations: List[str] = field(default_factory=list)


class ZipGuard:
    """Validates ZIP archives against bomb, ratio, and traversal attacks.

    Args:
        max_uncompressed_bytes: Maximum allowed total uncompressed size.
        max_ratio:              Maximum per-entry compression ratio
                                (uncompressed / compressed).
        max_files:              Maximum number of entries in the archive.
    """

    def __init__(
        self,
        max_uncompressed_bytes: int = DEFAULT_MAX_ZIP_TOTAL_SIZE,
        max_ratio: int = DEFAULT_MAX_ZIP_RATIO,
        max_files: int = DEFAULT_MAX_ZIP_ENTRIES,
    ) -> None:
        self.max_uncompressed_bytes = max_uncompressed_bytes
        self.max_ratio = max_ratio
        self.max_files = max_files

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_zip(self, zip_path: str) -> ZipCheckResult:
        """Inspect *zip_path* for safety without extracting.

        Returns a :class:`ZipCheckResult` summarising the archive contents.
        """
        violations: List[str] = []
        total_uncompressed = 0
        max_ratio_seen = 0.0

        with zipfile.ZipFile(zip_path, "r") as zf:
            entries = zf.infolist()

            if len(entries) > self.max_files:
                violations.append(
                    f"Too many entries: {len(entries)} > {self.max_files}"
                )

            for info in entries:
                # Path-safety checks
                try:
                    self._check_path_safety(info)
                except (PathTraversalError, ZipBombError) as exc:
                    violations.append(str(exc))

                # Symlink check
                if self._is_symlink(info):
                    violations.append(
                        f"Symlink entry detected: {info.filename}"
                    )

                total_uncompressed += info.file_size

                # Compression ratio (guard against zero-length compressed)
                if info.compress_size > 0:
                    ratio = info.file_size / info.compress_size
                    if ratio > max_ratio_seen:
                        max_ratio_seen = ratio
                    if ratio > self.max_ratio:
                        violations.append(
                            f"Entry {info.filename!r} ratio {ratio:.1f}:1 "
                            f"exceeds limit {self.max_ratio}:1"
                        )
                elif info.file_size > 0:
                    # Compressed size is 0 but file_size > 0 – suspicious.
                    violations.append(
                        f"Entry {info.filename!r} has zero compressed size "
                        f"but {info.file_size} bytes uncompressed"
                    )

            if total_uncompressed > self.max_uncompressed_bytes:
                violations.append(
                    f"Total uncompressed size {total_uncompressed} bytes "
                    f"exceeds limit {self.max_uncompressed_bytes} bytes"
                )

        return ZipCheckResult(
            safe=len(violations) == 0,
            total_entries=len(entries),
            total_uncompressed=total_uncompressed,
            max_ratio=max_ratio_seen,
            violations=violations,
        )

    def safe_extract(self, zip_path: str, dest: str) -> List[str]:
        """Extract *zip_path* to *dest* after safety validation.

        Each entry is validated before extraction.  On any violation the
        method raises immediately without extracting further entries.

        Args:
            zip_path: Path to the ZIP archive.
            dest:     Destination directory for extraction.

        Returns:
            List of extracted file paths (absolute).

        Raises:
            ZipBombError:        On bomb-related violations.
            PathTraversalError:  On path-traversal violations.
        """
        dest_path = Path(dest).resolve()
        dest_path.mkdir(parents=True, exist_ok=True)

        extracted: List[str] = []
        total_uncompressed = 0

        with zipfile.ZipFile(zip_path, "r") as zf:
            entries = zf.infolist()

            if len(entries) > self.max_files:
                raise ZipBombError(
                    message=(
                        f"Archive contains {len(entries)} entries, "
                        f"exceeding the {self.max_files} limit"
                    ),
                    context={
                        "entry_count": len(entries),
                        "limit": self.max_files,
                    },
                )

            for info in entries:
                self.check_entry(info)

                total_uncompressed += info.file_size
                if total_uncompressed > self.max_uncompressed_bytes:
                    raise ZipBombError(
                        message=(
                            f"Cumulative uncompressed size "
                            f"({total_uncompressed} bytes) exceeds the "
                            f"{self.max_uncompressed_bytes}-byte limit"
                        ),
                        context={
                            "total_uncompressed": total_uncompressed,
                            "limit": self.max_uncompressed_bytes,
                            "triggering_entry": info.filename,
                        },
                    )

                # Resolve target path and ensure it stays within dest.
                target = (dest_path / info.filename).resolve()
                if not str(target).startswith(str(dest_path)):
                    raise PathTraversalError(
                        message=(
                            f"Resolved path {target} escapes destination "
                            f"directory {dest_path}"
                        ),
                        context={
                            "entry": info.filename,
                            "resolved": str(target),
                            "dest": str(dest_path),
                        },
                    )

                # Extract single entry
                zf.extract(info, path=str(dest_path))
                extracted.append(str(target))

        return extracted

    def check_entry(self, info: zipfile.ZipInfo) -> None:
        """Validate a single ZIP entry.

        Args:
            info: A :class:`zipfile.ZipInfo` for the entry.

        Raises:
            PathTraversalError: If the entry path is unsafe.
            ZipBombError:       If the compression ratio is suspicious.
        """
        self._check_path_safety(info)

        if self._is_symlink(info):
            raise PathTraversalError(
                message=f"Symlink entry not allowed: {info.filename}",
                context={"entry": info.filename},
            )

        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > self.max_ratio:
                raise ZipBombError(
                    message=(
                        f"Entry {info.filename!r} compression ratio "
                        f"{ratio:.1f}:1 exceeds {self.max_ratio}:1 limit"
                    ),
                    context={
                        "entry": info.filename,
                        "ratio": ratio,
                        "limit": self.max_ratio,
                    },
                )
        elif info.file_size > 0:
            raise ZipBombError(
                message=(
                    f"Entry {info.filename!r} has zero compressed size "
                    f"but {info.file_size} bytes uncompressed"
                ),
                context={
                    "entry": info.filename,
                    "file_size": info.file_size,
                },
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_path_safety(info: zipfile.ZipInfo) -> None:
        """Reject absolute paths and ``..`` segments."""
        filename = info.filename

        if os.path.isabs(filename):
            raise PathTraversalError(
                message=f"Absolute path in ZIP entry: {filename}",
                context={"entry": filename},
            )

        # Normalise separators for cross-platform safety.
        parts = Path(filename).parts
        if ".." in parts:
            raise PathTraversalError(
                message=f"Path traversal ('..') in ZIP entry: {filename}",
                context={"entry": filename},
            )

    @staticmethod
    def _is_symlink(info: zipfile.ZipInfo) -> bool:
        """Return ``True`` if the entry's external attributes indicate a symlink."""
        # Unix symlinks are flagged in the upper 16 bits of external_attr.
        unix_attrs = info.external_attr >> 16
        return bool(unix_attrs & stat.S_IFLNK == stat.S_IFLNK and unix_attrs != 0)
