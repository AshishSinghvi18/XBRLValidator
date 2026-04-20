"""SQLite-backed fact index for disk-spilled large file processing.

Spec: XBRL 2.1 - streaming fact storage for files >100MB.
Same interface as InMemoryFactIndex, backed by SQLite with WAL mode.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from collections import defaultdict
from typing import Dict, Iterator, List, Optional, Tuple

import structlog

from src.core.parser.streaming.fact_index import FactReference
from src.core.types import BalanceType, PeriodType, QName, ContextID, UnitID

logger = structlog.get_logger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS facts (
    idx             INTEGER PRIMARY KEY,
    concept         TEXT NOT NULL,
    context_ref     TEXT NOT NULL,
    unit_ref        TEXT,
    byte_offset     INTEGER NOT NULL,
    value_length    INTEGER NOT NULL,
    value_preview   BLOB,
    is_numeric      INTEGER NOT NULL,
    is_nil          INTEGER NOT NULL,
    is_tuple        INTEGER NOT NULL,
    decimals        TEXT,
    precision_val   TEXT,
    fact_id         TEXT,
    source_line     INTEGER NOT NULL,
    source_column   INTEGER NOT NULL,
    period_type     TEXT,
    balance_type    TEXT,
    language        TEXT,
    parent_tuple    INTEGER
)
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_concept ON facts(concept)",
    "CREATE INDEX IF NOT EXISTS idx_context ON facts(context_ref)",
    "CREATE INDEX IF NOT EXISTS idx_unit ON facts(unit_ref)",
    "CREATE INDEX IF NOT EXISTS idx_cc ON facts(concept, context_ref)",
    "CREATE INDEX IF NOT EXISTS idx_parent ON facts(parent_tuple)",
    "CREATE INDEX IF NOT EXISTS idx_fact_id ON facts(fact_id) WHERE fact_id IS NOT NULL",
]

_INSERT = """
INSERT INTO facts (idx, concept, context_ref, unit_ref, byte_offset, value_length,
    value_preview, is_numeric, is_nil, is_tuple, decimals, precision_val, fact_id,
    source_line, source_column, period_type, balance_type, language, parent_tuple)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _ref_to_row(ref: FactReference) -> tuple:
    """Convert FactReference to SQLite row tuple."""
    return (
        ref.index, ref.concept, ref.context_ref, ref.unit_ref,
        ref.byte_offset, ref.value_length, ref.value_preview,
        int(ref.is_numeric), int(ref.is_nil), int(ref.is_tuple),
        ref.decimals, ref.precision, ref.id,
        ref.source_line, ref.source_column,
        ref.period_type.value if ref.period_type else None,
        ref.balance_type.value if ref.balance_type else None,
        ref.language, ref.parent_tuple_ref,
    )


def _row_to_ref(row: tuple) -> FactReference:
    """Convert SQLite row to FactReference."""
    return FactReference(
        index=row[0], concept=row[1], context_ref=row[2], unit_ref=row[3],
        byte_offset=row[4], value_length=row[5], value_preview=row[6],
        is_numeric=bool(row[7]), is_nil=bool(row[8]), is_tuple=bool(row[9]),
        decimals=row[10], precision=row[11], id=row[12],
        source_line=row[13], source_column=row[14],
        period_type=PeriodType(row[15]) if row[15] else None,
        balance_type=BalanceType(row[16]) if row[16] else None,
        language=row[17], parent_tuple_ref=row[18],
    )


class DiskSpilledFactIndex:
    """SQLite-backed fact index for large files exceeding memory budget.

    Same query interface as InMemoryFactIndex. Uses WAL mode and
    batched inserts (10K per transaction) for performance.

    Spec: Supports XBRL 2.1 streaming validation for files > 100MB.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            fd, db_path = tempfile.mkstemp(suffix=".sqlite3", prefix="xbrl_facts_")
            os.close(fd)
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-65536")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._conn.execute("PRAGMA mmap_size=268435456")
        self._conn.execute(_CREATE_TABLE)
        for idx_sql in _CREATE_INDEXES:
            self._conn.execute(idx_sql)
        self._conn.commit()
        self._count = 0
        self._pending: List[tuple] = []
        self._batch_size = 10_000
        logger.info("disk_spill.initialized", db_path=db_path)

    @property
    def count(self) -> int:
        """Number of facts stored."""
        return self._count

    @property
    def should_spill(self) -> bool:
        """Always False - already on disk."""
        return False

    @property
    def estimated_bytes(self) -> int:
        """Estimated disk usage."""
        try:
            return os.path.getsize(self._db_path)
        except OSError:
            return 0

    def add(self, ref: FactReference) -> bool:
        """Add a fact reference."""
        self._pending.append(_ref_to_row(ref))
        self._count += 1
        if len(self._pending) >= self._batch_size:
            self._flush()
        return True

    def add_batch(self, refs: List[FactReference]) -> int:
        """Add a batch of fact references."""
        rows = [_ref_to_row(r) for r in refs]
        self._pending.extend(rows)
        self._count += len(refs)
        if len(self._pending) >= self._batch_size:
            self._flush()
        return len(refs)

    def _flush(self) -> None:
        """Flush pending inserts to SQLite."""
        if not self._pending:
            return
        self._conn.executemany(_INSERT, self._pending)
        self._conn.commit()
        self._pending.clear()

    def get(self, idx: int) -> FactReference:
        """Get fact reference by ordinal index."""
        self._flush()
        row = self._conn.execute("SELECT * FROM facts WHERE idx = ?", (idx,)).fetchone()
        if row is None:
            raise IndexError(f"Fact index {idx} not found")
        return _row_to_ref(row)

    def get_by_concept(self, concept: QName) -> List[FactReference]:
        """Get all fact references for a concept."""
        self._flush()
        rows = self._conn.execute("SELECT * FROM facts WHERE concept = ?", (concept,)).fetchall()
        return [_row_to_ref(r) for r in rows]

    def get_by_context(self, ctx_id: ContextID) -> List[FactReference]:
        """Get all fact references for a context."""
        self._flush()
        rows = self._conn.execute("SELECT * FROM facts WHERE context_ref = ?", (ctx_id,)).fetchall()
        return [_row_to_ref(r) for r in rows]

    def get_by_unit(self, unit_id: UnitID) -> List[FactReference]:
        """Get all fact references for a unit."""
        self._flush()
        rows = self._conn.execute("SELECT * FROM facts WHERE unit_ref = ?", (unit_id,)).fetchall()
        return [_row_to_ref(r) for r in rows]

    def get_by_concept_and_context(self, concept: QName, ctx_id: ContextID) -> List[FactReference]:
        """Get fact references matching both concept and context."""
        self._flush()
        rows = self._conn.execute(
            "SELECT * FROM facts WHERE concept = ? AND context_ref = ?", (concept, ctx_id)
        ).fetchall()
        return [_row_to_ref(r) for r in rows]

    def get_duplicate_groups(self) -> Dict[Tuple[str, ...], List[FactReference]]:
        """Get groups of duplicate facts."""
        self._flush()
        cursor = self._conn.execute(
            "SELECT concept, context_ref, COALESCE(unit_ref,''), COALESCE(language,'') "
            "FROM facts GROUP BY concept, context_ref, unit_ref, language HAVING COUNT(*) > 1"
        )
        result: Dict[Tuple[str, ...], List[FactReference]] = {}
        for row in cursor:
            key = (row[0], row[1], row[2], row[3])
            refs = self._conn.execute(
                "SELECT * FROM facts WHERE concept=? AND context_ref=? "
                "AND COALESCE(unit_ref,'')=? AND COALESCE(language,'')=?", key
            ).fetchall()
            result[key] = [_row_to_ref(r) for r in refs]
        return result

    def get_tuple_children(self, parent_idx: int) -> List[FactReference]:
        """Get child facts of a tuple."""
        self._flush()
        rows = self._conn.execute(
            "SELECT * FROM facts WHERE parent_tuple = ?", (parent_idx,)
        ).fetchall()
        return [_row_to_ref(r) for r in rows]

    def iter_all(self) -> Iterator[FactReference]:
        """Iterate over all fact references."""
        self._flush()
        cursor = self._conn.execute("SELECT * FROM facts ORDER BY idx")
        for row in cursor:
            yield _row_to_ref(row)

    def iter_batches(self, batch_size: int = 10_000) -> Iterator[List[FactReference]]:
        """Iterate in batches of given size."""
        self._flush()
        offset = 0
        while True:
            rows = self._conn.execute(
                "SELECT * FROM facts ORDER BY idx LIMIT ? OFFSET ?", (batch_size, offset)
            ).fetchall()
            if not rows:
                break
            yield [_row_to_ref(r) for r in rows]
            offset += batch_size

    def iter_by_concept(self) -> Iterator[Tuple[QName, List[FactReference]]]:
        """Iterate grouped by concept."""
        self._flush()
        concepts = self._conn.execute("SELECT DISTINCT concept FROM facts ORDER BY concept").fetchall()
        for (concept,) in concepts:
            refs = self.get_by_concept(concept)
            yield concept, refs

    def close(self) -> None:
        """Close the database connection and clean up."""
        try:
            self._flush()
            self._conn.close()
        except Exception:
            pass
        try:
            if os.path.exists(self._db_path):
                os.unlink(self._db_path)
                wal = self._db_path + "-wal"
                shm = self._db_path + "-shm"
                if os.path.exists(wal):
                    os.unlink(wal)
                if os.path.exists(shm):
                    os.unlink(shm)
        except OSError:
            pass

    def __del__(self) -> None:
        """Best-effort cleanup."""
        try:
            self.close()
        except Exception:
            pass
