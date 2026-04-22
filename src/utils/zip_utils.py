"""Safe ZIP extraction utilities with anti-zip-bomb and anti-path-traversal guards.

All extraction routines enforce:
- Maximum entry count
- Maximum compression ratio
- Maximum total uncompressed size
- Path traversal prevention (no ``..`` components, no absolute paths)

References:
    - CWE-22: Improper Limitation of a Pathname to a Restricted Directory
    - ZIP specification §4.3.7
    - XBRL Taxonomy Packages 1.0 §3.1
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path, PurePosixPath

from src.core.constants import (
    DEFAULT_MAX_ZIP_ENTRIES,
    DEFAULT_MAX_ZIP_RATIO,
    DEFAULT_MAX_ZIP_TOTAL_SIZE,
)
from src.core.exceptions import PathTraversalError, ZipBombError


def _validate_entry_name(name: str) -> None:
    """Validate that a ZIP entry name does not contain path traversal.

    Args:
        name: The ZIP entry's file name.

    Raises:
        PathTraversalError: If the name contains ``..`` or is absolute.
    """
    posix_path = PurePosixPath(name)

    # Reject absolute paths
    if posix_path.is_absolute():
        raise PathTraversalError(
            message=f"Absolute path in ZIP entry: {name!r}",
            context={"entry_name": name},
        )

    # Reject parent-directory traversal
    for part in posix_path.parts:
        if part == "..":
            raise PathTraversalError(
                message=f"Path traversal in ZIP entry: {name!r}",
                context={"entry_name": name},
            )


def validate_zip_safety(
    zip_path: str | Path,
    *,
    max_entries: int = DEFAULT_MAX_ZIP_ENTRIES,
    max_ratio: int = DEFAULT_MAX_ZIP_RATIO,
    max_total_size: int = DEFAULT_MAX_ZIP_TOTAL_SIZE,
) -> list[zipfile.ZipInfo]:
    """Validate a ZIP file for safety before extraction.

    Checks entry count, compression ratios, total uncompressed size,
    and path traversal in all entry names.

    Args:
        zip_path:       Path to the ZIP file.
        max_entries:    Maximum number of entries allowed.
        max_ratio:      Maximum compression ratio (uncompressed/compressed).
        max_total_size: Maximum total uncompressed size in bytes.

    Returns:
        List of ``ZipInfo`` objects for all entries.

    Raises:
        ZipBombError: If any safety check fails.
        PathTraversalError: If any entry name contains path traversal.
        zipfile.BadZipFile: If the file is not a valid ZIP.
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        entries = zf.infolist()

        # Check entry count
        if len(entries) > max_entries:
            raise ZipBombError(
                message=(
                    f"ZIP file contains {len(entries)} entries, "
                    f"exceeding the {max_entries} limit"
                ),
                context={
                    "zip_path": str(zip_path),
                    "entry_count": len(entries),
                    "max_entries": max_entries,
                },
            )

        total_uncompressed = 0
        for info in entries:
            # Validate entry name
            _validate_entry_name(info.filename)

            # Skip directories for size checks
            if info.is_dir():
                continue

            total_uncompressed += info.file_size

            # Check compression ratio
            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > max_ratio:
                    raise ZipBombError(
                        message=(
                            f"ZIP entry {info.filename!r} has compression ratio "
                            f"{ratio:.1f}x, exceeding the {max_ratio}x limit"
                        ),
                        context={
                            "zip_path": str(zip_path),
                            "entry_name": info.filename,
                            "ratio": ratio,
                            "max_ratio": max_ratio,
                        },
                    )

        # Check total uncompressed size
        if total_uncompressed > max_total_size:
            raise ZipBombError(
                message=(
                    f"ZIP total uncompressed size {total_uncompressed:,} bytes "
                    f"exceeds the {max_total_size:,}-byte limit"
                ),
                context={
                    "zip_path": str(zip_path),
                    "total_uncompressed": total_uncompressed,
                    "max_total_size": max_total_size,
                },
            )

        return entries


def safe_extract_all(
    zip_path: str | Path,
    dest_dir: str | Path,
    *,
    max_entries: int = DEFAULT_MAX_ZIP_ENTRIES,
    max_ratio: int = DEFAULT_MAX_ZIP_RATIO,
    max_total_size: int = DEFAULT_MAX_ZIP_TOTAL_SIZE,
) -> list[Path]:
    """Safely extract all entries from a ZIP file to a destination directory.

    Validates the ZIP for safety before extraction.

    Args:
        zip_path:       Path to the ZIP file.
        dest_dir:       Destination directory for extraction.
        max_entries:    Maximum number of entries allowed.
        max_ratio:      Maximum compression ratio.
        max_total_size: Maximum total uncompressed size.

    Returns:
        List of extracted file paths.

    Raises:
        ZipBombError: If any safety check fails.
        PathTraversalError: If path traversal is detected.
    """
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    entries = validate_zip_safety(
        zip_path,
        max_entries=max_entries,
        max_ratio=max_ratio,
        max_total_size=max_total_size,
    )

    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in entries:
            target = (dest / info.filename).resolve()

            # Final safety check: ensure target is under dest_dir
            if not str(target).startswith(str(dest) + os.sep) and target != dest:
                raise PathTraversalError(
                    message=(
                        f"Resolved path {target} escapes destination {dest}"
                    ),
                    context={
                        "entry_name": info.filename,
                        "resolved": str(target),
                        "dest_dir": str(dest),
                    },
                )

            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                extracted.append(target)

    return extracted


def safe_read_entry(
    zip_path: str | Path,
    entry_name: str,
    *,
    max_size: int = DEFAULT_MAX_ZIP_TOTAL_SIZE,
) -> bytes:
    """Read a single entry from a ZIP file safely.

    Args:
        zip_path:   Path to the ZIP file.
        entry_name: Name of the entry to read.
        max_size:   Maximum allowed uncompressed size.

    Returns:
        Raw bytes of the entry content.

    Raises:
        PathTraversalError: If the entry name contains path traversal.
        ZipBombError: If the entry is too large.
        KeyError: If the entry does not exist.
    """
    _validate_entry_name(entry_name)

    with zipfile.ZipFile(zip_path, "r") as zf:
        info = zf.getinfo(entry_name)
        if info.file_size > max_size:
            raise ZipBombError(
                message=(
                    f"ZIP entry {entry_name!r} uncompressed size "
                    f"{info.file_size:,} bytes exceeds {max_size:,}-byte limit"
                ),
                context={
                    "entry_name": entry_name,
                    "file_size": info.file_size,
                    "max_size": max_size,
                },
            )
        return zf.read(entry_name)


def list_entries(zip_path: str | Path) -> list[str]:
    """List all entry names in a ZIP file.

    Args:
        zip_path: Path to the ZIP file.

    Returns:
        List of entry names (file paths within the archive).
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        return zf.namelist()
