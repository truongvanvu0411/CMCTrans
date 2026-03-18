from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.database import connect_database, initialize_database
from backend.app.services.kb_dataset_import import (
    KnowledgeDatasetRecord,
    build_translation_memory_pairs,
    import_datasets_into_translation_memory,
    load_dataset_records,
)


class KnowledgeDatasetImportTests(unittest.TestCase):
    def test_build_translation_memory_pairs_creates_all_directional_pairs(self) -> None:
        records = load_dataset_records_from_payloads(
            [
                [
                    {
                        "ja": "音声テキスト変換",
                        "en": "speech to text",
                        "vi": "chuyen giong noi thanh van ban",
                    }
                ]
            ]
        )

        pairs = build_translation_memory_pairs(records)

        self.assertEqual(len(pairs), 6)
        self.assertEqual(
            pairs[("ja", "en", "音声テキスト変換")],
            "speech to text",
        )
        self.assertEqual(
            pairs[("vi", "ja", "chuyen giong noi thanh van ban")],
            "音声テキスト変換",
        )

    def test_import_datasets_into_translation_memory_upserts_pairs_and_writes_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            database_path = temp_path / "workspace" / "app.db"
            backup_path = temp_path / "workspace" / "app.backup.db"
            dataset_dir = temp_path / "kb_input"
            dataset_dir.mkdir(parents=True, exist_ok=True)

            connection = connect_database(database_path)
            try:
                initialize_database(connection)
            finally:
                connection.close()

            first_dataset = dataset_dir / "first.json"
            first_dataset.write_text(
                json.dumps(
                    [
                        {
                            "ja": "監査ログ",
                            "en": "audit log",
                            "vi": "nhat ky kiem toan",
                        },
                        {
                            "ja": "音声テキスト変換",
                            "en": "speech to text",
                            "vi": "chuyen giong noi thanh van ban",
                        },
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            second_dataset = dataset_dir / "second.json"
            second_dataset.write_text(
                json.dumps(
                    [
                        {
                            "ja": "監査ログ",
                            "en": "audit trail",
                            "vi": "nhat ky kiem toan",
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            summary = import_datasets_into_translation_memory(
                database_path=database_path,
                dataset_paths=[first_dataset, second_dataset],
                backup_path=backup_path,
            )

            self.assertEqual(summary.dataset_files, 2)
            self.assertEqual(summary.dataset_records, 3)
            self.assertEqual(summary.imported_pairs, 14)
            self.assertTrue(backup_path.exists())

            connection = sqlite3.connect(database_path)
            try:
                row_count = connection.execute(
                    "SELECT COUNT(*) FROM translation_memory"
                ).fetchone()[0]
                updated_value = connection.execute(
                    """
                    SELECT translated_text
                    FROM translation_memory
                    WHERE source_language = 'ja'
                      AND target_language = 'en'
                      AND source_text = '監査ログ'
                    """
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(summary.translation_memory_rows, 14)
            self.assertEqual(row_count, 14)
            self.assertEqual(updated_value, "audit trail")


def load_dataset_records_from_payloads(
    payloads: list[list[dict[str, str]]],
) -> list[KnowledgeDatasetRecord]:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dataset_paths: list[Path] = []
        for index, payload in enumerate(payloads):
            dataset_path = temp_path / f"dataset-{index}.json"
            dataset_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            dataset_paths.append(dataset_path)
        return load_dataset_records(dataset_paths)


if __name__ == "__main__":
    unittest.main()
