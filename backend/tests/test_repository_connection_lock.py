from __future__ import annotations

import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, cast

from backend.app.activity_repository import ActivityRepository
from backend.app.auth_repository import UserRepository
from backend.app.database import connect_database, initialize_database


class GuardedConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._busy = threading.Lock()

    @contextmanager
    def _guard(self) -> Iterator[None]:
        if not self._busy.acquire(blocking=False):
            raise RuntimeError("Concurrent connection access detected.")
        try:
            time.sleep(0.03)
            yield
        finally:
            self._busy.release()

    def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> sqlite3.Cursor:
        with self._guard():
            return self._connection.execute(sql, parameters)

    def executemany(
        self,
        sql: str,
        seq_of_parameters: list[tuple[object, ...]],
    ) -> sqlite3.Cursor:
        with self._guard():
            return self._connection.executemany(sql, seq_of_parameters)

    def commit(self) -> None:
        with self._guard():
            self._connection.commit()


class RepositoryConnectionLockTests(unittest.TestCase):
    def test_shared_lock_serializes_access_across_repositories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "app.db"
            real_connection = connect_database(database_path)
            initialize_database(real_connection)
            guarded_connection = cast(sqlite3.Connection, GuardedConnection(real_connection))

            unshared_user_repository = UserRepository(guarded_connection)
            unshared_activity_repository = ActivityRepository(guarded_connection)
            unshared_errors = self._run_concurrent_reads(
                user_repository=unshared_user_repository,
                activity_repository=unshared_activity_repository,
            )
            self.assertEqual(unshared_errors, ["Concurrent connection access detected."])

            shared_lock = threading.RLock()
            shared_user_repository = UserRepository(guarded_connection, lock=shared_lock)
            shared_activity_repository = ActivityRepository(guarded_connection, lock=shared_lock)
            shared_errors = self._run_concurrent_reads(
                user_repository=shared_user_repository,
                activity_repository=shared_activity_repository,
            )
            self.assertEqual(shared_errors, [])

            real_connection.close()

    def _run_concurrent_reads(
        self,
        *,
        user_repository: UserRepository,
        activity_repository: ActivityRepository,
    ) -> list[str]:
        errors: list[str] = []
        start_barrier = threading.Barrier(2)

        def read_users() -> None:
            try:
                start_barrier.wait(timeout=1)
                user_repository.list_users(query=None, role=None, is_active=None)
            except Exception as exc:
                errors.append(str(exc))

        def read_activity() -> None:
            try:
                start_barrier.wait(timeout=1)
                activity_repository.list_entries(
                    user_id=None,
                    action_type=None,
                    target_type=None,
                    query=None,
                    date_from=None,
                    date_to=None,
                )
            except Exception as exc:
                errors.append(str(exc))

        user_thread = threading.Thread(target=read_users)
        activity_thread = threading.Thread(target=read_activity)
        user_thread.start()
        activity_thread.start()
        user_thread.join()
        activity_thread.join()
        errors.sort()
        return errors


if __name__ == "__main__":
    unittest.main()
