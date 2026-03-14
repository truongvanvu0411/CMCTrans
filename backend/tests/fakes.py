from __future__ import annotations

from pathlib import Path

from backend.app.domain import TranslateResult
from backend.app.services.ocr_document import (
    ExtractedOcrSegment,
    ParsedOcrDocument,
)
from backend.app.services.ocr_layout import DocumentLayoutError, RenderedOcrDocument


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


class FakeDocumentOcrService:
    def parse_document(
        self,
        *,
        file_path: Path,
        file_type: str,
        source_language: str,
    ) -> ParsedOcrDocument:
        if file_type == "pdf":
            return ParsedOcrDocument(
                segments=[
                    ExtractedOcrSegment(
                        page_name="Page 1",
                        page_index=0,
                        block_label="Block 1",
                        original_text="OCR PDF heading",
                        normalized_text="OCR PDF heading",
                        warning_codes=[],
                        locator={
                            "ocr_engine": "fake",
                            "page_index": "0",
                            "block_index": "0",
                            "page_width": "400",
                            "page_height": "200",
                            "box": "[40, 40, 180, 90]",
                        },
                    ),
                    ExtractedOcrSegment(
                        page_name="Page 2",
                        page_index=1,
                        block_label="Block 1",
                        original_text="OCR PDF body",
                        normalized_text="OCR PDF body",
                        warning_codes=[],
                        locator={
                            "ocr_engine": "fake",
                            "page_index": "1",
                            "block_index": "0",
                            "page_width": "400",
                            "page_height": "200",
                            "box": "[40, 40, 220, 90]",
                        },
                    ),
                ],
                parse_summary={
                    "kind": "ocr",
                    "ocr_engine": "fake",
                    "ocr_language": source_language,
                    "page_count": 2,
                    "total_extracted_segments": 2,
                    "warnings": [],
                },
            )
        if file_type == "image":
            return ParsedOcrDocument(
                segments=[
                    ExtractedOcrSegment(
                        page_name="Image 1",
                        page_index=0,
                        block_label="Block 1",
                        original_text="OCR image text",
                        normalized_text="OCR image text",
                        warning_codes=[],
                        locator={
                            "ocr_engine": "fake",
                            "page_index": "0",
                            "block_index": "0",
                            "page_width": "400",
                            "page_height": "200",
                            "box": "[40, 40, 220, 90]",
                        },
                    )
                ],
                parse_summary={
                    "kind": "ocr",
                    "ocr_engine": "fake",
                    "ocr_language": source_language,
                    "page_count": 1,
                    "total_extracted_segments": 1,
                    "warnings": [],
                },
            )
        raise RuntimeError(f"Unsupported fake OCR file type: {file_type}.")


class FlakyOcrLayoutRenderer:
    def __init__(self) -> None:
        self._call_count = 0

    def render_document(
        self,
        *,
        file_path: Path,
        file_type: str,
        translated_segments: list[object],
    ) -> RenderedOcrDocument:
        self._call_count += 1
        if self._call_count == 1:
            raise DocumentLayoutError(
                "Image 1 Block 1 translated text does not fit inside its detected layout box. "
                "Shorten the translation and try again."
            )
        return RenderedOcrDocument(
            file_bytes=(
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR"
                b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
                b"\x90wS\xde"
                b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA"
                b"\x89\x1f\xb5"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            ),
            output_suffix=".png",
            media_type="image/png",
        )
