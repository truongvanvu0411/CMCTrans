from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime

from .repository import _parse_timestamp, _serialize_timestamp


@dataclass(frozen=True)
class TranslationMemoryRecord:
    id: str
    source_language: str
    target_language: str
    source_text: str
    translated_text: str
    created_at: datetime
    updated_at: datetime


class TranslationMemoryRepository:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        lock: threading.RLock | None = None,
    ) -> None:
        self._connection = connection
        self._lock = lock or threading.RLock()

    def find_exact(
        self,
        *,
        source_language: str,
        target_language: str,
        source_text: str,
    ) -> TranslationMemoryRecord | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT *
                FROM translation_memory
                WHERE source_language = ?
                  AND target_language = ?
                  AND source_text = ?
                """,
                (source_language, target_language, source_text),
            ).fetchone()
        if row is None:
            return None
        return self._map_record(row)

    def list_candidates(
        self,
        *,
        source_language: str,
        target_language: str,
        source_text: str,
        limit: int = 50,
    ) -> list[TranslationMemoryRecord]:
        minimum_length = max(1, len(source_text) - 20)
        maximum_length = len(source_text) + 20
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT *
                FROM translation_memory
                WHERE source_language = ?
                  AND target_language = ?
                  AND LENGTH(source_text) BETWEEN ? AND ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (
                    source_language,
                    target_language,
                    minimum_length,
                    maximum_length,
                    limit,
                ),
            ).fetchall()
        return [self._map_record(row) for row in rows]

    def upsert(
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
                INSERT INTO translation_memory (
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

    def list_entries(self, *, limit: int = 500) -> list[TranslationMemoryRecord]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT *
                FROM translation_memory
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._map_record(row) for row in rows]

    def get_entry(self, entry_id: str) -> TranslationMemoryRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM translation_memory WHERE id = ?",
                (entry_id,),
            ).fetchone()
        if row is None:
            return None
        return self._map_record(row)

    def replace_entry(
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
                UPDATE translation_memory
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

    def delete_entry(self, entry_id: str) -> None:
        with self._lock:
            self._connection.execute(
                "DELETE FROM translation_memory WHERE id = ?",
                (entry_id,),
            )
            self._connection.commit()

    def _map_record(self, row: sqlite3.Row) -> TranslationMemoryRecord:
        return TranslationMemoryRecord(
            id=str(row["id"]),
            source_language=str(row["source_language"]),
            target_language=str(row["target_language"]),
            source_text=str(row["source_text"]),
            translated_text=str(row["translated_text"]),
            created_at=_parse_timestamp(str(row["created_at"])),
            updated_at=_parse_timestamp(str(row["updated_at"])),
        )
