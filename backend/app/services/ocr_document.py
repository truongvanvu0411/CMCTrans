from __future__ import annotations

import json
from dataclasses import dataclass
from numbers import Integral
from pathlib import Path
from typing import Protocol

OCR_LANGUAGE_MAP = {
    "ja": "japan",
    "en": "en",
    "vi": "vi",
}


class DocumentOcrError(Exception):
    """Raised when OCR parsing cannot be completed."""


@dataclass(frozen=True)
class ExtractedOcrSegment:
    page_name: str
    page_index: int
    block_label: str
    original_text: str
    normalized_text: str
    warning_codes: list[str]
    locator: dict[str, str]
    location_type: str = "ocr_text"


@dataclass(frozen=True)
class ParsedOcrDocument:
    segments: list[ExtractedOcrSegment]
    parse_summary: dict[str, object]


@dataclass(frozen=True)
class _Rectangle:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass(frozen=True)
class _OcrRawBlock:
    source_indexes: list[int]
    text: str
    rectangle: _Rectangle
    score: float | None


class SupportsDocumentOcr(Protocol):
    def parse_document(
        self,
        *,
        file_path: Path,
        file_type: str,
        source_language: str,
    ) -> ParsedOcrDocument:
        ...


class PaddleOcrService:
    def __init__(self, *, models_dir: Path) -> None:
        self._models_dir = models_dir
        self._pipelines: dict[str, object] = {}

    def parse_document(
        self,
        *,
        file_path: Path,
        file_type: str,
        source_language: str,
    ) -> ParsedOcrDocument:
        if file_type not in {"pdf", "image"}:
            raise DocumentOcrError(f"Unsupported OCR file type: {file_type}.")
        ocr_language = OCR_LANGUAGE_MAP.get(source_language)
        if ocr_language is None:
            raise DocumentOcrError(
                f"OCR is not configured for source language: {source_language}."
            )
        if not file_path.exists():
            raise DocumentOcrError(f"OCR source file was not found: {file_path}.")

        pipeline = self._get_pipeline(ocr_language)
        prediction_items = pipeline.predict(str(file_path))
        segments: list[ExtractedOcrSegment] = []
        page_count = 0
        warning_pages: list[str] = []
        for default_page_index, prediction_item in enumerate(prediction_items):
            payload = _extract_prediction_payload(prediction_item)
            page_index = _coerce_page_index(
                payload.get("page_index"),
                default_page_index=default_page_index,
            )
            page_count = max(page_count, page_index + 1)
            page_name = (
                f"Page {page_index + 1}" if file_type == "pdf" else "Image 1"
            )
            page_segments = _build_page_segments(
                payload=payload,
                page_name=page_name,
                page_index=page_index,
            )
            if not page_segments:
                warning_pages.append(page_name)
                continue
            segments.extend(page_segments)
        if not segments:
            raise DocumentOcrError("OCR did not extract any translatable text.")
        warnings = [
            f"{page_name}: no OCR text was extracted."
            for page_name in warning_pages
        ]
        return ParsedOcrDocument(
            segments=segments,
            parse_summary={
                "kind": "ocr",
                "ocr_engine": "paddleocr-pp-ocrv5-mobile",
                "ocr_language": ocr_language,
                "page_count": page_count if file_type == "pdf" else 1,
                "total_extracted_segments": len(segments),
                "warnings": warnings,
            },
        )

    def _get_pipeline(self, ocr_language: str) -> object:
        cached_pipeline = self._pipelines.get(ocr_language)
        if cached_pipeline is not None:
            return cached_pipeline
        try:
            from paddleocr import PaddleOCR
        except ModuleNotFoundError as exc:
            raise DocumentOcrError(
                "PaddleOCR dependencies are not installed. Install paddlepaddle and paddleocr first."
            ) from exc
        except Exception as exc:
            raise DocumentOcrError(
                f"Could not import PaddleOCR runtime dependencies: {exc}"
            ) from exc
        try:
            pipeline = PaddleOCR(
                lang=ocr_language,
                text_detection_model_name="PP-OCRv5_mobile_det",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                device="cpu",
            )
        except Exception as exc:
            raise DocumentOcrError(
                f"Could not initialize PaddleOCR: {exc}"
            ) from exc
        self._pipelines[ocr_language] = pipeline
        return pipeline


def _build_page_segments(
    *,
    payload: dict[str, object],
    page_name: str,
    page_index: int,
) -> list[ExtractedOcrSegment]:
    texts = _coerce_string_list(payload.get("rec_texts"), key_name="rec_texts")
    boxes = _coerce_list(payload.get("rec_boxes"))
    scores = _coerce_list(payload.get("rec_scores"))
    page_width, page_height = _extract_page_image_size(payload)
    raw_blocks = _build_raw_blocks(
        texts=texts,
        boxes=boxes,
        scores=scores,
    )
    merged_blocks = _merge_raw_blocks(
        raw_blocks=raw_blocks,
        page_width=page_width,
        page_height=page_height,
    )
    segments: list[ExtractedOcrSegment] = []
    for block_index, block in enumerate(merged_blocks):
        normalized_text = block.text.strip()
        locator = {
            "ocr_engine": "paddleocr",
            "page_index": str(page_index),
            "block_index": str(block_index),
            "page_width": str(page_width),
            "page_height": str(page_height),
            "source_block_indexes": json.dumps(block.source_indexes),
        }
        locator["box"] = json.dumps(
            [
                block.rectangle.left,
                block.rectangle.top,
                block.rectangle.right,
                block.rectangle.bottom,
            ]
        )
        if block.score is not None:
            locator["score"] = str(block.score)
        segments.append(
            ExtractedOcrSegment(
                page_name=page_name,
                page_index=page_index,
                block_label=f"Block {block_index + 1}",
                original_text=block.text,
                normalized_text=normalized_text,
                warning_codes=[],
                locator=locator,
            )
        )
    return segments


def _build_raw_blocks(
    *,
    texts: list[str],
    boxes: list[object],
    scores: list[object],
) -> list[_OcrRawBlock]:
    raw_blocks: list[_OcrRawBlock] = []
    for block_index, text in enumerate(texts):
        normalized_text = text.strip()
        if normalized_text == "":
            continue
        rectangle = _resolve_rectangle(
            boxes[block_index] if block_index < len(boxes) else None,
            block_index=block_index,
        )
        raw_blocks.append(
            _OcrRawBlock(
                source_indexes=[block_index],
                text=normalized_text,
                rectangle=rectangle,
                score=_coerce_score(scores[block_index] if block_index < len(scores) else None),
            )
        )
    raw_blocks.sort(key=lambda block: (block.rectangle.top, block.rectangle.left))
    return raw_blocks


def _merge_raw_blocks(
    *,
    raw_blocks: list[_OcrRawBlock],
    page_width: int,
    page_height: int,
) -> list[_OcrRawBlock]:
    merged_blocks = list(raw_blocks)
    if len(merged_blocks) < 2:
        return merged_blocks
    while True:
        merge_happened = False
        for index, block in enumerate(merged_blocks):
            candidate_index = _find_merge_candidate(
                blocks=merged_blocks,
                current_index=index,
                page_width=page_width,
                page_height=page_height,
            )
            if candidate_index is None:
                continue
            merged_block = _combine_blocks(
                first=block,
                second=merged_blocks[candidate_index],
            )
            merged_blocks[index] = merged_block
            del merged_blocks[candidate_index]
            merge_happened = True
            break
        if not merge_happened:
            return merged_blocks


def _find_merge_candidate(
    *,
    blocks: list[_OcrRawBlock],
    current_index: int,
    page_width: int,
    page_height: int,
) -> int | None:
    current_block = blocks[current_index]
    horizontal_candidate: tuple[int, int] | None = None
    vertical_candidate: tuple[int, int] | None = None
    for candidate_index in range(current_index + 1, len(blocks)):
        candidate_block = blocks[candidate_index]
        horizontal_gap = candidate_block.rectangle.left - current_block.rectangle.right
        if _should_merge_horizontally(
            current_block=current_block,
            candidate_block=candidate_block,
            horizontal_gap=horizontal_gap,
            page_width=page_width,
        ):
            if horizontal_candidate is None or horizontal_gap < horizontal_candidate[1]:
                horizontal_candidate = (candidate_index, horizontal_gap)
        vertical_gap = candidate_block.rectangle.top - current_block.rectangle.bottom
        if _should_merge_vertically(
            current_block=current_block,
            candidate_block=candidate_block,
            vertical_gap=vertical_gap,
            page_height=page_height,
        ):
            if vertical_candidate is None or vertical_gap < vertical_candidate[1]:
                vertical_candidate = (candidate_index, vertical_gap)
    if horizontal_candidate is not None:
        return horizontal_candidate[0]
    if vertical_candidate is not None:
        return vertical_candidate[0]
    return None


def _should_merge_horizontally(
    *,
    current_block: _OcrRawBlock,
    candidate_block: _OcrRawBlock,
    horizontal_gap: int,
    page_width: int,
) -> bool:
    if horizontal_gap < -4:
        return False
    if horizontal_gap > max(24, min(current_block.rectangle.height, candidate_block.rectangle.height) * 2, page_width // 50):
        return False
    if not _vertical_line_overlap(current_block.rectangle, candidate_block.rectangle):
        return False
    if not _height_ratio_is_compatible(current_block.rectangle, candidate_block.rectangle):
        return False
    return _looks_incomplete(current_block.text) or horizontal_gap <= 8


def _should_merge_vertically(
    *,
    current_block: _OcrRawBlock,
    candidate_block: _OcrRawBlock,
    vertical_gap: int,
    page_height: int,
) -> bool:
    if vertical_gap < -4:
        return False
    if vertical_gap > max(18, min(current_block.rectangle.height, candidate_block.rectangle.height) * 2, page_height // 80):
        return False
    if not _horizontal_column_overlap(current_block.rectangle, candidate_block.rectangle):
        return False
    if not _height_ratio_is_compatible(current_block.rectangle, candidate_block.rectangle):
        return False
    if len(current_block.text) < 5:
        return False
    if not _looks_incomplete(current_block.text):
        return False
    return _looks_like_continuation(candidate_block.text)


def _vertical_line_overlap(first: _Rectangle, second: _Rectangle) -> bool:
    overlap = min(first.bottom, second.bottom) - max(first.top, second.top)
    minimum_overlap = min(first.height, second.height) * 0.45
    return overlap >= minimum_overlap


def _horizontal_column_overlap(first: _Rectangle, second: _Rectangle) -> bool:
    overlap = min(first.right, second.right) - max(first.left, second.left)
    minimum_overlap = min(first.width, second.width) * 0.45
    center_distance = abs(first.center_x - second.center_x)
    return overlap >= minimum_overlap or center_distance <= max(first.width, second.width) * 0.35


def _height_ratio_is_compatible(first: _Rectangle, second: _Rectangle) -> bool:
    shorter_height = max(1, min(first.height, second.height))
    taller_height = max(first.height, second.height)
    return taller_height / shorter_height <= 2.5


def _looks_incomplete(text: str) -> bool:
    normalized_text = text.strip()
    if normalized_text == "":
        return False
    if normalized_text.endswith(
        (
            ".",
            ",",
            ":",
            ";",
            "!",
            "?",
            "。",
            "、",
            "：",
            "；",
            "！",
            "？",
            ")",
            "]",
            "}",
            "）",
            "】",
            "』",
            "」",
            "》",
        )
    ):
        return False
    return True


def _looks_like_continuation(text: str) -> bool:
    normalized_text = text.strip()
    if normalized_text == "":
        return False
    if _is_ascii_label(normalized_text):
        return False
    first_character = normalized_text[0]
    if first_character.islower() or first_character.isdigit():
        return True
    if ord(first_character) > 127:
        return True
    return first_character in {")", "]", "}", "）", "】", "」", "》", "-", "–", "—"}


def _is_ascii_label(text: str) -> bool:
    if any(ord(character) > 127 for character in text):
        return False
    compact_text = text.replace(" ", "")
    return compact_text.isupper() and 1 <= len(compact_text) <= 32


def _combine_blocks(first: _OcrRawBlock, second: _OcrRawBlock) -> _OcrRawBlock:
    separator = _merge_separator(first.text, second.text)
    merged_score_values = [score for score in (first.score, second.score) if score is not None]
    merged_score = (
        sum(merged_score_values) / len(merged_score_values)
        if merged_score_values
        else None
    )
    return _OcrRawBlock(
        source_indexes=first.source_indexes + second.source_indexes,
        text=f"{first.text}{separator}{second.text}".strip(),
        rectangle=_Rectangle(
            left=min(first.rectangle.left, second.rectangle.left),
            top=min(first.rectangle.top, second.rectangle.top),
            right=max(first.rectangle.right, second.rectangle.right),
            bottom=max(first.rectangle.bottom, second.rectangle.bottom),
        ),
        score=merged_score,
    )


def _merge_separator(first_text: str, second_text: str) -> str:
    if first_text.endswith((" ", "\n")) or second_text.startswith((" ", "\n")):
        return ""
    if _contains_non_ascii(first_text) or _contains_non_ascii(second_text):
        return ""
    return " "


def _contains_non_ascii(text: str) -> bool:
    return any(ord(character) > 127 for character in text)


def _resolve_rectangle(box_payload: object, *, block_index: int) -> _Rectangle:
    if box_payload is None:
        raise DocumentOcrError(
            f"PaddleOCR prediction is missing rec_boxes[{block_index}]."
        )
    values = _coerce_list(box_payload)
    if len(values) == 4 and all(isinstance(value, (int, float)) for value in values):
        left = int(values[0])
        top = int(values[1])
        right = int(values[2])
        bottom = int(values[3])
        return _Rectangle(left=left, top=top, right=right, bottom=bottom)
    if len(values) == 4 and all(isinstance(value, (list, tuple)) for value in values):
        coordinates: list[tuple[int, int]] = []
        for point in values:
            point_values = _coerce_list(point)
            if len(point_values) != 2:
                raise DocumentOcrError(
                    f"PaddleOCR returned an unsupported point format in rec_boxes[{block_index}]."
                )
            x_value = point_values[0]
            y_value = point_values[1]
            if not isinstance(x_value, (int, float)) or not isinstance(y_value, (int, float)):
                raise DocumentOcrError(
                    f"PaddleOCR returned non-numeric coordinates in rec_boxes[{block_index}]."
                )
            coordinates.append((int(x_value), int(y_value)))
        return _Rectangle(
            left=min(point[0] for point in coordinates),
            top=min(point[1] for point in coordinates),
            right=max(point[0] for point in coordinates),
            bottom=max(point[1] for point in coordinates),
        )
    raise DocumentOcrError(
        f"PaddleOCR returned an unsupported rec_boxes[{block_index}] format."
    )


def _coerce_score(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _extract_page_image_size(payload: dict[str, object]) -> tuple[int, int]:
    doc_preprocessor = _as_mapping(payload.get("doc_preprocessor_res"))
    if doc_preprocessor is None:
        raise DocumentOcrError(
            "PaddleOCR prediction is missing doc_preprocessor_res."
        )
    output_image = doc_preprocessor.get("output_img")
    shape = getattr(output_image, "shape", None)
    if not isinstance(shape, tuple) or len(shape) < 2:
        raise DocumentOcrError(
            "PaddleOCR prediction is missing output image dimensions."
        )
    page_height = shape[0]
    page_width = shape[1]
    if not isinstance(page_height, Integral) or not isinstance(page_width, Integral):
        raise DocumentOcrError(
            "PaddleOCR prediction returned non-integer page dimensions."
        )
    return int(page_width), int(page_height)


def _extract_prediction_payload(prediction_item: object) -> dict[str, object]:
    direct_mapping = _as_mapping(prediction_item)
    if direct_mapping is not None:
        nested_mapping = _mapping_value(direct_mapping, "res")
        if nested_mapping is not None:
            return nested_mapping
        return direct_mapping
    for attribute_name in ("res", "prunedResult"):
        attribute_value = getattr(prediction_item, attribute_name, None)
        nested_mapping = _as_mapping(attribute_value)
        if nested_mapping is not None:
            return nested_mapping
    for key_name in ("res", "prunedResult"):
        try:
            nested_value = prediction_item[key_name]
        except (KeyError, IndexError, TypeError):
            continue
        nested_mapping = _as_mapping(nested_value)
        if nested_mapping is not None:
            return nested_mapping
    raise DocumentOcrError(
        "PaddleOCR returned an unsupported prediction structure."
    )


def _as_mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    normalized_mapping: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        normalized_mapping[key] = item
    return normalized_mapping


def _mapping_value(mapping: dict[str, object], key_name: str) -> dict[str, object] | None:
    value = mapping.get(key_name)
    return _as_mapping(value)


def _coerce_page_index(value: object, *, default_page_index: int) -> int:
    if value is None:
        return default_page_index
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return default_page_index


def _coerce_string_list(value: object, *, key_name: str) -> list[str]:
    raw_list = _coerce_list(value)
    if not raw_list:
        raise DocumentOcrError(f"PaddleOCR prediction is missing {key_name}.")
    texts: list[str] = []
    for item in raw_list:
        if not isinstance(item, str):
            raise DocumentOcrError(
                f"PaddleOCR returned a non-string value inside {key_name}."
            )
        texts.append(item)
    return texts


def _coerce_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    to_list = getattr(value, "tolist", None)
    if callable(to_list):
        converted = to_list()
        if isinstance(converted, list):
            return converted
        if isinstance(converted, tuple):
            return list(converted)
    return []
