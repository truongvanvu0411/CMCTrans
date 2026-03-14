from __future__ import annotations

import tempfile
import unittest
import uuid
from datetime import datetime
from pathlib import Path

from backend.app.database import connect_database, initialize_database
from backend.app.domain import TranslateResult
from backend.app.memory_repository import TranslationMemoryRepository
from backend.app.services.glossary import GlossaryService
from backend.app.services.knowledge_translation import KnowledgeAwareTranslationService
from backend.app.services.text_quality import build_clean_correction


class StubTranslationService:
    def __init__(self, responses: dict[tuple[str, str, str], TranslateResult]) -> None:
        self._responses = responses
        self.calls: list[tuple[list[str], str, str]] = []

    def available_pairs(self) -> list[dict[str, object]]:
        return [
            {
                "source": {"code": "ja", "label": "Japanese"},
                "targets": [
                    {"code": "en", "label": "English"},
                    {"code": "vi", "label": "Vietnamese"},
                ],
            },
            {
                "source": {"code": "en", "label": "English"},
                "targets": [
                    {"code": "ja", "label": "Japanese"},
                    {"code": "vi", "label": "Vietnamese"},
                ],
            },
            {
                "source": {"code": "vi", "label": "Vietnamese"},
                "targets": [
                    {"code": "en", "label": "English"},
                    {"code": "ja", "label": "Japanese"},
                ],
            },
        ]

    def translate(self, text: str, source_language: str, target_language: str) -> TranslateResult:
        return self.translate_many([text], source_language, target_language)[0]

    def translate_many(
        self,
        texts: list[str],
        source_language: str,
        target_language: str,
    ) -> list[TranslateResult]:
        self.calls.append((list(texts), source_language, target_language))
        results: list[TranslateResult] = []
        for text in texts:
            key = (source_language, target_language, text)
            response = self._responses.get(key)
            if response is None:
                raise AssertionError(f"Unexpected delegate translation request for {key}.")
            results.append(response)
        return results


class TranslationQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._root_dir = Path(self._temp_dir.name)
        self._connection = connect_database(self._root_dir / "workspace" / "quality.db")
        initialize_database(self._connection)
        self._memory_repository = TranslationMemoryRepository(self._connection)
        glossary_path = (
            Path(__file__).resolve().parents[1] / "app" / "data" / "it_glossary.json"
        )
        self._glossary = GlossaryService(glossary_path)

    def tearDown(self) -> None:
        self._connection.close()
        self._temp_dir.cleanup()

    def test_translate_many_uses_glossary_for_known_it_terms_before_delegate(self) -> None:
        service = KnowledgeAwareTranslationService(
            delegate=StubTranslationService({}),
            memory_repository=self._memory_repository,
            glossary=self._glossary,
        )

        result = service.translate("監査ログビュー", "ja", "vi")

        self.assertEqual(result.translation, "Audit Log View")
        self.assertEqual(result.model_chain, ["glossary:ja->vi"])

    def test_translate_many_applies_short_text_and_protected_rules_without_delegate(self) -> None:
        delegate = StubTranslationService({})
        service = KnowledgeAwareTranslationService(
            delegate=delegate,
            memory_repository=self._memory_repository,
            glossary=self._glossary,
        )

        results = service.translate_many(["O", "No", "API"], "ja", "vi")

        self.assertEqual(results[0].translation, "O")
        self.assertEqual(results[0].model_chain, ["rule:ja->vi"])
        self.assertEqual(results[1].translation, "Không")
        self.assertEqual(results[1].model_chain, ["rule:ja->vi"])
        self.assertEqual(results[2].translation, "API")
        self.assertEqual(results[2].model_chain, ["passthrough:ja->vi"])
        self.assertEqual(delegate.calls, [])

    def test_translate_many_uses_fuzzy_translation_memory_for_close_label_match(self) -> None:
        now = datetime.utcnow()
        self._memory_repository.upsert(
            entry_id=str(uuid.uuid4()),
            source_language="en",
            target_language="vi",
            source_text="Audit Log View",
            translated_text="Audit Log View",
            created_at=now,
            updated_at=now,
        )
        delegate = StubTranslationService({})
        service = KnowledgeAwareTranslationService(
            delegate=delegate,
            memory_repository=self._memory_repository,
            glossary=self._glossary,
        )

        result = service.translate("Audit Log Views", "en", "vi")

        self.assertEqual(result.translation, "Audit Log View")
        self.assertEqual(result.model_chain, ["memory-fuzzy:en->vi"])
        self.assertEqual(delegate.calls, [])

    def test_translate_many_postprocesses_duplicates_and_protected_tokens(self) -> None:
        delegate = StubTranslationService(
            {
                ("en", "vi", "Approval"): TranslateResult(
                    translation="Không, không.",
                    intermediate_translation=None,
                    model_chain=["stub"],
                ),
                ("en", "vi", "API documentation"): TranslateResult(
                    translation="Tài liệu",
                    intermediate_translation=None,
                    model_chain=["stub"],
                ),
            }
        )
        service = KnowledgeAwareTranslationService(
            delegate=delegate,
            memory_repository=self._memory_repository,
            glossary=self._glossary,
        )

        results = service.translate_many(["Approval", "API documentation"], "en", "vi")

        self.assertEqual(results[0].translation, "Không")
        self.assertEqual(results[0].model_chain, ["stub", "postprocess"])
        self.assertEqual(results[1].translation, "Tài liệu API")
        self.assertEqual(results[1].model_chain, ["stub", "postprocess"])

    def test_translate_many_auto_detects_mixed_language_segments_per_text(self) -> None:
        delegate = StubTranslationService(
            {
                ("en", "ja", "OCR-AI SOLUTIONS"): TranslateResult(
                    translation="JA::OCR-AI SOLUTIONS",
                    intermediate_translation=None,
                    model_chain=["en->ja"],
                ),
                ("vi", "ja", "Giải pháp OCR-AI"): TranslateResult(
                    translation="JA::Giải pháp OCR-AI",
                    intermediate_translation="EN::Giải pháp OCR-AI",
                    model_chain=["vi->en", "en->ja"],
                ),
            }
        )
        service = KnowledgeAwareTranslationService(
            delegate=delegate,
            memory_repository=self._memory_repository,
            glossary=self._glossary,
        )

        results = service.translate_many(
            ["OCR-AI SOLUTIONS", "自然言語処理", "Giải pháp OCR-AI"],
            "vi",
            "ja",
        )

        self.assertEqual(results[0].translation, "JA::OCR-AI SOLUTIONS")
        self.assertEqual(results[0].model_chain, ["en->ja", "postprocess"])
        self.assertEqual(results[1].translation, "自然言語処理")
        self.assertEqual(results[1].model_chain, ["passthrough:ja->ja"])
        self.assertEqual(results[2].translation, "JA::Giải pháp OCR-AI")
        self.assertEqual(results[2].model_chain, ["vi->en", "en->ja", "postprocess"])
        self.assertEqual(
            delegate.calls,
            [
                (["OCR-AI SOLUTIONS"], "en", "ja"),
                (["Giải pháp OCR-AI"], "vi", "ja"),
            ],
        )

    def test_build_clean_correction_rejects_symbol_and_noop_edits(self) -> None:
        rejected_symbol = build_clean_correction(
            source_text="O",
            machine_translation="O",
            corrected_translation="O O O",
            glossary=self._glossary,
        )
        rejected_noop = build_clean_correction(
            source_text="購買依頼管理",
            machine_translation="Quản lý yêu cầu mua hàng",
            corrected_translation=" Quản lý yêu cầu mua hàng ",
            glossary=self._glossary,
        )
        accepted = build_clean_correction(
            source_text="購買依頼管理",
            machine_translation="Quản lý đơn hàng",
            corrected_translation="Quản lý yêu cầu mua hàng",
            glossary=self._glossary,
        )

        self.assertIsNone(rejected_symbol)
        self.assertIsNone(rejected_noop)
        self.assertIsNotNone(accepted)
        if accepted is None:
            raise AssertionError("Expected a clean correction candidate.")
        self.assertEqual(accepted.source_text, "購買依頼管理")
        self.assertEqual(accepted.machine_translation, "Quản lý đơn hàng")
        self.assertEqual(accepted.corrected_translation, "Quản lý yêu cầu mua hàng")


if __name__ == "__main__":
    unittest.main()
