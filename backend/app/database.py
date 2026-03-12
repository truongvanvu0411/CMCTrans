from __future__ import annotations

import sqlite3
from pathlib import Path


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def connect_database(database_path: Path) -> sqlite3.Connection:
    ensure_parent_dir(database_path)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            original_file_name TEXT NOT NULL,
            original_file_path TEXT NOT NULL,
            output_file_path TEXT,
            file_type TEXT NOT NULL,
            status TEXT NOT NULL,
            current_step TEXT NOT NULL DEFAULT 'uploaded',
            progress_percent INTEGER NOT NULL DEFAULT 0,
            processed_segments INTEGER NOT NULL DEFAULT 0,
            total_segments INTEGER NOT NULL DEFAULT 0,
            status_message TEXT NOT NULL DEFAULT '',
            current_sheet TEXT,
            current_cell TEXT,
            preview_ready INTEGER NOT NULL DEFAULT 0,
            preview_summary_json TEXT NOT NULL DEFAULT '{}',
            source_language TEXT,
            target_language TEXT,
            parse_summary_json TEXT NOT NULL,
            translation_summary_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS segments (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            sheet_name TEXT NOT NULL,
            sheet_index INTEGER NOT NULL,
            cell_address TEXT NOT NULL,
            location_type TEXT NOT NULL,
            original_text TEXT NOT NULL,
            normalized_text TEXT NOT NULL,
            machine_translation TEXT,
            edited_translation TEXT,
            final_text TEXT,
            intermediate_translation TEXT,
            status TEXT NOT NULL,
            warning_codes_json TEXT NOT NULL,
            locator_json TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_segments_job_id ON segments(job_id);
        CREATE INDEX IF NOT EXISTS idx_segments_job_order ON segments(job_id, order_index);

        CREATE TABLE IF NOT EXISTS translation_memory (
            id TEXT PRIMARY KEY,
            source_language TEXT NOT NULL,
            target_language TEXT NOT NULL,
            source_text TEXT NOT NULL,
            translated_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_language, target_language, source_text)
        );

        CREATE INDEX IF NOT EXISTS idx_translation_memory_lookup
        ON translation_memory(source_language, target_language, source_text);

        CREATE TABLE IF NOT EXISTS glossary_exact_entries (
            id TEXT PRIMARY KEY,
            source_language TEXT NOT NULL,
            target_language TEXT NOT NULL,
            source_text TEXT NOT NULL,
            translated_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_language, target_language, source_text)
        );

        CREATE INDEX IF NOT EXISTS idx_glossary_exact_lookup
        ON glossary_exact_entries(source_language, target_language, source_text);

        CREATE TABLE IF NOT EXISTS glossary_protected_terms (
            id TEXT PRIMARY KEY,
            term TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS translation_corrections (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            segment_id TEXT NOT NULL,
            source_language TEXT NOT NULL,
            target_language TEXT NOT NULL,
            source_text TEXT NOT NULL,
            machine_translation TEXT,
            corrected_translation TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
            FOREIGN KEY(segment_id) REFERENCES segments(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_translation_corrections_job
        ON translation_corrections(job_id, created_at);
        """
    )
    _ensure_job_columns(connection)
    connection.commit()


def _ensure_job_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
    }
    required_columns = {
        "current_step": "TEXT NOT NULL DEFAULT 'uploaded'",
        "progress_percent": "INTEGER NOT NULL DEFAULT 0",
        "processed_segments": "INTEGER NOT NULL DEFAULT 0",
        "total_segments": "INTEGER NOT NULL DEFAULT 0",
        "status_message": "TEXT NOT NULL DEFAULT ''",
        "current_sheet": "TEXT",
        "current_cell": "TEXT",
        "preview_ready": "INTEGER NOT NULL DEFAULT 0",
        "preview_summary_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    for column_name, definition in required_columns.items():
        if column_name in existing_columns:
            continue
        connection.execute(f"ALTER TABLE jobs ADD COLUMN {column_name} {definition}")
