from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import AppConfig
from backend.app.main import create_app
from backend.tests.fakes import FakeTranslationService

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FrontendDeliveryTests(unittest.TestCase):
    def test_backend_serves_built_frontend_and_keeps_api_routes_working(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            frontend_dist_dir = temp_path / "frontend-dist"
            assets_dir = frontend_dist_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            (frontend_dist_dir / "index.html").write_text(
                "<!doctype html><html><body><div id='app'></div></body></html>",
                encoding="utf-8",
            )
            (assets_dir / "app.js").write_text("console.log('ok')", encoding="utf-8")
            config = AppConfig(
                root_dir=PROJECT_ROOT,
                models_dir=temp_path / "models",
                workspace_dir=temp_path / "workspace",
                database_path=temp_path / "workspace" / "app.db",
                frontend_dist_dir=frontend_dist_dir,
            )
            app = create_app(
                config=config,
                translation_service=FakeTranslationService(),
            )

            with TestClient(app) as client:
                index_response = client.get("/")
                self.assertEqual(index_response.status_code, 200)
                self.assertIn("<div id='app'></div>", index_response.text)

                asset_response = client.get("/assets/app.js")
                self.assertEqual(asset_response.status_code, 200)
                self.assertIn("console.log('ok')", asset_response.text)

                spa_response = client.get("/translated")
                self.assertEqual(spa_response.status_code, 200)
                self.assertIn("<div id='app'></div>", spa_response.text)

                api_response = client.get("/api/health")
                self.assertEqual(api_response.status_code, 200)
                self.assertEqual(api_response.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
