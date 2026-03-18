from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..domain import TranslateResult
from .ocr_document import DocumentOcrError, ParsedOcrDocument, SupportsDocumentOcr
from .translation import SupportsTranslation

LANGUAGE_PAIRS: list[dict[str, object]] = [
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


class LazyTranslationService:
    def __init__(self, *, factory: Callable[[], SupportsTranslation]) -> None:
        self._factory = factory
        self._delegate: SupportsTranslation | None = None

    def available_pairs(self) -> list[dict[str, object]]:
        return LANGUAGE_PAIRS

    def translate(self, text: str, source_language: str, target_language: str) -> TranslateResult:
        return self._get_delegate().translate(text, source_language, target_language)

    def translate_many(
        self, texts: list[str], source_language: str, target_language: str
    ) -> list[TranslateResult]:
        return self._get_delegate().translate_many(texts, source_language, target_language)

    def _get_delegate(self) -> SupportsTranslation:
        if self._delegate is None:
            self._delegate = self._factory()
        return self._delegate


class LazyDocumentOcrService:
    def __init__(self, *, factory: Callable[[], SupportsDocumentOcr]) -> None:
        self._factory = factory
        self._delegate: SupportsDocumentOcr | None = None

    def parse_document(
        self,
        *,
        file_path: Path,
        file_type: str,
        source_language: str,
    ) -> ParsedOcrDocument:
        return self._get_delegate().parse_document(
            file_path=file_path,
            file_type=file_type,
            source_language=source_language,
        )

    def _get_delegate(self) -> SupportsDocumentOcr:
        if self._delegate is None:
            self._delegate = self._factory()
        return self._delegate
