"""Disk-spilled (SQLite-backed) fact index for large XBRL filings.

When the in-memory fact index exceeds its spill threshold, facts are flushed
to a SQLite database on disk.  This module provides the same query interface
as ``InMemoryFactIndex`` so the caller can switch transparently.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
from typing import Iterator, Optional

from src.core.exceptions import DiskSpillError
from src.core.parser.streaming.fact_index import FactReference
from src.core.types import (
    BalanceType,
    ContextID,
    PeriodType,
    QName,
    UnitID,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 10_000

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS facts (
    idx           INTEGER PRIMARY KEY,
    concept       TEXT    NOT NULL,
    context_ref   TEXT    NOT NULL,
    unit_ref      TEXT,
    byte_offset   INTEGER NOT NULL,
    value_length  INTEGER NOT NULL,
    is_numeric    INTEGER NOT NULL,
    is_nil        INTEGER NOT NULL,
    decimals      TEXT,
    precision     TEXT,
    fact_id       TEXT,
    source_line   INTEGER NOT NULL,
    period_type   TEXT,
    balance_type  TEXT
);
"""

_CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS ix_concept      ON facts (concept);",
    "CREATE INDEX IF NOT EXISTS ix_context_ref   ON facts (context_ref);",
    "CREATE INDEX IF NOT EXISTS ix_unit_ref      ON facts (unit_ref);",
    "CREATE INDEX IF NOT EXISTS ix_cc            ON facts (concept, context_ref);",
    "CREATE INDEX IF NOT EXISTS ix_byte_offset   ON facts (byte_offset);",
]

_INSERT_SQL = """
INSERT OR REPLACE INTO facts (
    idx, concept, context_ref, unit_ref, byte_offset, value_length,
    is_numeric, is_nil, decimals, precision, fact_id, source_line,
    period_type, balance_type
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""


def _ref_to_row(ref: FactReference) -> tuple:
    """Convert a ``FactReference`` to a SQLite parameter tuple."""
    return (
        ref.index,
        ref.concept,
        ref.context_ref,
        ref.unit_ref,
        ref.byte_offset,
        ref.value_length,
        int(ref.is_numeric),
        int(ref.is_nil),
        ref.decimals,
        ref.precision,
        ref.id,
        ref.source_line,
        ref.period_type.value if ref.period_type else None,
        ref.balance_type.value if ref.balance_type else None,
    )


def _row_to_ref(row: tuple) -> FactReference:
    """Reconstruct a ``FactReference`` from a SQLite row."""
    return FactReference(
        index=row[0],
        concept=row[1],
        context_ref=row[2],
        unit_ref=row[3],
        byte_offset=row[4],
        value_length=row[5],
        is_numeric=bool(row[6]),
        is_nil=bool(row[7]),
        decimals=row[8],
        precision=row[9],
        id=row[10],
        source_line=row[11],
        period_type=PeriodType(row[12]) if row[12] else None,
        balance_type=BalanceType(row[13]) if row[13] else None,
    )


class DiskSpilledFactIndex:
    """SQLite-backed fact index sharing the same query interface as
    ``InMemoryFactIndex``.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  If ``None`` a temporary file
        is created automatically and deleted on ``close()``.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._is_temp: bool = db_path is None
        if db_path is None:
            fd, db_path = tempfile.mkstemp(suffix=".db", prefix="xbrl_spill_")
            os.close(fd)
        self._db_path: str = db_path
        self._count: int = 0

        try:
            self._conn: sqlite3.Connection = sqlite3.connect(
                self._db_path, check_same_thread=False
            )
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute(_CREATE_TABLE_SQL)
            for idx_sql in _CREATE_INDEXES_SQL:
                self._conn.execute(idx_sql)
            self._conn.commit()
        except sqlite3.Error as exc:
            raise DiskSpillError(
                f"Failed to initialise spill database at {db_path}: {exc}"
            ) from exc

        logger.info("DiskSpilledFactIndex opened at %s", self._db_path)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, ref: FactReference) -> bool:
        """Insert a single ``FactReference``.

        Returns ``True`` on success, ``False`` on failure (logged, not raised).
        """
        try:
            self._conn.execute(_INSERT_SQL, _ref_to_row(ref))
            self._conn.commit()
            self._count += 1
            return True
        except sqlite3.Error:
            logger.exception("Failed to insert fact %s", ref.index)
            return False

    def add_batch(self, refs: list[FactReference]) -> None:
        """Insert a batch of ``FactReference`` objects in a single transaction.

        The batch is split into sub-batches of 10 000 rows to keep
        write-ahead-log growth bounded.
        """
        try:
            for start in range(0, len(refs), _BATCH_SIZE):
                chunk = refs[start : start + _BATCH_SIZE]
                self._conn.executemany(
                    _INSERT_SQL, [_ref_to_row(r) for r in chunk]
                )
            self._conn.commit()
            self._count += len(refs)
        except sqlite3.Error:
            logger.exception("Batch insert failed")
            raise DiskSpillError("Batch insert into spill database failed")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        """Number of facts stored in the database."""
        return self._count

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def _query(self, sql: str, params: tuple = ()) -> list[FactReference]:
        """Execute *sql* with *params* and convert every row."""
        try:
            cursor = self._conn.execute(sql, params)
            return [_row_to_ref(row) for row in cursor.fetchall()]
        except sqlite3.Error:
            logger.exception("Query failed: %s", sql)
            return []

    def get_by_concept(self, concept: QName) -> list[FactReference]:
        """Return all facts matching the given *concept*."""
        return self._query("SELECT * FROM facts WHERE concept = ?", (concept,))

    def get_by_context(self, ctx_id: ContextID) -> list[FactReference]:
        """Return all facts matching the given *context id*."""
        return self._query(
            "SELECT * FROM facts WHERE context_ref = ?", (ctx_id,)
        )

    def get_by_unit(self, unit_id: UnitID) -> list[FactReference]:
        """Return all facts matching the given *unit id*."""
        return self._query(
            "SELECT * FROM facts WHERE unit_ref = ?", (unit_id,)
        )

    def get_by_concept_and_context(
        self, concept: QName, ctx_id: ContextID
    ) -> list[FactReference]:
        """Return all facts matching both *concept* and *context id*."""
        return self._query(
            "SELECT * FROM facts WHERE concept = ? AND context_ref = ?",
            (concept, ctx_id),
        )

    def get_duplicate_groups(self) -> dict[tuple, list[FactReference]]:
        """Return groups of facts sharing the same (concept, context, unit).

        Only groups with more than one member are returned.
        """
        groups: dict[tuple, list[FactReference]] = {}
        try:
            cursor = self._conn.execute(
                "SELECT concept, context_ref, COALESCE(unit_ref, '') "
                "FROM facts "
                "GROUP BY concept, context_ref, COALESCE(unit_ref, '') "
                "HAVING COUNT(*) > 1"
            )
            for concept, ctx, unit in cursor.fetchall():
                key = (concept, ctx, unit)
                unit_param = unit if unit != "" else None
                if unit_param is not None:
                    refs = self._query(
                        "SELECT * FROM facts "
                        "WHERE concept = ? AND context_ref = ? AND unit_ref = ?",
                        (concept, ctx, unit_param),
                    )
                else:
                    refs = self._query(
                        "SELECT * FROM facts "
                        "WHERE concept = ? AND context_ref = ? AND unit_ref IS NULL",
                        (concept, ctx),
                    )
                if refs:
                    groups[key] = refs
        except sqlite3.Error:
            logger.exception("get_duplicate_groups query failed")
        return groups

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def iter_all(self) -> Iterator[FactReference]:
        """Iterate over every stored ``FactReference`` (ordered by index)."""
        try:
            cursor = self._conn.execute("SELECT * FROM facts ORDER BY idx")
            while True:
                row = cursor.fetchone()
                if row is None:
                    break
                yield _row_to_ref(row)
        except sqlite3.Error:
            logger.exception("iter_all query failed")

    def iter_batches(
        self, batch_size: int = 10_000
    ) -> Iterator[list[FactReference]]:
        """Yield successive batches of ``FactReference`` objects."""
        try:
            cursor = self._conn.execute("SELECT * FROM facts ORDER BY idx")
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                yield [_row_to_ref(r) for r in rows]
        except sqlite3.Error:
            logger.exception("iter_batches query failed")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection and remove the temp file (if any)."""
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            logger.debug("Error closing spill database", exc_info=True)

        if self._is_temp:
            try:
                os.unlink(self._db_path)
                logger.debug("Removed temp spill file %s", self._db_path)
            except OSError:
                logger.debug(
                    "Could not remove temp spill file %s",
                    self._db_path,
                    exc_info=True,
                )

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass
