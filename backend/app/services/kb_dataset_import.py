from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import permutations
from pathlib import Path

from ..database import connect_database, initialize_database
from ..memory_repository import TranslationMemoryRepository
from .text_quality import normalize_text_for_lookup

SUPPORTED_DATASET_LANGUAGES = ("ja", "en", "vi")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class KnowledgeDatasetImportError(Exception):
    """Raised when a KB dataset file cannot be imported."""


@dataclass(frozen=True)
class KnowledgeDatasetRecord:
    ja: str
    en: str
    vi: str

    def value_for(self, language: str) -> str:
        if language == "ja":
            return self.ja
        if language == "en":
            return self.en
        if language == "vi":
            return self.vi
        raise KnowledgeDatasetImportError(f"Unsupported dataset language: {language}.")


@dataclass(frozen=True)
class KnowledgeDatasetImportSummary:
    dataset_files: int
    dataset_records: int
    imported_pairs: int
    translation_memory_rows: int
    backup_path: Path | None


def load_dataset_records(dataset_paths: list[Path]) -> list[KnowledgeDatasetRecord]:
    records: list[KnowledgeDatasetRecord] = []
    for dataset_path in dataset_paths:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise KnowledgeDatasetImportError(
                f"{dataset_path} must contain a top-level JSON list."
            )
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise KnowledgeDatasetImportError(
                    f"{dataset_path} entry {index} must be a JSON object."
                )
            normalized_values = {
                language: normalize_text_for_lookup(str(item.get(language, "")))
                for language in SUPPORTED_DATASET_LANGUAGES
            }
            if not all(normalized_values.values()):
                raise KnowledgeDatasetImportError(
                    f"{dataset_path} entry {index} must include non-empty ja/en/vi values."
                )
            records.append(
                KnowledgeDatasetRecord(
                    ja=normalized_values["ja"],
                    en=normalized_values["en"],
                    vi=normalized_values["vi"],
                )
            )
    return records


def build_translation_memory_pairs(
    records: list[KnowledgeDatasetRecord],
) -> dict[tuple[str, str, str], str]:
    pairs: dict[tuple[str, str, str], str] = {}
    for record in records:
        for source_language, target_language in permutations(
            SUPPORTED_DATASET_LANGUAGES,
            2,
        ):
            source_text = record.value_for(source_language)
            translated_text = record.value_for(target_language)
            pair_key = (source_language, target_language, source_text)
            pairs[pair_key] = translated_text
    return pairs


def import_datasets_into_translation_memory(
    *,
    database_path: Path,
    dataset_paths: list[Path],
    backup_path: Path | None,
) -> KnowledgeDatasetImportSummary:
    if not dataset_paths:
        raise KnowledgeDatasetImportError("At least one dataset path is required for import.")

    records = load_dataset_records(dataset_paths)
    translation_pairs = build_translation_memory_pairs(records)
    now = _utc_now()

    if backup_path is not None:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_bytes(database_path.read_bytes())

    connection = connect_database(database_path)
    try:
        initialize_database(connection)
        memory_repository = TranslationMemoryRepository(connection)
        for (source_language, target_language, source_text), translated_text in translation_pairs.items():
            memory_repository.upsert(
                entry_id=str(uuid.uuid4()),
                source_language=source_language,
                target_language=target_language,
                source_text=source_text,
                translated_text=translated_text,
                created_at=now,
                updated_at=now,
            )
        translation_memory_rows = _translation_memory_row_count(connection)
    finally:
        connection.close()

    return KnowledgeDatasetImportSummary(
        dataset_files=len(dataset_paths),
        dataset_records=len(records),
        imported_pairs=len(translation_pairs),
        translation_memory_rows=translation_memory_rows,
        backup_path=backup_path,
    )


def _translation_memory_row_count(connection: sqlite3.Connection) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM translation_memory").fetchone()[0])
