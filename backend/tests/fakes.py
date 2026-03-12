from __future__ import annotations

from backend.app.domain import TranslateResult


class FakeTranslationService:
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
        self, texts: list[str], source_language: str, target_language: str
    ) -> list[TranslateResult]:
        results: list[TranslateResult] = []
        for text in texts:
            if source_language == "ja" and target_language == "en":
                results.append(
                    TranslateResult(
                        translation=f"EN::{text}",
                        intermediate_translation=None,
                        model_chain=["ja->en"],
                    )
                )
            elif source_language == "ja" and target_language == "vi":
                results.append(
                    TranslateResult(
                        translation=f"VI::{text}",
                        intermediate_translation=f"EN::{text}",
                        model_chain=["ja->en", "en->vi"],
                    )
                )
            elif source_language == "vi" and target_language == "en":
                results.append(
                    TranslateResult(
                        translation=f"EN::{text}",
                        intermediate_translation=None,
                        model_chain=["vi->en"],
                    )
                )
            elif source_language == "en" and target_language == "ja":
                results.append(
                    TranslateResult(
                        translation=f"JA::{text}",
                        intermediate_translation=None,
                        model_chain=["en->ja"],
                    )
                )
            elif source_language == "vi" and target_language == "ja":
                results.append(
                    TranslateResult(
                        translation=f"JA::{text}",
                        intermediate_translation=f"EN::{text}",
                        model_chain=["vi->en", "en->ja"],
                    )
                )
            elif source_language == "en" and target_language == "vi":
                results.append(
                    TranslateResult(
                        translation=f"VI::{text}",
                        intermediate_translation=None,
                        model_chain=["en->vi"],
                    )
                )
            else:
                raise RuntimeError("Unsupported fake translation route.")
        return results
