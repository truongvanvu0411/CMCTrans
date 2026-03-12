from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import ctranslate2
import sentencepiece as spm

from ..domain import TranslateResult


SPECIAL_TOKENS = {"<s>", "</s>"}
LANGUAGE_LABELS = {
    "ja": "Japanese",
    "en": "English",
    "vi": "Vietnamese",
}


class TranslationError(Exception):
    """Raised when a translation request cannot be fulfilled."""


class SupportsTranslation(Protocol):
    def available_pairs(self) -> list[dict[str, object]]:
        ...

    def translate(self, text: str, source_language: str, target_language: str) -> TranslateResult:
        ...

    def translate_many(
        self, texts: list[str], source_language: str, target_language: str
    ) -> list[TranslateResult]:
        ...


@dataclass
class ModelBundle:
    name: str
    source_language: str
    target_language: str
    model_dir: Path
    translator: ctranslate2.Translator
    source_tokenizer: spm.SentencePieceProcessor
    target_tokenizer: spm.SentencePieceProcessor
    beam_size: int

    def translate_batch(self, texts: list[str]) -> list[str]:
        tokenized_inputs = [
            self.source_tokenizer.encode(text.strip(), out_type=str) for text in texts
        ]
        results = self.translator.translate_batch(tokenized_inputs, beam_size=self.beam_size)
        translations: list[str] = []
        for result in results:
            target_tokens = [
                token for token in result.hypotheses[0] if token not in SPECIAL_TOKENS
            ]
            translations.append(self.target_tokenizer.decode(target_tokens))
        return translations


class TranslationService:
    def __init__(self, models_dir: Path) -> None:
        workers = max(1, (os.cpu_count() or 4) // 2)
        self._ja_en = self._load_bundle(
            models_dir=models_dir,
            name="quickmt-ja-en",
            source_language="ja",
            target_language="en",
            beam_size=3,
            inter_threads=workers,
        )
        self._en_vi = self._load_bundle(
            models_dir=models_dir,
            name="quickmt-en-vi",
            source_language="en",
            target_language="vi",
            beam_size=4,
            inter_threads=workers,
        )
        self._vi_en = self._load_bundle(
            models_dir=models_dir,
            name="quickmt-vi-en",
            source_language="vi",
            target_language="en",
            beam_size=4,
            inter_threads=workers,
        )
        self._en_ja = self._load_bundle(
            models_dir=models_dir,
            name="quickmt-en-ja",
            source_language="en",
            target_language="ja",
            beam_size=3,
            inter_threads=workers,
        )
        self._pairs = {
            ("ja", "en"): [self._ja_en],
            ("ja", "vi"): [self._ja_en, self._en_vi],
            ("en", "vi"): [self._en_vi],
            ("vi", "en"): [self._vi_en],
            ("en", "ja"): [self._en_ja],
            ("vi", "ja"): [self._vi_en, self._en_ja],
        }

    def available_pairs(self) -> list[dict[str, object]]:
        routes = self._available_routes()
        return [
            {
                "source": {
                    "code": source_code,
                    "label": LANGUAGE_LABELS[source_code],
                },
                "targets": [
                    {
                        "code": target_code,
                        "label": LANGUAGE_LABELS[target_code],
                    }
                    for target_code in target_codes
                ],
            }
            for source_code, target_codes in routes.items()
        ]

    def _available_routes(self) -> dict[str, list[str]]:
        routes: dict[str, list[str]] = {}
        for source_code, target_code in self._pairs:
            targets = routes.setdefault(source_code, [])
            targets.append(target_code)
        return {
            source_code: sorted(target_codes)
            for source_code, target_codes in sorted(routes.items())
        }

    def translate(self, text: str, source_language: str, target_language: str) -> TranslateResult:
        return self.translate_many([text], source_language, target_language)[0]

    def translate_many(
        self, texts: list[str], source_language: str, target_language: str
    ) -> list[TranslateResult]:
        if not texts:
            raise TranslationError("Text batch must not be empty.")
        route = self._pairs.get((source_language, target_language))
        if route is None:
            raise TranslationError(
                f"Unsupported language pair: {source_language} -> {target_language}."
            )
        stripped_texts = [text.strip() for text in texts]
        if any(not text for text in stripped_texts):
            raise TranslationError("Text entries must not be empty.")

        current_texts = stripped_texts
        steps: list[str] = []
        intermediate_texts: list[str | None] = [None for _ in stripped_texts]

        for index, bundle in enumerate(route):
            current_texts = bundle.translate_batch(current_texts)
            steps.append(f"{bundle.source_language}->{bundle.target_language}")
            if index == 0 and len(route) > 1:
                intermediate_texts = list(current_texts)

        return [
            TranslateResult(
                translation=translation,
                intermediate_translation=intermediate_texts[item_index],
                model_chain=list(steps),
            )
            for item_index, translation in enumerate(current_texts)
        ]

    def _load_bundle(
        self,
        *,
        models_dir: Path,
        name: str,
        source_language: str,
        target_language: str,
        beam_size: int,
        inter_threads: int,
    ) -> ModelBundle:
        model_dir = models_dir / name
        if not model_dir.exists():
            raise TranslationError(f"Missing model directory: {model_dir}")
        return ModelBundle(
            name=name,
            source_language=source_language,
            target_language=target_language,
            model_dir=model_dir,
            translator=ctranslate2.Translator(
                str(model_dir),
                device="cpu",
                compute_type="int8",
                inter_threads=inter_threads,
                intra_threads=1,
            ),
            source_tokenizer=spm.SentencePieceProcessor(
                model_file=str(model_dir / "src.spm.model")
            ),
            target_tokenizer=spm.SentencePieceProcessor(
                model_file=str(model_dir / "tgt.spm.model")
            ),
            beam_size=beam_size,
        )
