from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime

from .domain import JobRecord, SegmentRecord


TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _serialize_timestamp(value: datetime) -> str:
    return value.strftime(TIMESTAMP_FORMAT)


def _parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, TIMESTAMP_FORMAT)


class JobRepository:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        lock: threading.RLock | None = None,
    ) -> None:
        self._connection = connection
        self._lock = lock or threading.RLock()

    def create_job(self, record: JobRecord) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO jobs (
                    id,
                    original_file_name,
                    original_file_path,
                    output_file_path,
                    owner_user_id,
                    file_type,
                    status,
                    current_step,
                    progress_percent,
                    processed_segments,
                    total_segments,
                    status_message,
                    current_sheet,
                    current_cell,
                    preview_ready,
                    preview_summary_json,
                    source_language,
                    target_language,
                    parse_summary_json,
                    translation_summary_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.original_file_name,
                    record.original_file_path,
                    record.output_file_path,
                    record.owner_user_id,
                    record.file_type,
                    record.status,
                    record.current_step,
                    record.progress_percent,
                    record.processed_segments,
                    record.total_segments,
                    record.status_message,
                    record.current_sheet,
                    record.current_cell,
                    1 if record.preview_ready else 0,
                    json.dumps(record.preview_summary),
                    record.source_language,
                    record.target_language,
                    json.dumps(record.parse_summary),
                    json.dumps(record.translation_summary),
                    _serialize_timestamp(record.created_at),
                    _serialize_timestamp(record.updated_at),
                ),
            )
            self._connection.commit()

    def update_job(
        self,
        job_id: str,
        *,
        status: str,
        current_step: str,
        progress_percent: int,
        processed_segments: int,
        total_segments: int,
        status_message: str,
        current_sheet: str | None,
        current_cell: str | None,
        preview_ready: bool,
        preview_summary: dict[str, object],
        source_language: str | None,
        target_language: str | None,
        parse_summary: dict[str, object],
        translation_summary: dict[str, object],
        output_file_path: str | None,
        updated_at: datetime,
    ) -> None:
        with self._lock:
            self._connection.execute(
                """
                UPDATE jobs
                SET status = ?,
                    current_step = ?,
                    progress_percent = ?,
                    processed_segments = ?,
                    total_segments = ?,
                    status_message = ?,
                    current_sheet = ?,
                    current_cell = ?,
                    preview_ready = ?,
                    preview_summary_json = ?,
                    source_language = ?,
                    target_language = ?,
                    parse_summary_json = ?,
                    translation_summary_json = ?,
                    output_file_path = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    current_step,
                    progress_percent,
                    processed_segments,
                    total_segments,
                    status_message,
                    current_sheet,
                    current_cell,
                    1 if preview_ready else 0,
                    json.dumps(preview_summary),
                    source_language,
                    target_language,
                    json.dumps(parse_summary),
                    json.dumps(translation_summary),
                    output_file_path,
                    _serialize_timestamp(updated_at),
                    job_id,
                ),
            )
            self._connection.commit()

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return self._map_job(row)

    def list_jobs(self) -> list[JobRecord]:
        return self.list_jobs_for_owner(owner_user_id=None)

    def list_jobs_for_owner(self, owner_user_id: str | None) -> list[JobRecord]:
        sql = "SELECT * FROM jobs"
        parameters: list[object] = []
        if owner_user_id is not None:
            sql += " WHERE owner_user_id = ?"
            parameters.append(owner_user_id)
        sql += " ORDER BY updated_at DESC"
        with self._lock:
            rows = self._connection.execute(sql, tuple(parameters)).fetchall()
        return [self._map_job(row) for row in rows]

    def delete_job(self, job_id: str) -> None:
        with self._lock:
            self._connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            self._connection.commit()

    def replace_segments(self, job_id: str, segments: list[SegmentRecord]) -> None:
        with self._lock:
            self._connection.execute("DELETE FROM segments WHERE job_id = ?", (job_id,))
            self._connection.executemany(
            """
            INSERT INTO segments (
                id,
                job_id,
                order_index,
                sheet_name,
                sheet_index,
                cell_address,
                location_type,
                original_text,
                normalized_text,
                machine_translation,
                edited_translation,
                final_text,
                intermediate_translation,
                status,
                warning_codes_json,
                locator_json,
                error_message,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    segment.id,
                    segment.job_id,
                    segment.order_index,
                    segment.sheet_name,
                    segment.sheet_index,
                    segment.cell_address,
                    segment.location_type,
                    segment.original_text,
                    segment.normalized_text,
                    segment.machine_translation,
                    segment.edited_translation,
                    segment.final_text,
                    segment.intermediate_translation,
                    segment.status,
                    json.dumps(segment.warning_codes),
                    json.dumps(segment.locator),
                    segment.error_message,
                    _serialize_timestamp(segment.created_at),
                    _serialize_timestamp(segment.updated_at),
                )
                for segment in segments
            ],
            )
            self._connection.commit()

    def list_segments(
        self,
        job_id: str,
        *,
        sheet_name: str | None,
        status: str | None,
        query: str | None,
    ) -> list[SegmentRecord]:
        sql = "SELECT * FROM segments WHERE job_id = ?"
        parameters: list[str] = [job_id]
        if sheet_name is not None:
            sql += " AND sheet_name = ?"
            parameters.append(sheet_name)
        if status is not None:
            sql += " AND status = ?"
            parameters.append(status)
        if query is not None:
            sql += " AND (original_text LIKE ? OR final_text LIKE ? OR machine_translation LIKE ?)"
            needle = f"%{query}%"
            parameters.extend([needle, needle, needle])
        sql += " ORDER BY order_index ASC"
        with self._lock:
            rows = self._connection.execute(sql, tuple(parameters)).fetchall()
        return [self._map_segment(row) for row in rows]

    def get_segment(self, job_id: str, segment_id: str) -> SegmentRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM segments WHERE job_id = ? AND id = ?",
                (job_id, segment_id),
            ).fetchone()
        if row is None:
            return None
        return self._map_segment(row)

    def update_segment(
        self,
        *,
        job_id: str,
        segment_id: str,
        machine_translation: str | None,
        edited_translation: str | None,
        final_text: str | None,
        intermediate_translation: str | None,
        status: str,
        error_message: str | None,
        updated_at: datetime,
    ) -> None:
        with self._lock:
            self._connection.execute(
            """
            UPDATE segments
            SET machine_translation = ?,
                edited_translation = ?,
                final_text = ?,
                intermediate_translation = ?,
                status = ?,
                error_message = ?,
                updated_at = ?
            WHERE job_id = ? AND id = ?
            """,
            (
                machine_translation,
                edited_translation,
                final_text,
                intermediate_translation,
                status,
                error_message,
                _serialize_timestamp(updated_at),
                job_id,
                segment_id,
            ),
            )
            self._connection.commit()

    def bulk_update_segments(
        self,
        updates: list[
            tuple[str, str | None, str | None, str | None, str | None, str, str | None, datetime]
        ],
        *,
        job_id: str,
    ) -> None:
        with self._lock:
            self._connection.executemany(
            """
            UPDATE segments
            SET machine_translation = ?,
                edited_translation = ?,
                final_text = ?,
                intermediate_translation = ?,
                status = ?,
                error_message = ?,
                updated_at = ?
            WHERE job_id = ? AND id = ?
            """,
            [
                (
                    machine_translation,
                    edited_translation,
                    final_text,
                    intermediate_translation,
                    status,
                    error_message,
                    _serialize_timestamp(updated_at),
                    job_id,
                    segment_id,
                )
                for (
                    segment_id,
                    machine_translation,
                    edited_translation,
                    final_text,
                    intermediate_translation,
                    status,
                    error_message,
                    updated_at,
                ) in updates
            ],
            )
            self._connection.commit()

    def bulk_update_segment_warning_codes(
        self,
        *,
        job_id: str,
        updates: list[tuple[str, list[str], datetime]],
    ) -> None:
        with self._lock:
            self._connection.executemany(
                """
                UPDATE segments
                SET warning_codes_json = ?,
                    updated_at = ?
                WHERE job_id = ? AND id = ?
                """,
                [
                    (
                        json.dumps(warning_codes),
                        _serialize_timestamp(updated_at),
                        job_id,
                        segment_id,
                    )
                    for segment_id, warning_codes, updated_at in updates
                ],
            )
            self._connection.commit()

    def _map_job(self, row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=str(row["id"]),
            original_file_name=str(row["original_file_name"]),
            original_file_path=str(row["original_file_path"]),
            output_file_path=str(row["output_file_path"]) if row["output_file_path"] else None,
            owner_user_id=str(row["owner_user_id"]) if row["owner_user_id"] else None,
            file_type=str(row["file_type"]),
            status=str(row["status"]),
            current_step=str(row["current_step"]),
            progress_percent=int(row["progress_percent"]),
            processed_segments=int(row["processed_segments"]),
            total_segments=int(row["total_segments"]),
            status_message=str(row["status_message"]),
            current_sheet=str(row["current_sheet"]) if row["current_sheet"] else None,
            current_cell=str(row["current_cell"]) if row["current_cell"] else None,
            preview_ready=bool(int(row["preview_ready"])),
            preview_summary=json.loads(str(row["preview_summary_json"])),
            source_language=str(row["source_language"]) if row["source_language"] else None,
            target_language=str(row["target_language"]) if row["target_language"] else None,
            parse_summary=json.loads(str(row["parse_summary_json"])),
            translation_summary=json.loads(str(row["translation_summary_json"])),
            created_at=_parse_timestamp(str(row["created_at"])),
            updated_at=_parse_timestamp(str(row["updated_at"])),
        )

    def _map_segment(self, row: sqlite3.Row) -> SegmentRecord:
        return SegmentRecord(
            id=str(row["id"]),
            job_id=str(row["job_id"]),
            order_index=int(row["order_index"]),
            sheet_name=str(row["sheet_name"]),
            sheet_index=int(row["sheet_index"]),
            cell_address=str(row["cell_address"]),
            location_type=str(row["location_type"]),
            original_text=str(row["original_text"]),
            normalized_text=str(row["normalized_text"]),
            machine_translation=str(row["machine_translation"])
            if row["machine_translation"] is not None
            else None,
            edited_translation=str(row["edited_translation"])
            if row["edited_translation"] is not None
            else None,
            final_text=str(row["final_text"]) if row["final_text"] is not None else None,
            intermediate_translation=str(row["intermediate_translation"])
            if row["intermediate_translation"] is not None
            else None,
            status=str(row["status"]),
            warning_codes=json.loads(str(row["warning_codes_json"])),
            locator=json.loads(str(row["locator_json"])),
            error_message=str(row["error_message"]) if row["error_message"] is not None else None,
            created_at=_parse_timestamp(str(row["created_at"])),
            updated_at=_parse_timestamp(str(row["updated_at"])),
        )
