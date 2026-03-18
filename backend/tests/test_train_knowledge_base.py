from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import scripts.train_knowledge_base as train_knowledge_base


class TrainKnowledgeBaseScriptTests(TestCase):
    def test_console_safe_text_escapes_unencodable_file_names(self) -> None:
        rendered = train_knowledge_base._console_safe_text(
            "App Point Hội viên_Estimate.xlsx",
            "cp932",
        )

        self.assertEqual("App Point H\\u1ed9i vi\\xean_Estimate.xlsx", rendered)

    def test_plan_file_uses_file_name_detection_for_pdf(self) -> None:
        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "ATS様向け_お見積書.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")

            plan = train_knowledge_base._plan_file(pdf_path)

        self.assertEqual("pdf", plan.file_type)
        self.assertIsNone(plan.segment_count)
        self.assertEqual("ja", plan.detected_source_language)
        self.assertIsNone(plan.skipped_reason)

    def test_run_saves_corrected_translation_to_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            input_dir = temp_root / "input"
            run_dir = temp_root / "run"
            input_dir.mkdir()
            sample_path = input_dir / "sample.pptx"
            sample_path.write_bytes(b"pptx")
            plan = train_knowledge_base.FilePlan(
                path=sample_path,
                file_type="pptx",
                segment_count=1,
                detected_source_language="ja",
                skipped_reason=None,
            )
            segment_payload = {
                "id": "segment-1",
                "sheet_name": "Slide 1",
                "cell_address": "A1",
                "location_type": "text",
                "original_text": "質問へ自動回答する",
                "final_text": "Automatically answer employee questions",
            }

            with (
                patch.object(train_knowledge_base, "_fetch_protected_terms", return_value=set()),
                patch.object(train_knowledge_base, "_plan_file", return_value=plan),
                patch.object(train_knowledge_base, "_upload_job", return_value="job-1"),
                patch.object(train_knowledge_base, "_start_job"),
                patch.object(train_knowledge_base, "_wait_for_review", return_value={"status": "review"}),
                patch.object(train_knowledge_base, "_fetch_segments", return_value=[segment_payload]),
                patch.object(
                    train_knowledge_base,
                    "_review_translation",
                    return_value=("Tự động trả lời câu hỏi", []),
                ),
                patch.object(train_knowledge_base, "_update_segment") as update_segment_mock,
                patch.object(train_knowledge_base, "_save_memory_entry") as save_memory_entry_mock,
                patch.object(
                    train_knowledge_base,
                    "_prepare_download",
                    side_effect=train_knowledge_base.ApiError("download is optional during training"),
                ),
                patch.object(train_knowledge_base, "_download_output"),
            ):
                exit_code = train_knowledge_base.run(
                    [
                        "--api-base",
                        "http://example.test",
                        "--input-dir",
                        str(input_dir),
                        "--run-dir",
                        str(run_dir),
                    ]
                )

        self.assertEqual(0, exit_code)
        update_segment_mock.assert_called_once_with(
            "http://example.test",
            "job-1",
            "segment-1",
            "Tự động trả lời câu hỏi",
        )
        save_memory_entry_mock.assert_called_once_with(
            base_url="http://example.test",
            source_language="ja",
            target_language="vi",
            source_text="質問へ自動回答する",
            translated_text="Tự động trả lời câu hỏi",
        )

    def test_run_continues_after_a_failed_file_and_marks_exit_code(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            input_dir = temp_root / "input"
            run_dir = temp_root / "run"
            input_dir.mkdir()
            first_path = input_dir / "first.pptx"
            second_path = input_dir / "second.pptx"
            first_path.write_bytes(b"first")
            second_path.write_bytes(b"second")
            plans = {
                first_path: train_knowledge_base.FilePlan(
                    path=first_path,
                    file_type="pptx",
                    segment_count=1,
                    detected_source_language="ja",
                    skipped_reason=None,
                ),
                second_path: train_knowledge_base.FilePlan(
                    path=second_path,
                    file_type="pptx",
                    segment_count=1,
                    detected_source_language="ja",
                    skipped_reason=None,
                ),
            }
            segment_payload = {
                "id": "segment-2",
                "sheet_name": "Slide 1",
                "cell_address": "A2",
                "location_type": "text",
                "original_text": "クラウド移行",
                "final_text": "Chuyển đổi đám mây",
            }

            def plan_side_effect(path: Path) -> train_knowledge_base.FilePlan:
                return plans[path]

            def upload_side_effect(base_url: str, plan: train_knowledge_base.FilePlan) -> str:
                if plan.path == first_path:
                    raise train_knowledge_base.ApiError("simulated upload failure")
                return "job-2"

            with (
                patch.object(train_knowledge_base, "_fetch_protected_terms", return_value=set()),
                patch.object(train_knowledge_base, "_plan_file", side_effect=plan_side_effect),
                patch.object(train_knowledge_base, "_upload_job", side_effect=upload_side_effect),
                patch.object(train_knowledge_base, "_start_job"),
                patch.object(train_knowledge_base, "_wait_for_review", return_value={"status": "review"}),
                patch.object(train_knowledge_base, "_fetch_segments", return_value=[segment_payload]),
                patch.object(
                    train_knowledge_base,
                    "_review_translation",
                    return_value=("Chuyển đổi đám mây", []),
                ),
                patch.object(train_knowledge_base, "_update_segment"),
                patch.object(train_knowledge_base, "_save_memory_entry") as save_memory_entry_mock,
                patch.object(
                    train_knowledge_base,
                    "_prepare_download",
                    side_effect=train_knowledge_base.ApiError("download is optional during training"),
                ),
                patch.object(train_knowledge_base, "_download_output"),
            ):
                exit_code = train_knowledge_base.run(
                    [
                        "--api-base",
                        "http://example.test",
                        "--input-dir",
                        str(input_dir),
                        "--run-dir",
                        str(run_dir),
                    ]
                )

            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", manifest["files"]["first.pptx"]["status"])
        self.assertEqual("completed", manifest["files"]["second.pptx"]["status"])
        save_memory_entry_mock.assert_called_once_with(
            base_url="http://example.test",
            source_language="ja",
            target_language="vi",
            source_text="クラウド移行",
            translated_text="Chuyển đổi đám mây",
        )
