from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.frontend_delivery import register_frontend_delivery


class FrontendDeliveryTests(unittest.TestCase):
    def test_serves_brand_logo_from_configured_logo_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            frontend_dist_dir = temp_path / "dist"
            frontend_dist_dir.mkdir()
            (frontend_dist_dir / "index.html").write_text("<html><body>app</body></html>", encoding="utf-8")
            brand_logo_path = temp_path / "logo-trans.png"
            brand_logo_path.write_bytes(
                bytes.fromhex(
                    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
                    "0000000D49444154789C6360606060000000040001F61738550000000049454E44AE426082"
                )
            )

            app = FastAPI()
            register_frontend_delivery(
                app,
                frontend_dist_dir=frontend_dist_dir,
                brand_logo_path=brand_logo_path,
            )

            with TestClient(app) as client:
                response = client.get("/brand/logo-trans.png")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "image/png")
            self.assertEqual(response.content, brand_logo_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
