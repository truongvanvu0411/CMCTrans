from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import AppConfig
from backend.app.main import create_app
from backend.tests.auth_helpers import authenticate_client
from backend.tests.fakes import FakeTranslationService

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class KnowledgeApiTests(unittest.TestCase):
    def test_list_seeded_knowledge_and_manage_glossary_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config = AppConfig(
                root_dir=PROJECT_ROOT,
                models_dir=temp_path / "models",
                workspace_dir=temp_path / "workspace",
                database_path=temp_path / "workspace" / "app.db",
            )
            app = create_app(
                config=config,
                translation_service=FakeTranslationService(),
            )
            with TestClient(app) as client:
                authenticate_client(client)
                summary_response = client.get("/api/knowledge/summary")
                self.assertEqual(summary_response.status_code, 200)
                summary_payload = summary_response.json()
                self.assertGreater(summary_payload["glossary_count"], 0)
                self.assertGreater(summary_payload["protected_term_count"], 0)

                glossary_response = client.get("/api/knowledge/glossary")
                self.assertEqual(glossary_response.status_code, 200)
                glossary_payload = glossary_response.json()
                self.assertTrue(
                    any(entry["source_text"] == "監査ログ" for entry in glossary_payload)
                )

                created_glossary = client.post(
                    "/api/knowledge/glossary",
                    json={
                        "source_language": "ja",
                        "target_language": "vi",
                        "source_text": "監査ログビュー",
                        "translated_text": "Màn hình nhật ký kiểm toán",
                    },
                )
                self.assertEqual(created_glossary.status_code, 200)
                created_glossary_payload = created_glossary.json()
                self.assertEqual(
                    created_glossary_payload["translated_text"],
                    "Màn hình nhật ký kiểm toán",
                )

                updated_glossary = client.post(
                    "/api/knowledge/glossary",
                    json={
                        "id": created_glossary_payload["id"],
                        "source_language": "ja",
                        "target_language": "vi",
                        "source_text": "監査ログビュー",
                        "translated_text": "Audit Log View",
                    },
                )
                self.assertEqual(updated_glossary.status_code, 200)
                self.assertEqual(updated_glossary.json()["translated_text"], "Audit Log View")

                protected_term = client.post(
                    "/api/knowledge/protected-terms",
                    json={"term": "OpenSearch"},
                )
                self.assertEqual(protected_term.status_code, 200)
                protected_term_payload = protected_term.json()
                self.assertEqual(protected_term_payload["term"], "OpenSearch")

                memory_entry = client.post(
                    "/api/knowledge/memory",
                    json={
                        "source_language": "ja",
                        "target_language": "vi",
                        "source_text": "購買依頼管理",
                        "translated_text": "Quản lý yêu cầu mua hàng",
                    },
                )
                self.assertEqual(memory_entry.status_code, 200)
                memory_payload = memory_entry.json()
                self.assertEqual(memory_payload["source_text"], "購買依頼管理")

                memory_list = client.get("/api/knowledge/memory")
                self.assertEqual(memory_list.status_code, 200)
                self.assertTrue(
                    any(entry["id"] == memory_payload["id"] for entry in memory_list.json())
                )

                delete_memory = client.delete(f"/api/knowledge/memory/{memory_payload['id']}")
                self.assertEqual(delete_memory.status_code, 204)

                delete_glossary = client.delete(
                    f"/api/knowledge/glossary/{created_glossary_payload['id']}"
                )
                self.assertEqual(delete_glossary.status_code, 204)

                delete_protected = client.delete(
                    f"/api/knowledge/protected-terms/{protected_term_payload['id']}"
                )
                self.assertEqual(delete_protected.status_code, 204)

    def test_duplicate_glossary_entry_updates_existing_translation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config = AppConfig(
                root_dir=PROJECT_ROOT,
                models_dir=temp_path / "models",
                workspace_dir=temp_path / "workspace",
                database_path=temp_path / "workspace" / "app.db",
            )
            app = create_app(
                config=config,
                translation_service=FakeTranslationService(),
            )
            with TestClient(app) as client:
                authenticate_client(client)
                first_response = client.post(
                    "/api/knowledge/glossary",
                    json={
                        "source_language": "ja",
                        "target_language": "vi",
                        "source_text": "内部監査",
                        "translated_text": "Kiểm toán nội bộ",
                    },
                )
                self.assertEqual(first_response.status_code, 200)

                second_response = client.post(
                    "/api/knowledge/glossary",
                    json={
                        "source_language": "ja",
                        "target_language": "vi",
                        "source_text": "内部監査",
                        "translated_text": "Audit nội bộ",
                    },
                )
                self.assertEqual(second_response.status_code, 200)
                self.assertEqual(second_response.json()["translated_text"], "Audit nội bộ")

    def test_save_memory_entry_creates_bidirectional_translation_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config = AppConfig(
                root_dir=PROJECT_ROOT,
                models_dir=temp_path / "models",
                workspace_dir=temp_path / "workspace",
                database_path=temp_path / "workspace" / "app.db",
            )
            app = create_app(
                config=config,
                translation_service=FakeTranslationService(),
            )
            with TestClient(app) as client:
                authenticate_client(client)
                response = client.post(
                    "/api/knowledge/memory",
                    json={
                        "source_language": "ja",
                        "target_language": "vi",
                        "source_text": "受注管理",
                        "translated_text": "Quan ly don hang",
                    },
                )
                self.assertEqual(response.status_code, 200)

                connection = sqlite3.connect(config.database_path)
                try:
                    rows = connection.execute(
                        """
                        SELECT source_language, target_language, source_text, translated_text
                        FROM translation_memory
                        ORDER BY source_language, target_language, source_text
                        """
                    ).fetchall()
                finally:
                    connection.close()

                self.assertIn(("ja", "vi", "受注管理", "Quan ly don hang"), rows)
                self.assertIn(("vi", "ja", "Quan ly don hang", "受注管理"), rows)


if __name__ == "__main__":
    unittest.main()
