from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime

from .repository import _parse_timestamp, _serialize_timestamp


@dataclass(frozen=True)
class GlossaryExactRecord:
    id: str
    source_language: str
    target_language: str
    source_text: str
    translated_text: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProtectedTermRecord:
    id: str
    term: str
    created_at: datetime
    updated_at: datetime


class GlossaryRepository:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        lock: threading.RLock | None = None,
    ) -> None:
        self._connection = connection
        self._lock = lock or threading.RLock()

    def list_exact_entries(self) -> list[GlossaryExactRecord]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT *
                FROM glossary_exact_entries
                ORDER BY source_language ASC, target_language ASC, source_text COLLATE NOCASE ASC
                """
            ).fetchall()
        return [self._map_exact(row) for row in rows]

    def count_exact_entries(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS count_value FROM glossary_exact_entries"
            ).fetchone()
        if row is None:
            return 0
        return int(row["count_value"])

    def get_exact_entry(self, entry_id: str) -> GlossaryExactRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM glossary_exact_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
        if row is None:
            return None
        return self._map_exact(row)

    def upsert_exact_entry(
        self,
        *,
        entry_id: str,
        source_language: str,
        target_language: str,
        source_text: str,
        translated_text: str,
        created_at: datetime,
        updated_at: datetime,
    ) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO glossary_exact_entries (
                    id,
                    source_language,
                    target_language,
                    source_text,
                    translated_text,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_language, target_language, source_text)
                DO UPDATE SET
                    translated_text = excluded.translated_text,
                    updated_at = excluded.updated_at
                """,
                (
                    entry_id,
                    source_language,
                    target_language,
                    source_text,
                    translated_text,
                    _serialize_timestamp(created_at),
                    _serialize_timestamp(updated_at),
                ),
            )
            self._connection.commit()

    def replace_exact_entry(
        self,
        *,
        entry_id: str,
        source_language: str,
        target_language: str,
        source_text: str,
        translated_text: str,
        updated_at: datetime,
    ) -> None:
        with self._lock:
            self._connection.execute(
                """
                UPDATE glossary_exact_entries
                SET source_language = ?,
                    target_language = ?,
                    source_text = ?,
                    translated_text = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    source_language,
                    target_language,
                    source_text,
                    translated_text,
                    _serialize_timestamp(updated_at),
                    entry_id,
                ),
            )
            self._connection.commit()

    def delete_exact_entry(self, entry_id: str) -> None:
        with self._lock:
            self._connection.execute(
                "DELETE FROM glossary_exact_entries WHERE id = ?",
                (entry_id,),
            )
            self._connection.commit()

    def list_protected_terms(self) -> list[ProtectedTermRecord]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT *
                FROM glossary_protected_terms
                ORDER BY term COLLATE NOCASE ASC
                """
            ).fetchall()
        return [self._map_protected(row) for row in rows]

    def count_protected_terms(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS count_value FROM glossary_protected_terms"
            ).fetchone()
        if row is None:
            return 0
        return int(row["count_value"])

    def get_protected_term(self, term_id: str) -> ProtectedTermRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM glossary_protected_terms WHERE id = ?",
                (term_id,),
            ).fetchone()
        if row is None:
            return None
        return self._map_protected(row)

    def upsert_protected_term(
        self,
        *,
        term_id: str,
        term: str,
        created_at: datetime,
        updated_at: datetime,
    ) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO glossary_protected_terms (
                    id,
                    term,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(term)
                DO UPDATE SET
                    updated_at = excluded.updated_at
                """,
                (
                    term_id,
                    term,
                    _serialize_timestamp(created_at),
                    _serialize_timestamp(updated_at),
                ),
            )
            self._connection.commit()

    def replace_protected_term(
        self,
        *,
        term_id: str,
        term: str,
        updated_at: datetime,
    ) -> None:
        with self._lock:
            self._connection.execute(
                """
                UPDATE glossary_protected_terms
                SET term = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    term,
                    _serialize_timestamp(updated_at),
                    term_id,
                ),
            )
            self._connection.commit()

    def delete_protected_term(self, term_id: str) -> None:
        with self._lock:
            self._connection.execute(
                "DELETE FROM glossary_protected_terms WHERE id = ?",
                (term_id,),
            )
            self._connection.commit()

    def _map_exact(self, row: sqlite3.Row) -> GlossaryExactRecord:
        return GlossaryExactRecord(
            id=str(row["id"]),
            source_language=str(row["source_language"]),
            target_language=str(row["target_language"]),
            source_text=str(row["source_text"]),
            translated_text=str(row["translated_text"]),
            created_at=_parse_timestamp(str(row["created_at"])),
            updated_at=_parse_timestamp(str(row["updated_at"])),
        )

    def _map_protected(self, row: sqlite3.Row) -> ProtectedTermRecord:
        return ProtectedTermRecord(
            id=str(row["id"]),
            term=str(row["term"]),
            created_at=_parse_timestamp(str(row["created_at"])),
            updated_at=_parse_timestamp(str(row["updated_at"])),
        )
