from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime

from .repository import _serialize_timestamp


@dataclass(frozen=True)
class CorrectionRecord:
    id: str
    job_id: str
    segment_id: str
    source_language: str
    target_language: str
    source_text: str
    machine_translation: str | None
    corrected_translation: str
    created_at: datetime


class CorrectionRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._lock = threading.RLock()

    def create(self, record: CorrectionRecord) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO translation_corrections (
                    id,
                    job_id,
                    segment_id,
                    source_language,
                    target_language,
                    source_text,
                    machine_translation,
                    corrected_translation,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.job_id,
                    record.segment_id,
                    record.source_language,
                    record.target_language,
                    record.source_text,
                    record.machine_translation,
                    record.corrected_translation,
                    _serialize_timestamp(record.created_at),
                ),
            )
            self._connection.commit()
