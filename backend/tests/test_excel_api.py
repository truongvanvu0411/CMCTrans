from __future__ import annotations

import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import AppConfig
from backend.app.main import create_app
from backend.app.services.ocr_layout import PillowOcrLayoutRenderer
from backend.tests.fakes import (
    FakeDocumentOcrService,
    FakeTranslationService,
    FlakyOcrLayoutRenderer,
)
from backend.tests.test_excel_ooxml import build_symbol_workbook, build_test_workbook
from backend.tests.test_ocr_document import (
    _resolve_test_font_path,
    build_test_ocr_image,
    build_test_ocr_pdf,
)
from backend.tests.test_pptx_ooxml import (
    build_overflow_presentation,
    build_smartart_presentation,
    build_test_presentation,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class BrokenOcrService:
    def parse_document(
        self,
        *,
        file_path: Path,
        file_type: str,
        source_language: str,
    ) -> object:
        raise RuntimeError("broken ocr runtime")


class ExcelApiTests(unittest.TestCase):
    def test_upload_start_edit_and_download_pdf_job(self) -> None:
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
                ocr_service=FakeDocumentOcrService(),
                ocr_layout_renderer=PillowOcrLayoutRenderer(font_path=_resolve_test_font_path()),
            )
            with TestClient(app) as client:
                upload_response = client.post(
                    "/api/excel/jobs/upload",
                    params={"file_name": "scan.pdf"},
                    content=build_test_ocr_pdf(),
                    headers={"Content-Type": "application/pdf"},
                )
                self.assertEqual(upload_response.status_code, 200)
                job_id = upload_response.json()["id"]
                self.assertEqual(upload_response.json()["file_type"], "pdf")

                source_document_response = client.get(
                    f"/api/excel/jobs/{job_id}/source-document"
                )
                self.assertEqual(source_document_response.status_code, 200)
                self.assertEqual(
                    source_document_response.headers["content-type"],
                    "application/pdf",
                )
                self.assertTrue(source_document_response.content.startswith(b"%PDF"))

                start_response = client.post(
                    f"/api/excel/jobs/{job_id}/start",
                    json={"source_language": "en", "target_language": "vi"},
                )
                self.assertEqual(start_response.status_code, 200)

                for _ in range(20):
                    job_state = client.get(f"/api/excel/jobs/{job_id}").json()
                    if job_state["status"] == "review":
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("PDF OCR job did not reach review state in time.")

                segments_response = client.get(f"/api/excel/jobs/{job_id}/segments")
                self.assertEqual(segments_response.status_code, 200)
                segments = segments_response.json()["items"]
                self.assertEqual(len(segments), 2)
                self.assertEqual(segments[0]["sheet_name"], "Page 1")
                self.assertEqual(segments[0]["cell_address"], "Block 1")
                self.assertEqual(segments[0]["location_type"], "ocr_text")
                self.assertEqual(segments[0]["final_text"], "VI::OCR PDF heading")

                edit_response = client.patch(
                    f"/api/excel/jobs/{job_id}/segments/{segments[0]['id']}",
                    json={"final_text": "Tieu de da sua"},
                )
                self.assertEqual(edit_response.status_code, 200)
                self.assertEqual(edit_response.json()["status"], "edited")

                prepare_download_response = client.post(
                    f"/api/excel/jobs/{job_id}/download"
                )
                self.assertEqual(prepare_download_response.status_code, 200)
                self.assertEqual(prepare_download_response.json()["file_name"], "scan.vi.pdf")

                completed_job = client.get(f"/api/excel/jobs/{job_id}").json()
                self.assertEqual(completed_job["status"], "completed")

                download_response = client.get(f"/api/excel/jobs/{job_id}/download")
                self.assertEqual(download_response.status_code, 200)
                self.assertEqual(download_response.headers["content-type"], "application/pdf")
                self.assertTrue(download_response.content.startswith(b"%PDF"))

    def test_upload_start_and_download_image_job(self) -> None:
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
                ocr_service=FakeDocumentOcrService(),
                ocr_layout_renderer=PillowOcrLayoutRenderer(font_path=_resolve_test_font_path()),
            )
            with TestClient(app) as client:
                upload_response = client.post(
                    "/api/excel/jobs/upload",
                    params={"file_name": "screen.png"},
                    content=build_test_ocr_image(),
                    headers={"Content-Type": "image/png"},
                )
                self.assertEqual(upload_response.status_code, 200)
                self.assertEqual(upload_response.json()["file_type"], "image")
                job_id = upload_response.json()["id"]

                source_document_response = client.get(
                    f"/api/excel/jobs/{job_id}/source-document"
                )
                self.assertEqual(source_document_response.status_code, 200)
                self.assertEqual(
                    source_document_response.headers["content-type"],
                    "image/png",
                )
                self.assertEqual(source_document_response.content[:8], b"\x89PNG\r\n\x1a\n")

                start_response = client.post(
                    f"/api/excel/jobs/{job_id}/start",
                    json={"source_language": "en", "target_language": "ja"},
                )
                self.assertEqual(start_response.status_code, 200)

                for _ in range(20):
                    job_state = client.get(f"/api/excel/jobs/{job_id}").json()
                    if job_state["status"] == "review":
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("Image OCR job did not reach review state in time.")

                segments_response = client.get(f"/api/excel/jobs/{job_id}/segments")
                self.assertEqual(segments_response.status_code, 200)
                segments = segments_response.json()["items"]
                self.assertEqual(len(segments), 1)
                self.assertEqual(segments[0]["sheet_name"], "Image 1")
                self.assertEqual(segments[0]["location_type"], "ocr_text")
                self.assertEqual(segments[0]["final_text"], "JA::OCR image text")

                prepare_download_response = client.post(
                    f"/api/excel/jobs/{job_id}/download"
                )
                self.assertEqual(prepare_download_response.status_code, 200)
                self.assertEqual(prepare_download_response.json()["file_name"], "screen.ja.png")

                completed_job = client.get(f"/api/excel/jobs/{job_id}").json()
                self.assertEqual(completed_job["status"], "completed")

                download_response = client.get(f"/api/excel/jobs/{job_id}/download")
                self.assertEqual(download_response.status_code, 200)
                self.assertEqual(download_response.headers["content-type"], "image/png")
                self.assertEqual(download_response.content[:8], b"\x89PNG\r\n\x1a\n")

    def test_pdf_job_reports_unexpected_ocr_runtime_errors(self) -> None:
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
                ocr_service=BrokenOcrService(),
                ocr_layout_renderer=PillowOcrLayoutRenderer(font_path=_resolve_test_font_path()),
            )
            with TestClient(app) as client:
                upload_response = client.post(
                    "/api/excel/jobs/upload",
                    params={"file_name": "broken.pdf"},
                    content=build_test_ocr_pdf(),
                    headers={"Content-Type": "application/pdf"},
                )
                self.assertEqual(upload_response.status_code, 200)
                job_id = upload_response.json()["id"]

                start_response = client.post(
                    f"/api/excel/jobs/{job_id}/start",
                    json={"source_language": "en", "target_language": "vi"},
                )
                self.assertEqual(start_response.status_code, 200)

                for _ in range(20):
                    job_state = client.get(f"/api/excel/jobs/{job_id}").json()
                    if job_state["status"] == "failed":
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("Broken OCR job did not reach failed state in time.")

                self.assertEqual(job_state["current_step"], "failed")
                self.assertIn("Unexpected processing error: broken ocr runtime", job_state["status_message"])

    def test_languages_endpoint_lists_reverse_routes(self) -> None:
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
                response = client.get("/api/languages")
                self.assertEqual(response.status_code, 200)
                payload = response.json()

                routes = {
                    item["source"]["code"]: [target["code"] for target in item["targets"]]
                    for item in payload
                }
                self.assertEqual(routes["ja"], ["en", "vi"])
                self.assertEqual(routes["en"], ["ja", "vi"])
                self.assertEqual(routes["vi"], ["en", "ja"])

    def test_translate_endpoint_supports_reverse_vi_to_ja_route(self) -> None:
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
                response = client.post(
                    "/api/translate",
                    json={
                        "text": "Tùy chọn",
                        "source_language": "vi",
                        "target_language": "ja",
                    },
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["translation"], "JA::Tùy chọn")
                self.assertEqual(payload["intermediate_translation"], "EN::Tùy chọn")
                self.assertEqual(payload["model_chain"], ["vi->en", "en->ja", "postprocess"])

    def test_translate_endpoint_auto_detects_mixed_language_text(self) -> None:
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
                english_response = client.post(
                    "/api/translate",
                    json={
                        "text": "OCR-AI SOLUTIONS",
                        "source_language": "vi",
                        "target_language": "ja",
                    },
                )
                self.assertEqual(english_response.status_code, 200)
                self.assertEqual(english_response.json()["translation"], "JA::OCR-AI SOLUTIONS")
                self.assertEqual(
                    english_response.json()["model_chain"],
                    ["en->ja", "postprocess"],
                )

                japanese_response = client.post(
                    "/api/translate",
                    json={
                        "text": "自然言語処理",
                        "source_language": "vi",
                        "target_language": "ja",
                    },
                )
                self.assertEqual(japanese_response.status_code, 200)
                self.assertEqual(japanese_response.json()["translation"], "自然言語処理")
                self.assertEqual(
                    japanese_response.json()["model_chain"],
                    ["passthrough:ja->ja"],
                )

    def test_upload_start_and_download_pptx_job_without_preview(self) -> None:
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
                upload_response = client.post(
                    "/api/excel/jobs/upload",
                    params={"file_name": "deck.pptx"},
                    content=build_test_presentation(),
                    headers={
                        "Content-Type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                    },
                )
                self.assertEqual(upload_response.status_code, 200)
                job_payload = upload_response.json()
                self.assertEqual(job_payload["file_type"], "pptx")
                self.assertEqual(job_payload["status"], "uploaded")
                job_id = job_payload["id"]

                start_response = client.post(
                    f"/api/excel/jobs/{job_id}/start",
                    json={"source_language": "ja", "target_language": "vi"},
                )
                self.assertEqual(start_response.status_code, 200)

                for _ in range(20):
                    job_state = client.get(f"/api/excel/jobs/{job_id}").json()
                    if job_state["status"] == "review":
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("PPTX job did not reach review state in time.")

                segments_payload = client.get(f"/api/excel/jobs/{job_id}/segments").json()
                self.assertEqual(segments_payload["total"], 8)
                self.assertEqual(segments_payload["items"][0]["location_type"], "shape_text")
                self.assertEqual(segments_payload["items"][0]["final_text"], "VI::こんにちは")

                prepare_download_response = client.post(
                    f"/api/excel/jobs/{job_id}/download"
                )
                self.assertEqual(prepare_download_response.status_code, 200)
                download_response = client.get(f"/api/excel/jobs/{job_id}/download")
                self.assertEqual(download_response.status_code, 200)
                self.assertEqual(
                    download_response.headers["content-type"],
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )

    def test_upload_start_review_job_supports_reverse_vi_to_ja_route(self) -> None:
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
                upload_response = client.post(
                    "/api/excel/jobs/upload",
                    params={"file_name": "sample.xlsx"},
                    content=build_test_workbook(),
                    headers={
                        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    },
                )
                self.assertEqual(upload_response.status_code, 200)
                job_id = upload_response.json()["id"]

                start_response = client.post(
                    f"/api/excel/jobs/{job_id}/start",
                    json={"source_language": "vi", "target_language": "ja"},
                )
                self.assertEqual(start_response.status_code, 200)
                self.assertIn(start_response.json()["status"], {"queued", "parsing"})

                for _ in range(20):
                    job_state = client.get(f"/api/excel/jobs/{job_id}").json()
                    if job_state["status"] == "review":
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("Reverse route job did not reach review state in time.")

                translated_segments = client.get(f"/api/excel/jobs/{job_id}/segments").json()["items"]
                first_segment = translated_segments[0]
                self.assertEqual(first_segment["machine_translation"], "こんにちは")
                self.assertEqual(first_segment["final_text"], "こんにちは")
                self.assertIsNone(first_segment["intermediate_translation"])

    def test_pptx_preview_marks_layout_review_on_overflowing_text(self) -> None:
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
                upload_response = client.post(
                    "/api/excel/jobs/upload",
                    params={"file_name": "overflow.pptx"},
                    content=build_overflow_presentation(),
                    headers={
                        "Content-Type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                    },
                )
                self.assertEqual(upload_response.status_code, 200)
                job_id = upload_response.json()["id"]

                start_response = client.post(
                    f"/api/excel/jobs/{job_id}/start",
                    json={"source_language": "ja", "target_language": "vi"},
                )
                self.assertEqual(start_response.status_code, 200)

                for _ in range(20):
                    job_state = client.get(f"/api/excel/jobs/{job_id}").json()
                    if job_state["status"] == "review":
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("Overflow PPTX job did not reach review state in time.")

                segment = client.get(f"/api/excel/jobs/{job_id}/segments").json()["items"][0]
                edit_response = client.patch(
                    f"/api/excel/jobs/{job_id}/segments/{segment['id']}",
                    json={
                        "final_text": "Đây là một đoạn văn bản rất dài sẽ không thể nằm gọn trong hộp chữ hẹp này."
                    },
                )
                self.assertEqual(edit_response.status_code, 200)

                preview_response = client.post(f"/api/excel/jobs/{job_id}/preview")
                self.assertEqual(preview_response.status_code, 200)
                preview_summary = preview_response.json()["summary"]
                self.assertEqual(preview_summary["kind"], "pptx")
                self.assertEqual(len(preview_summary["layout_warnings"]), 1)

                segments_response = client.get(f"/api/excel/jobs/{job_id}/segments")
                self.assertEqual(segments_response.status_code, 200)
                updated_segment = segments_response.json()["items"][0]
                self.assertIn("layout_review_required", updated_segment["warning_codes"])

    def test_image_download_failure_keeps_job_in_review_and_allows_retry(self) -> None:
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
                ocr_service=FakeDocumentOcrService(),
                ocr_layout_renderer=FlakyOcrLayoutRenderer(),
            )
            with TestClient(app) as client:
                upload_response = client.post(
                    "/api/excel/jobs/upload",
                    params={"file_name": "retry.png"},
                    content=build_test_ocr_image(),
                    headers={"Content-Type": "image/png"},
                )
                self.assertEqual(upload_response.status_code, 200)
                job_id = upload_response.json()["id"]

                start_response = client.post(
                    f"/api/excel/jobs/{job_id}/start",
                    json={"source_language": "en", "target_language": "ja"},
                )
                self.assertEqual(start_response.status_code, 200)

                for _ in range(20):
                    job_state = client.get(f"/api/excel/jobs/{job_id}").json()
                    if job_state["status"] == "review":
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("Image OCR retry job did not reach review state in time.")

                first_download_response = client.post(f"/api/excel/jobs/{job_id}/download")
                self.assertEqual(first_download_response.status_code, 400)
                self.assertIn(
                    "translated text does not fit inside its detected layout box",
                    first_download_response.text,
                )

                failed_export_job = client.get(f"/api/excel/jobs/{job_id}").json()
                self.assertEqual(failed_export_job["status"], "review")
                self.assertEqual(failed_export_job["current_step"], "review")
                self.assertIn(
                    "translated text does not fit inside its detected layout box",
                    failed_export_job["status_message"],
                )

                retry_download_response = client.post(f"/api/excel/jobs/{job_id}/download")
                self.assertEqual(retry_download_response.status_code, 200)
                self.assertEqual(retry_download_response.json()["file_name"], "retry.ja.png")

                completed_job = client.get(f"/api/excel/jobs/{job_id}").json()
                self.assertEqual(completed_job["status"], "completed")

                download_response = client.get(f"/api/excel/jobs/{job_id}/download")
                self.assertEqual(download_response.status_code, 200)
                self.assertEqual(download_response.headers["content-type"], "image/png")

    def test_upload_start_and_download_smartart_pptx_job_without_preview(self) -> None:
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
                upload_response = client.post(
                    "/api/excel/jobs/upload",
                    params={"file_name": "smartart.pptx"},
                    content=build_smartart_presentation(),
                    headers={
                        "Content-Type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                    },
                )
                self.assertEqual(upload_response.status_code, 200)
                job_id = upload_response.json()["id"]

                start_response = client.post(
                    f"/api/excel/jobs/{job_id}/start",
                    json={"source_language": "ja", "target_language": "vi"},
                )
                self.assertEqual(start_response.status_code, 200)

                for _ in range(20):
                    job_state = client.get(f"/api/excel/jobs/{job_id}").json()
                    if job_state["status"] == "review":
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("SmartArt PPTX job did not reach review state in time.")

                segments_payload = client.get(f"/api/excel/jobs/{job_id}/segments").json()
                self.assertEqual(segments_payload["total"], 2)
                self.assertEqual(segments_payload["items"][0]["location_type"], "smartart_text")
                self.assertEqual(segments_payload["items"][0]["final_text"], "VI::顧客管理")

                prepare_download_response = client.post(f"/api/excel/jobs/{job_id}/download")
                self.assertEqual(prepare_download_response.status_code, 200)
                download_response = client.get(f"/api/excel/jobs/{job_id}/download")
                self.assertEqual(download_response.status_code, 200)

    def test_upload_start_review_edit_and_download_job_without_preview(self) -> None:
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
                upload_response = client.post(
                    "/api/excel/jobs/upload",
                    params={"file_name": "sample.xlsx"},
                    content=build_test_workbook(),
                    headers={
                        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    },
                )
                self.assertEqual(upload_response.status_code, 200)
                job_payload = upload_response.json()
                self.assertEqual(job_payload["status"], "uploaded")
                self.assertEqual(job_payload["current_step"], "uploaded")
                job_id = job_payload["id"]

                segments_response = client.get(f"/api/excel/jobs/{job_id}/segments")
                self.assertEqual(segments_response.status_code, 200)
                segments_payload = segments_response.json()
                self.assertEqual(segments_payload["total"], 0)

                start_response = client.post(
                    f"/api/excel/jobs/{job_id}/start",
                    json={"source_language": "ja", "target_language": "vi"},
                )
                self.assertEqual(start_response.status_code, 200)
                self.assertIn(start_response.json()["status"], {"queued", "parsing"})

                for _ in range(20):
                    job_state = client.get(f"/api/excel/jobs/{job_id}").json()
                    if job_state["status"] == "review":
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("Job did not reach review state in time.")

                translated_segments = client.get(f"/api/excel/jobs/{job_id}/segments").json()["items"]
                first_segment = translated_segments[0]
                self.assertEqual(first_segment["final_text"], "VI::こんにちは")
                self.assertEqual(first_segment["intermediate_translation"], "EN::こんにちは")

                edit_response = client.patch(
                    f"/api/excel/jobs/{job_id}/segments/{first_segment['id']}",
                    json={"final_text": "User fixed translation"},
                )
                self.assertEqual(edit_response.status_code, 200)
                self.assertEqual(edit_response.json()["status"], "edited")
                self.assertEqual(
                    edit_response.json()["final_text"],
                    "User fixed translation",
                )

                history_response = client.get("/api/excel/jobs")
                self.assertEqual(history_response.status_code, 200)
                history_items = history_response.json()
                self.assertEqual(history_items[0]["id"], job_id)

                reopened_segments = client.get(f"/api/excel/jobs/{job_id}/segments").json()["items"]
                reopened_first = next(
                    segment for segment in reopened_segments if segment["id"] == first_segment["id"]
                )
                self.assertEqual(reopened_first["status"], "edited")
                self.assertEqual(reopened_first["final_text"], "User fixed translation")

                prepare_download_response = client.post(
                    f"/api/excel/jobs/{job_id}/download"
                )
                self.assertEqual(prepare_download_response.status_code, 200)
                download_response = client.get(f"/api/excel/jobs/{job_id}/download")
                self.assertEqual(download_response.status_code, 200)
                self.assertEqual(
                    download_response.headers["content-type"],
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    def test_delete_job_removes_database_record_and_workspace_files(self) -> None:
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
                upload_response = client.post(
                    "/api/excel/jobs/upload",
                    params={"file_name": "sample.xlsx"},
                    content=build_test_workbook(),
                    headers={
                        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    },
                )
                self.assertEqual(upload_response.status_code, 200)
                job_payload = upload_response.json()
                job_id = job_payload["id"]
                job_dir = config.workspace_dir / "jobs" / job_id
                self.assertTrue(job_dir.exists())

                delete_response = client.delete(f"/api/excel/jobs/{job_id}")
                self.assertEqual(delete_response.status_code, 204)
                self.assertFalse(job_dir.exists())

                list_response = client.get("/api/excel/jobs")
                self.assertEqual(list_response.status_code, 200)
                self.assertEqual(list_response.json(), [])

    def test_edited_translation_is_reused_from_translation_memory(self) -> None:
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
                first_upload = client.post(
                    "/api/excel/jobs/upload",
                    params={"file_name": "memory-1.xlsx"},
                    content=build_test_workbook(),
                    headers={
                        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    },
                )
                self.assertEqual(first_upload.status_code, 200)
                first_job_id = first_upload.json()["id"]

                first_start = client.post(
                    f"/api/excel/jobs/{first_job_id}/start",
                    json={"source_language": "ja", "target_language": "vi"},
                )
                self.assertEqual(first_start.status_code, 200)

                for _ in range(20):
                    first_state = client.get(f"/api/excel/jobs/{first_job_id}").json()
                    if first_state["status"] == "review":
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("First job did not reach review state in time.")

                first_segments = client.get(f"/api/excel/jobs/{first_job_id}/segments").json()["items"]
                first_segment = first_segments[0]
                edit_response = client.patch(
                    f"/api/excel/jobs/{first_job_id}/segments/{first_segment['id']}",
                    json={"final_text": "User glossary translation"},
                )
                self.assertEqual(edit_response.status_code, 200)
                connection = sqlite3.connect(config.database_path)
                try:
                    correction_rows = connection.execute(
                        """
                        SELECT source_text, machine_translation, corrected_translation
                        FROM translation_corrections
                        """
                    ).fetchall()
                finally:
                    connection.close()
                self.assertEqual(len(correction_rows), 1)
                self.assertEqual(correction_rows[0][0], "こんにちは")
                self.assertEqual(correction_rows[0][1], "VI::こんにちは")
                self.assertEqual(correction_rows[0][2], "User glossary translation")
                source_text = correction_rows[0][0]
                connection = sqlite3.connect(config.database_path)
                try:
                    memory_rows = connection.execute(
                        """
                        SELECT source_language, target_language, source_text, translated_text
                        FROM translation_memory
                        ORDER BY source_language, target_language, source_text
                        """
                    ).fetchall()
                finally:
                    connection.close()
                self.assertIn(
                    ("ja", "vi", source_text, "User glossary translation"),
                    memory_rows,
                )
                self.assertIn(
                    ("vi", "ja", "User glossary translation", source_text),
                    memory_rows,
                )

                second_upload = client.post(
                    "/api/excel/jobs/upload",
                    params={"file_name": "memory-2.xlsx"},
                    content=build_test_workbook(),
                    headers={
                        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    },
                )
                self.assertEqual(second_upload.status_code, 200)
                second_job_id = second_upload.json()["id"]

                second_start = client.post(
                    f"/api/excel/jobs/{second_job_id}/start",
                    json={"source_language": "ja", "target_language": "vi"},
                )
                self.assertEqual(second_start.status_code, 200)

                for _ in range(20):
                    second_state = client.get(f"/api/excel/jobs/{second_job_id}").json()
                    if second_state["status"] == "review":
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("Second job did not reach review state in time.")

                second_segments = client.get(f"/api/excel/jobs/{second_job_id}/segments").json()["items"]
                self.assertEqual(second_segments[0]["final_text"], "User glossary translation")
                self.assertEqual(second_segments[0]["machine_translation"], "User glossary translation")

    def test_symbol_edits_are_not_persisted_to_translation_memory_or_corrections(self) -> None:
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
                upload_response = client.post(
                    "/api/excel/jobs/upload",
                    params={"file_name": "symbols.xlsx"},
                    content=build_symbol_workbook(),
                    headers={
                        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    },
                )
                self.assertEqual(upload_response.status_code, 200)
                job_id = upload_response.json()["id"]

                start_response = client.post(
                    f"/api/excel/jobs/{job_id}/start",
                    json={"source_language": "ja", "target_language": "vi"},
                )
                self.assertEqual(start_response.status_code, 200)

                for _ in range(20):
                    job_state = client.get(f"/api/excel/jobs/{job_id}").json()
                    if job_state["status"] == "review":
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("Job did not reach review state in time.")

                segments = client.get(f"/api/excel/jobs/{job_id}/segments").json()["items"]
                symbol_segment = next(segment for segment in segments if segment["cell_address"] == "A1")
                self.assertEqual(symbol_segment["machine_translation"], "O")

                edit_response = client.patch(
                    f"/api/excel/jobs/{job_id}/segments/{symbol_segment['id']}",
                    json={"final_text": "O O O"},
                )
                self.assertEqual(edit_response.status_code, 200)

                connection = sqlite3.connect(config.database_path)
                try:
                    memory_rows = connection.execute(
                        "SELECT source_text, translated_text FROM translation_memory"
                    ).fetchall()
                    correction_rows = connection.execute(
                        """
                        SELECT source_text, corrected_translation
                        FROM translation_corrections
                        """
                    ).fetchall()
                finally:
                    connection.close()

                self.assertEqual(memory_rows, [])
                self.assertEqual(correction_rows, [])


if __name__ == "__main__":
    unittest.main()
