from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import AppConfig
from backend.app.main import create_app
from backend.tests.auth_helpers import authenticate_client
from backend.tests.fakes import FakeTranslationService
from backend.tests.test_excel_ooxml import build_test_workbook


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AuthApiTests(unittest.TestCase):
    def test_login_succeeds_without_loading_translation_models_at_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config = AppConfig(
                root_dir=PROJECT_ROOT,
                models_dir=temp_path / "models",
                workspace_dir=temp_path / "workspace",
                database_path=temp_path / "workspace" / "app.db",
            )
            app = create_app(config=config)
            with TestClient(app) as client:
                login_response = client.post(
                    "/api/auth/login",
                    json={"username": "admin", "password": "admin123!"},
                )
                self.assertEqual(login_response.status_code, 200)
                self.assertEqual(login_response.json()["user"]["username"], "admin")

    def test_login_session_and_admin_account_crud(self) -> None:
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
                admin_session = authenticate_client(client)
                self.assertEqual(admin_session["user"]["role"], "admin")

                session_response = client.get("/api/auth/session")
                self.assertEqual(session_response.status_code, 200)
                self.assertEqual(session_response.json()["user"]["username"], "admin")

                create_user_response = client.post(
                    "/api/admin/accounts",
                    json={
                        "username": "member.user",
                        "role": "user",
                        "is_active": True,
                        "password": "member123!",
                    },
                )
                self.assertEqual(create_user_response.status_code, 200)
                created_user = create_user_response.json()
                self.assertEqual(created_user["username"], "member.user")
                self.assertEqual(created_user["role"], "user")

                activity_response = client.get(
                    "/api/admin/activity",
                    params={"action_type": "account_save", "query": "member.user"},
                )
                self.assertEqual(activity_response.status_code, 200)
                activity_payload = activity_response.json()
                self.assertEqual(activity_payload["total"], 1)
                self.assertEqual(activity_payload["items"][0]["target_id"], created_user["id"])

                delete_response = client.delete(f"/api/admin/accounts/{created_user['id']}")
                self.assertEqual(delete_response.status_code, 204)

    def test_regular_user_cannot_access_admin_endpoints_and_only_sees_own_jobs(self) -> None:
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
                create_user_response = client.post(
                    "/api/admin/accounts",
                    json={
                        "username": "user.one",
                        "role": "user",
                        "is_active": True,
                        "password": "userpass1!",
                    },
                )
                self.assertEqual(create_user_response.status_code, 200)
                client.headers.pop("Authorization", None)
                authenticate_client(client, username="user.one", password="userpass1!")
                knowledge_response = client.get("/api/knowledge/summary")
                self.assertEqual(knowledge_response.status_code, 403)

                upload_response = client.post(
                    "/api/excel/jobs/upload",
                    params={"file_name": "owned.xlsx"},
                    content=build_test_workbook(),
                    headers={
                        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    },
                )
                self.assertEqual(upload_response.status_code, 200)
                owned_job_id = upload_response.json()["id"]

                jobs_response = client.get("/api/excel/jobs")
                self.assertEqual(jobs_response.status_code, 200)
                self.assertEqual(len(jobs_response.json()), 1)
                self.assertEqual(jobs_response.json()[0]["id"], owned_job_id)
                client.headers.pop("Authorization", None)
                authenticate_client(client)
                admin_jobs_response = client.get("/api/excel/jobs")
                self.assertEqual(admin_jobs_response.status_code, 200)
                self.assertEqual(len(admin_jobs_response.json()), 1)


if __name__ == "__main__":
    unittest.main()
