from __future__ import annotations

import re

from ..domain import TranslateResult
from ..memory_repository import TranslationMemoryRecord, TranslationMemoryRepository
from .glossary import GlossaryService
from .text_quality import (
    TextClassification,
    classify_text,
    fuzzy_similarity,
    normalize_text_for_lookup,
    postprocess_translation,
    try_rule_based_translation,
)
from .translation import SupportsTranslation, TranslationError


JAPANESE_CHAR_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
VIETNAMESE_CHAR_RE = re.compile(
    r"[ăâđêôơưĂÂĐÊÔƠƯáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệ"
    r"óòỏõọốồổỗộớờởỡợúùủũụứừửữựíìỉĩịýỳỷỹỵ]"
)
LATIN_CHAR_RE = re.compile(r"[A-Za-z]")


class KnowledgeAwareTranslationService:
    def __init__(
        self,
        *,
        delegate: SupportsTranslation,
        memory_repository: TranslationMemoryRepository,
        glossary: GlossaryService,
    ) -> None:
        self._delegate = delegate
        self._memory_repository = memory_repository
        self._glossary = glossary
        self._supported_pairs = {
            (pair["source"]["code"], target["code"])
            for pair in self._delegate.available_pairs()
            for target in pair["targets"]
        }

    def available_pairs(self) -> list[dict[str, object]]:
        return self._delegate.available_pairs()

    def translate(self, text: str, source_language: str, target_language: str) -> TranslateResult:
        return self.translate_many([text], source_language, target_language)[0]

    def translate_many(
        self,
        texts: list[str],
        source_language: str,
        target_language: str,
    ) -> list[TranslateResult]:
        if not texts:
            raise TranslationError("Text batch must not be empty.")
        if (source_language, target_language) not in self._supported_pairs:
            raise TranslationError(
                f"Unsupported language pair: {source_language} -> {target_language}."
            )

        normalized_texts = [normalize_text_for_lookup(text) for text in texts]
        if any(not text for text in normalized_texts):
            raise TranslationError("Text entries must not be empty.")

        classifications = [
            classify_text(text, self._glossary) for text in normalized_texts
        ]
        resolved_source_languages = [
            self._resolve_source_language(
                text=text,
                classification=classifications[index],
                requested_source_language=source_language,
                target_language=target_language,
            )
            for index, text in enumerate(normalized_texts)
        ]
        results: list[TranslateResult | None] = [None for _ in normalized_texts]
        delegate_batches: dict[tuple[str, str], list[tuple[int, str]]] = {}

        for index, text in enumerate(normalized_texts):
            classification = classifications[index]
            resolved_source_language = resolved_source_languages[index]

            if resolved_source_language == target_language:
                results[index] = TranslateResult(
                    translation=text,
                    intermediate_translation=None,
                    model_chain=[f"passthrough:{resolved_source_language}->{target_language}"],
                )
                continue

            routed = try_rule_based_translation(
                text=text,
                source_language=resolved_source_language,
                target_language=target_language,
                classification=classification,
                glossary=self._glossary,
            )
            if routed is not None:
                results[index] = routed
                continue

            exact_memory = self._memory_repository.find_exact(
                source_language=resolved_source_language,
                target_language=target_language,
                source_text=text,
            )
            if exact_memory is not None:
                results[index] = TranslateResult(
                    translation=exact_memory.translated_text,
                    intermediate_translation=None,
                    model_chain=[f"memory-exact:{resolved_source_language}->{target_language}"],
                )
                continue

            fuzzy_memory = self._find_fuzzy_memory(
                source_language=resolved_source_language,
                target_language=target_language,
                text=text,
                classification=classification,
            )
            if fuzzy_memory is not None:
                results[index] = TranslateResult(
                    translation=fuzzy_memory.translated_text,
                    intermediate_translation=None,
                    model_chain=[f"memory-fuzzy:{resolved_source_language}->{target_language}"],
                )
                continue

            delegate_batches.setdefault((resolved_source_language, target_language), []).append(
                (index, text)
            )

        for (batch_source_language, batch_target_language), batch_items in delegate_batches.items():
            delegate_results = self._delegate.translate_many(
                [text for _, text in batch_items],
                batch_source_language,
                batch_target_language,
            )
            for (delegate_index, _), delegate_result in zip(batch_items, delegate_results, strict=True):
                results[delegate_index] = self._postprocess_result(
                    source_text=normalized_texts[delegate_index],
                    result=delegate_result,
                )

        finalized_results = [result for result in results if result is not None]
        if len(finalized_results) != len(normalized_texts):
            raise TranslationError("Translation results could not be aligned with the request.")
        return finalized_results

    def _find_fuzzy_memory(
        self,
        *,
        source_language: str,
        target_language: str,
        text: str,
        classification: TextClassification,
    ) -> TranslationMemoryRecord | None:
        if classification.category not in {"short_text", "label", "mixed_technical"}:
            return None
        threshold = 0.96 if len(text) <= 16 else 0.985
        candidates = self._memory_repository.list_candidates(
            source_language=source_language,
            target_language=target_language,
            source_text=text,
        )
        best_candidate: TranslationMemoryRecord | None = None
        best_score = 0.0
        for candidate in candidates:
            score = fuzzy_similarity(text, candidate.source_text)
            if score > best_score:
                best_candidate = candidate
                best_score = score
        if best_candidate is None or best_score < threshold:
            return None
        return best_candidate

    def _resolve_source_language(
        self,
        *,
        text: str,
        classification: TextClassification,
        requested_source_language: str,
        target_language: str,
    ) -> str:
        if classification.category in {"protected", "symbol"}:
            return requested_source_language
        if classification.category == "short_text" and len(text) <= 4:
            return requested_source_language
        detected_language = self._detect_text_language(text)
        if detected_language == target_language:
            return detected_language
        if (detected_language, target_language) in self._supported_pairs:
            return detected_language
        return requested_source_language

    def _detect_text_language(self, text: str) -> str:
        japanese_count = len(JAPANESE_CHAR_RE.findall(text))
        vietnamese_count = len(VIETNAMESE_CHAR_RE.findall(text))
        latin_count = len(LATIN_CHAR_RE.findall(text))

        if japanese_count > 0 and japanese_count >= max(vietnamese_count, latin_count):
            return "ja"
        if vietnamese_count > 0:
            return "vi"
        if latin_count > 0:
            return "en"
        return "ja"

    def _postprocess_result(
        self,
        *,
        source_text: str,
        result: TranslateResult,
    ) -> TranslateResult:
        cleaned_translation = postprocess_translation(
            source_text=source_text,
            translated_text=result.translation,
            glossary=self._glossary,
        )
        cleaned_intermediate = (
            postprocess_translation(
                source_text=source_text,
                translated_text=result.intermediate_translation,
                glossary=self._glossary,
            )
            if result.intermediate_translation is not None
            else None
        )
        return TranslateResult(
            translation=cleaned_translation,
            intermediate_translation=cleaned_intermediate,
            model_chain=list(result.model_chain) + ["postprocess"],
        )
