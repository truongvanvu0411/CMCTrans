from __future__ import annotations

import sqlite3
import threading
from datetime import datetime

from .domain import SessionRecord, UserRecord


TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _serialize_timestamp(value: datetime) -> str:
    return value.strftime(TIMESTAMP_FORMAT)


def _parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, TIMESTAMP_FORMAT)


class UserRepository:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        lock: threading.RLock | None = None,
    ) -> None:
        self._connection = connection
        self._lock = lock or threading.RLock()

    def create_user(self, record: UserRecord) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO users (
                    id,
                    username,
                    password_hash,
                    role,
                    is_active,
                    created_at,
                    updated_at,
                    last_login_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.username,
                    record.password_hash,
                    record.role,
                    1 if record.is_active else 0,
                    _serialize_timestamp(record.created_at),
                    _serialize_timestamp(record.updated_at),
                    _serialize_timestamp(record.last_login_at)
                    if record.last_login_at is not None
                    else None,
                ),
            )
            self._connection.commit()

    def update_user(
        self,
        *,
        user_id: str,
        username: str,
        password_hash: str,
        role: str,
        is_active: bool,
        updated_at: datetime,
        last_login_at: datetime | None,
    ) -> None:
        with self._lock:
            self._connection.execute(
                """
                UPDATE users
                SET username = ?,
                    password_hash = ?,
                    role = ?,
                    is_active = ?,
                    updated_at = ?,
                    last_login_at = ?
                WHERE id = ?
                """,
                (
                    username,
                    password_hash,
                    role,
                    1 if is_active else 0,
                    _serialize_timestamp(updated_at),
                    _serialize_timestamp(last_login_at) if last_login_at is not None else None,
                    user_id,
                ),
            )
            self._connection.commit()

    def list_users(
        self,
        *,
        query: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> list[UserRecord]:
        sql = "SELECT * FROM users WHERE 1 = 1"
        parameters: list[object] = []
        if query is not None and query.strip():
            sql += " AND username LIKE ?"
            parameters.append(f"%{query.strip()}%")
        if role is not None:
            sql += " AND role = ?"
            parameters.append(role)
        if is_active is not None:
            sql += " AND is_active = ?"
            parameters.append(1 if is_active else 0)
        sql += " ORDER BY username ASC"
        with self._lock:
            rows = self._connection.execute(sql, tuple(parameters)).fetchall()
        return [self._map_user(row) for row in rows]

    def count_admin_users(self, *, active_only: bool) -> int:
        sql = "SELECT COUNT(*) FROM users WHERE role = 'admin'"
        parameters: list[object] = []
        if active_only:
            sql += " AND is_active = 1"
        with self._lock:
            row = self._connection.execute(sql, tuple(parameters)).fetchone()
        return int(row[0]) if row is not None else 0

    def get_user(self, user_id: str) -> UserRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return self._map_user(row)

    def find_by_username(self, username: str) -> UserRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            return None
        return self._map_user(row)

    def delete_user(self, user_id: str) -> None:
        with self._lock:
            self._connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
            self._connection.commit()

    def _map_user(self, row: sqlite3.Row) -> UserRecord:
        return UserRecord(
            id=str(row["id"]),
            username=str(row["username"]),
            password_hash=str(row["password_hash"]),
            role=str(row["role"]),
            is_active=bool(int(row["is_active"])),
            created_at=_parse_timestamp(str(row["created_at"])),
            updated_at=_parse_timestamp(str(row["updated_at"])),
            last_login_at=_parse_timestamp(str(row["last_login_at"]))
            if row["last_login_at"] is not None
            else None,
        )


class SessionRepository:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        lock: threading.RLock | None = None,
    ) -> None:
        self._connection = connection
        self._lock = lock or threading.RLock()

    def create_session(self, record: SessionRecord) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO user_sessions (
                    id,
                    user_id,
                    session_token,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.user_id,
                    record.session_token,
                    _serialize_timestamp(record.created_at),
                    _serialize_timestamp(record.updated_at),
                ),
            )
            self._connection.commit()

    def get_session_by_token(self, session_token: str) -> SessionRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM user_sessions WHERE session_token = ?",
                (session_token,),
            ).fetchone()
        if row is None:
            return None
        return self._map_session(row)

    def touch_session(self, session_id: str, updated_at: datetime) -> None:
        with self._lock:
            self._connection.execute(
                "UPDATE user_sessions SET updated_at = ? WHERE id = ?",
                (_serialize_timestamp(updated_at), session_id),
            )
            self._connection.commit()

    def delete_session_by_token(self, session_token: str) -> None:
        with self._lock:
            self._connection.execute(
                "DELETE FROM user_sessions WHERE session_token = ?",
                (session_token,),
            )
            self._connection.commit()

    def delete_sessions_for_user(self, user_id: str) -> None:
        with self._lock:
            self._connection.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
            self._connection.commit()

    def _map_session(self, row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            session_token=str(row["session_token"]),
            created_at=_parse_timestamp(str(row["created_at"])),
            updated_at=_parse_timestamp(str(row["updated_at"])),
        )
