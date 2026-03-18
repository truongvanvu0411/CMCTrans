from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime

from .domain import ActivityRecord


TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _serialize_timestamp(value: datetime) -> str:
    return value.strftime(TIMESTAMP_FORMAT)


def _parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, TIMESTAMP_FORMAT)


class ActivityRepository:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        lock: threading.RLock | None = None,
    ) -> None:
        self._connection = connection
        self._lock = lock or threading.RLock()

    def create(self, record: ActivityRecord) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO activity_logs (
                    id,
                    user_id,
                    username,
                    user_role,
                    action_type,
                    target_type,
                    target_id,
                    description,
                    metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.user_id,
                    record.username,
                    record.user_role,
                    record.action_type,
                    record.target_type,
                    record.target_id,
                    record.description,
                    json.dumps(record.metadata, ensure_ascii=False),
                    _serialize_timestamp(record.created_at),
                ),
            )
            self._connection.commit()

    def list_entries(
        self,
        *,
        user_id: str | None,
        action_type: str | None,
        target_type: str | None,
        query: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list[ActivityRecord]:
        sql = "SELECT * FROM activity_logs WHERE 1 = 1"
        parameters: list[object] = []
        if user_id is not None:
            sql += " AND user_id = ?"
            parameters.append(user_id)
        if action_type is not None:
            sql += " AND action_type = ?"
            parameters.append(action_type)
        if target_type is not None:
            sql += " AND target_type = ?"
            parameters.append(target_type)
        if query is not None and query.strip():
            needle = f"%{query.strip()}%"
            sql += " AND (username LIKE ? OR description LIKE ? OR metadata_json LIKE ? OR target_id LIKE ?)"
            parameters.extend([needle, needle, needle, needle])
        if date_from is not None:
            sql += " AND created_at >= ?"
            parameters.append(_serialize_timestamp(date_from))
        if date_to is not None:
            sql += " AND created_at <= ?"
            parameters.append(_serialize_timestamp(date_to))
        sql += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._connection.execute(sql, tuple(parameters)).fetchall()
        return [self._map_record(row) for row in rows]

    def list_distinct_action_types(self) -> list[str]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT DISTINCT action_type FROM activity_logs ORDER BY action_type ASC"
            ).fetchall()
        return [str(row[0]) for row in rows]

    def list_distinct_target_types(self) -> list[str]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT DISTINCT target_type FROM activity_logs ORDER BY target_type ASC"
            ).fetchall()
        return [str(row[0]) for row in rows]

    def _map_record(self, row: sqlite3.Row) -> ActivityRecord:
        return ActivityRecord(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            username=str(row["username"]),
            user_role=str(row["user_role"]),
            action_type=str(row["action_type"]),
            target_type=str(row["target_type"]),
            target_id=str(row["target_id"]) if row["target_id"] is not None else None,
            description=str(row["description"]),
            metadata=json.loads(str(row["metadata_json"])),
            created_at=_parse_timestamp(str(row["created_at"])),
        )
