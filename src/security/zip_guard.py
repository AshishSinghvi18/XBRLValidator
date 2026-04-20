"""Zip bomb and path-traversal protection for archive handling.

Validates ZIP archives before extraction by checking total uncompressed
size, per-entry compression ratios, file counts, and path safety.
Prevents zip bomb attacks and directory traversal exploits.

Spec references:
  - Rule 3 — Zero-Trust Parsing
  - CWE-409: Improper Handling of Highly Compressed Data (Zip Bomb)
  - CWE-22: Improper Limitation of a Pathname to a Restricted Directory

Example::

    guard = ZipGuard(max_uncompressed=1_073_741_824)  # 1 GB
    result = guard.validate_zip("report.zip")
    if result.is_safe:
        paths = guard.safe_extract("report.zip", "/dest/dir")
"""

from __future__ import annotations

import os
import stat
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from src.core.constants import (
    DEFAULT_MAX_ZIP_FILES,
    DEFAULT_MAX_ZIP_RATIO,
    DEFAULT_MAX_ZIP_UNCOMPRESSED_BYTES,
)
from src.core.exceptions import PathTraversalError, ZipBombError

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


@dataclass
class ZipValidationResult:
    """Result of ZIP archive validation.

    Attributes:
        total_compressed: Total compressed size in bytes.
        total_uncompressed: Total uncompressed size in bytes.
        file_count: Number of entries in the archive.
        max_ratio: Highest compression ratio among all entries.
        suspicious_entries: List of entry names that triggered warnings.
        is_safe: ``True`` if the archive passed all safety checks.
    """

    total_compressed: int = 0
    total_uncompressed: int = 0
    file_count: int = 0
    max_ratio: float = 0.0
    suspicious_entries: list[str] = field(default_factory=list)
    is_safe: bool = True


class ZipGuard:
    """Zip bomb and path-traversal protection.

    Validates ZIP archives against configurable limits for uncompressed
    size, compression ratio, and file count.  Also rejects entries with
    absolute paths, ``..`` path segments, or symlinks.
    """

    def __init__(
        self,
        max_uncompressed: int = DEFAULT_MAX_ZIP_UNCOMPRESSED_BYTES,
        max_ratio: int = DEFAULT_MAX_ZIP_RATIO,
        max_files: int = DEFAULT_MAX_ZIP_FILES,
    ) -> None:
        """Initialize the zip guard.

        Args:
            max_uncompressed: Maximum allowed total uncompressed size in
                bytes.  Defaults to ``DEFAULT_MAX_ZIP_UNCOMPRESSED_BYTES``.
            max_ratio: Maximum allowed compression ratio for any single
                entry.  Defaults to ``DEFAULT_MAX_ZIP_RATIO``.
            max_files: Maximum number of files allowed in the archive.
                Defaults to ``DEFAULT_MAX_ZIP_FILES``.
        """
        self.max_uncompressed: int = max_uncompressed
        self.max_ratio: int = max_ratio
        self.max_files: int = max_files
        self._log = logger.bind(
            component="zip_guard",
            max_uncompressed=max_uncompressed,
            max_ratio=max_ratio,
            max_files=max_files,
        )

    def validate_zip(self, zip_path: str) -> ZipValidationResult:
        """Validate a ZIP archive against safety limits.

        Checks performed:
          1. Total uncompressed size against ``max_uncompressed``
          2. Per-entry compression ratio against ``max_ratio``
          3. File count against ``max_files``
          4. Rejects entries with absolute paths
          5. Rejects entries containing ``..`` path segments
          6. Rejects symlink entries

        Args:
            zip_path: Path to the ZIP file to validate.

        Returns:
            A :class:`ZipValidationResult` with validation details.

        Raises:
            ZipBombError: If uncompressed size, ratio, or file count
                exceeds limits.
            PathTraversalError: If an entry uses absolute paths or ``..``
                segments.
        """
        result = ZipValidationResult()

        self._log.info("zip_validation_started", zip_path=zip_path)

        with zipfile.ZipFile(zip_path, "r") as zf:
            info_list = zf.infolist()
            result.file_count = len(info_list)

            # Check file count
            if result.file_count > self.max_files:
                self._log.error(
                    "zip_bomb_file_count",
                    file_count=result.file_count,
                    max_files=self.max_files,
                    zip_path=zip_path,
                )
                raise ZipBombError(
                    f"ZIP file count ({result.file_count}) exceeds "
                    f"maximum ({self.max_files})",
                    code="SEC-0003",
                    context={
                        "file_count": result.file_count,
                        "max_files": self.max_files,
                        "zip_path": zip_path,
                    },
                )

            for info in info_list:
                # Path safety: reject absolute paths
                if os.path.isabs(info.filename):
                    self._log.error(
                        "zip_absolute_path",
                        entry=info.filename,
                        zip_path=zip_path,
                    )
                    raise PathTraversalError(
                        f"ZIP entry has absolute path: {info.filename}",
                        code="SEC-0004",
                        context={
                            "entry": info.filename,
                            "zip_path": zip_path,
                        },
                    )

                # Path safety: reject ".." segments
                normalized = os.path.normpath(info.filename)
                if ".." in normalized.split(os.sep):
                    self._log.error(
                        "zip_path_traversal",
                        entry=info.filename,
                        zip_path=zip_path,
                    )
                    raise PathTraversalError(
                        f"ZIP entry contains path traversal: {info.filename}",
                        code="SEC-0004",
                        context={
                            "entry": info.filename,
                            "zip_path": zip_path,
                        },
                    )

                # Reject symlinks (external_attr upper 16 bits contain Unix mode)
                unix_mode = info.external_attr >> 16
                if unix_mode and stat.S_ISLNK(unix_mode):
                    result.suspicious_entries.append(info.filename)
                    self._log.error(
                        "zip_symlink_detected",
                        entry=info.filename,
                        zip_path=zip_path,
                    )
                    raise ZipBombError(
                        f"ZIP entry is a symlink: {info.filename}",
                        code="SEC-0003",
                        context={
                            "entry": info.filename,
                            "zip_path": zip_path,
                            "reason": "symlink",
                        },
                    )

                # Accumulate sizes
                result.total_compressed += info.compress_size
                result.total_uncompressed += info.file_size

                # Per-entry ratio check
                if info.compress_size > 0:
                    entry_ratio = info.file_size / info.compress_size
                    if entry_ratio > result.max_ratio:
                        result.max_ratio = entry_ratio

                    if entry_ratio > self.max_ratio:
                        result.suspicious_entries.append(info.filename)
                        self._log.error(
                            "zip_bomb_ratio",
                            entry=info.filename,
                            ratio=entry_ratio,
                            max_ratio=self.max_ratio,
                            zip_path=zip_path,
                        )
                        raise ZipBombError(
                            f"ZIP entry '{info.filename}' compression ratio "
                            f"({entry_ratio:.1f}) exceeds maximum ({self.max_ratio})",
                            code="SEC-0003",
                            context={
                                "entry": info.filename,
                                "ratio": entry_ratio,
                                "max_ratio": self.max_ratio,
                                "zip_path": zip_path,
                            },
                        )
                elif info.file_size > 0:
                    # Compressed size is 0 but file_size > 0: suspicious
                    result.suspicious_entries.append(info.filename)

            # Total uncompressed size check
            if result.total_uncompressed > self.max_uncompressed:
                self._log.error(
                    "zip_bomb_size",
                    total_uncompressed=result.total_uncompressed,
                    max_uncompressed=self.max_uncompressed,
                    zip_path=zip_path,
                )
                raise ZipBombError(
                    f"ZIP total uncompressed size ({result.total_uncompressed}) "
                    f"exceeds maximum ({self.max_uncompressed})",
                    code="SEC-0003",
                    context={
                        "total_uncompressed": result.total_uncompressed,
                        "max_uncompressed": self.max_uncompressed,
                        "zip_path": zip_path,
                    },
                )

        result.is_safe = len(result.suspicious_entries) == 0

        self._log.info(
            "zip_validation_complete",
            zip_path=zip_path,
            file_count=result.file_count,
            total_uncompressed=result.total_uncompressed,
            max_ratio=result.max_ratio,
            is_safe=result.is_safe,
        )
        return result

    def safe_extract(self, zip_path: str, dest: str) -> list[str]:
        """Extract a ZIP archive with full safety checks.

        Validates the archive first via :meth:`validate_zip`, then extracts
        all entries to *dest* with path-traversal prevention on each
        extracted file.

        Args:
            zip_path: Path to the ZIP file to extract.
            dest: Destination directory for extracted files.

        Returns:
            List of absolute paths of successfully extracted files.

        Raises:
            ZipBombError: If the archive fails validation.
            PathTraversalError: If an extracted path escapes *dest*.
        """
        # Validate first
        self.validate_zip(zip_path)

        dest_path = Path(dest).resolve()
        dest_path.mkdir(parents=True, exist_ok=True)
        extracted: list[str] = []

        self._log.info(
            "zip_extraction_started",
            zip_path=zip_path,
            dest=str(dest_path),
        )

        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                # Skip directories
                if info.is_dir():
                    dir_target = dest_path / info.filename
                    dir_resolved = dir_target.resolve()
                    if not str(dir_resolved).startswith(str(dest_path)):
                        raise PathTraversalError(
                            f"Directory entry escapes destination: {info.filename}",
                            code="SEC-0004",
                            context={
                                "entry": info.filename,
                                "dest": str(dest_path),
                            },
                        )
                    dir_resolved.mkdir(parents=True, exist_ok=True)
                    continue

                # Resolve and verify target path stays within dest
                target = dest_path / info.filename
                target_resolved = target.resolve()
                # Ensure parent dir for the target exists to avoid resolve()
                # failing on non-existent intermediate dirs
                target.parent.mkdir(parents=True, exist_ok=True)
                target_resolved = target.resolve()

                if not str(target_resolved).startswith(str(dest_path)):
                    self._log.error(
                        "zip_extraction_path_escape",
                        entry=info.filename,
                        resolved=str(target_resolved),
                        dest=str(dest_path),
                    )
                    raise PathTraversalError(
                        f"Extracted path escapes destination: {info.filename}",
                        code="SEC-0004",
                        context={
                            "entry": info.filename,
                            "resolved": str(target_resolved),
                            "dest": str(dest_path),
                        },
                    )

                # Extract single file
                with zf.open(info) as src, open(target_resolved, "wb") as dst:
                    while True:
                        chunk = src.read(65536)
                        if not chunk:
                            break
                        dst.write(chunk)

                extracted.append(str(target_resolved))

        self._log.info(
            "zip_extraction_complete",
            zip_path=zip_path,
            files_extracted=len(extracted),
        )
        return extracted
