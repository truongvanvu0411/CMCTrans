from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw, ImageFont, ImageStat


class DocumentLayoutError(Exception):
    """Raised when OCR layout rendering cannot be completed."""


@dataclass(frozen=True)
class RenderableOcrSegment:
    page_name: str
    block_label: str
    locator: dict[str, str]
    final_text: str


@dataclass(frozen=True)
class RenderedOcrDocument:
    file_bytes: bytes
    output_suffix: str
    media_type: str


class SupportsOcrLayoutRenderer(Protocol):
    def render_document(
        self,
        *,
        file_path: Path,
        file_type: str,
        translated_segments: list[RenderableOcrSegment],
    ) -> RenderedOcrDocument:
        ...


@dataclass(frozen=True)
class _PageSize:
    width: int
    height: int


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


class PillowOcrLayoutRenderer:
    def __init__(self, *, font_path: Path | None = None) -> None:
        self._font_path = font_path

    def render_document(
        self,
        *,
        file_path: Path,
        file_type: str,
        translated_segments: list[RenderableOcrSegment],
    ) -> RenderedOcrDocument:
        if file_type not in {"pdf", "image"}:
            raise DocumentLayoutError(f"Unsupported OCR layout export type: {file_type}.")
        if not translated_segments:
            raise DocumentLayoutError("No OCR segments were provided for layout export.")
        if not file_path.exists():
            raise DocumentLayoutError(f"Source file was not found: {file_path}.")
        resolved_font_path = self._font_path or _resolve_font_path()

        page_sizes = _collect_page_sizes(translated_segments)
        rendered_pages = _render_source_pages(
            file_path=file_path,
            file_type=file_type,
            page_sizes=page_sizes,
        )
        segments_by_page = _group_segments_by_page(translated_segments)
        for page_index in segments_by_page:
            if page_index >= len(rendered_pages):
                raise DocumentLayoutError(
                    f"OCR references Page {page_index + 1}, but the source document has only {len(rendered_pages)} rendered pages."
                )
        output_pages: list[Image.Image] = []

        for page_index, page_image in enumerate(rendered_pages):
            page_segments = segments_by_page.get(page_index, [])
            output_pages.append(
                _draw_page_translations(
                    page_image=page_image,
                    segments=page_segments,
                    font_path=resolved_font_path,
                )
            )

        if file_type == "pdf":
            return _export_pdf(output_pages)
        return _export_image(output_pages)


def _resolve_font_path() -> Path:
    override = os.getenv("TRANSLATOR_OCR_LAYOUT_FONT_PATH")
    candidate_paths = [Path(override).resolve()] if override else []
    candidate_paths.extend(
        [
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
            Path("C:/Windows/Fonts/arialuni.ttf"),
            Path("C:/Windows/Fonts/msgothic.ttc"),
            Path("C:/Windows/Fonts/arial.ttf"),
        ]
    )
    for candidate_path in candidate_paths:
        if candidate_path.exists():
            return candidate_path
    searched_locations = ", ".join(str(path) for path in candidate_paths)
    raise DocumentLayoutError(
        f"No OCR layout font was found. Checked: {searched_locations}"
    )


def _collect_page_sizes(translated_segments: list[RenderableOcrSegment]) -> dict[int, _PageSize]:
    page_sizes: dict[int, _PageSize] = {}
    for segment in translated_segments:
        locator = segment.locator
        page_index = _locator_int(locator, "page_index", segment=segment)
        page_width = _locator_int(locator, "page_width", segment=segment)
        page_height = _locator_int(locator, "page_height", segment=segment)
        existing_page_size = page_sizes.get(page_index)
        next_page_size = _PageSize(width=page_width, height=page_height)
        if existing_page_size is not None and existing_page_size != next_page_size:
            raise DocumentLayoutError(
                f"{segment.page_name} contains inconsistent OCR page dimensions."
            )
        page_sizes[page_index] = next_page_size
    return page_sizes


def _group_segments_by_page(
    translated_segments: list[RenderableOcrSegment],
) -> dict[int, list[RenderableOcrSegment]]:
    segments_by_page: dict[int, list[RenderableOcrSegment]] = {}
    for segment in translated_segments:
        page_index = _locator_int(segment.locator, "page_index", segment=segment)
        segments_by_page.setdefault(page_index, []).append(segment)
    for page_segments in segments_by_page.values():
        page_segments.sort(
            key=lambda segment: _locator_int(segment.locator, "block_index", segment=segment)
        )
    return segments_by_page


def _render_source_pages(
    *,
    file_path: Path,
    file_type: str,
    page_sizes: dict[int, _PageSize],
) -> list[Image.Image]:
    if file_type == "image":
        image = Image.open(file_path).convert("RGB")
        expected_page_size = page_sizes.get(0)
        if expected_page_size is None:
            raise DocumentLayoutError("Image OCR metadata is missing page dimensions.")
        if image.size != (expected_page_size.width, expected_page_size.height):
            raise DocumentLayoutError(
                "Image dimensions do not match the OCR coordinate space."
            )
        return [image]

    try:
        import pypdfium2 as pdfium
    except ModuleNotFoundError as exc:
        raise DocumentLayoutError(
            "PDF layout export requires pypdfium2 to be installed."
        ) from exc

    pdf_document = pdfium.PdfDocument(str(file_path))
    pages: list[Image.Image] = []
    try:
        page_count = len(pdf_document)
        for page_index in range(page_count):
            expected_page_size = page_sizes.get(page_index)
            if expected_page_size is None:
                raise DocumentLayoutError(
                    f"Missing OCR page dimensions for Page {page_index + 1}."
                )
            page = pdf_document[page_index]
            try:
                page_width = float(page.get_width())
                page_height = float(page.get_height())
                if page_width <= 0 or page_height <= 0:
                    raise DocumentLayoutError(
                        f"Page {page_index + 1} has invalid PDF dimensions."
                    )
                scale_x = expected_page_size.width / page_width
                scale_y = expected_page_size.height / page_height
                if abs(scale_x - scale_y) > 0.05:
                    raise DocumentLayoutError(
                        f"Page {page_index + 1} OCR dimensions do not match the PDF page aspect ratio."
                    )
                bitmap = page.render(scale=scale_x)
                page_image = bitmap.to_pil().convert("RGB")
            finally:
                page.close()
            if page_image.size != (expected_page_size.width, expected_page_size.height):
                raise DocumentLayoutError(
                    f"Page {page_index + 1} rendered size does not match OCR coordinates."
                )
            pages.append(page_image)
    finally:
        pdf_document.close()
    return pages


def _draw_page_translations(
    *,
    page_image: Image.Image,
    segments: list[RenderableOcrSegment],
    font_path: Path,
) -> Image.Image:
    output_image = page_image.copy()
    drawing_context = ImageDraw.Draw(output_image)
    segment_rectangles = [_locator_rectangle(segment) for segment in segments]

    for index, segment in enumerate(segments):
        rectangle = segment_rectangles[index]
        if rectangle.width <= 0 or rectangle.height <= 0:
            raise DocumentLayoutError(
                f"{segment.page_name} {segment.block_label} has an invalid OCR bounding box."
            )
        draw_rectangle, layout = _resolve_text_layout(
            drawing_context=drawing_context,
            font_path=font_path,
            segment=segment,
            rectangle=rectangle,
            other_rectangles=segment_rectangles[:index] + segment_rectangles[index + 1 :],
            page_width=output_image.width,
            page_height=output_image.height,
        )
        fill_color = _sample_background_color(output_image, rectangle)
        drawing_context.rectangle(
            [(draw_rectangle.left, draw_rectangle.top), (draw_rectangle.right, draw_rectangle.bottom)],
            fill=fill_color,
        )
        drawing_context.multiline_text(
            (draw_rectangle.left, draw_rectangle.top),
            layout.text,
            fill=(0, 0, 0),
            font=layout.font,
            spacing=layout.spacing,
            align="left",
        )

    return output_image


@dataclass(frozen=True)
class _TextLayout:
    text: str
    font: ImageFont.FreeTypeFont
    spacing: int


def _resolve_text_layout(
    *,
    drawing_context: ImageDraw.ImageDraw,
    font_path: Path,
    segment: RenderableOcrSegment,
    rectangle: _Rectangle,
    other_rectangles: list[_Rectangle],
    page_width: int,
    page_height: int,
) -> tuple[_Rectangle, _TextLayout]:
    candidate_rectangles = _layout_candidate_rectangles(
        rectangle=rectangle,
        other_rectangles=other_rectangles,
        page_width=page_width,
        page_height=page_height,
    )
    for candidate_rectangle in candidate_rectangles:
        try:
            layout = _fit_text_layout(
                drawing_context=drawing_context,
                font_path=font_path,
                text=segment.final_text,
                rectangle=candidate_rectangle,
                segment_label=f"{segment.page_name} {segment.block_label}",
            )
        except DocumentLayoutError:
            continue
        return candidate_rectangle, layout
    raise DocumentLayoutError(
        f"{segment.page_name} {segment.block_label} translated text does not fit inside its detected layout box. "
        "Shorten the translation and try again."
    )


def _fit_text_layout(
    *,
    drawing_context: ImageDraw.ImageDraw,
    font_path: Path,
    text: str,
    rectangle: _Rectangle,
    segment_label: str,
) -> _TextLayout:
    normalized_text = text.strip()
    if normalized_text == "":
        raise DocumentLayoutError("OCR layout export cannot render empty text.")

    minimum_font_size = max(2, min(8, rectangle.width, rectangle.height))
    maximum_font_size = max(minimum_font_size, min(96, rectangle.height))
    best_layout: _TextLayout | None = None

    low = minimum_font_size
    high = maximum_font_size
    while low <= high:
        font_size = (low + high) // 2
        font = ImageFont.truetype(str(font_path), font_size)
        spacing = max(0, font_size // 6)
        wrapped_text = _wrap_text_to_width(
            drawing_context=drawing_context,
            text=normalized_text,
            font=font,
            max_width=rectangle.width,
        )
        text_width, text_height = _measure_multiline_text(
            drawing_context=drawing_context,
            text=wrapped_text,
            font=font,
            spacing=spacing,
        )
        if text_width <= rectangle.width and text_height <= rectangle.height:
            best_layout = _TextLayout(text=wrapped_text, font=font, spacing=spacing)
            low = font_size + 1
        else:
            high = font_size - 1

    if best_layout is None:
        raise DocumentLayoutError(
            f"{segment_label} translated text does not fit inside its detected layout box. "
            "Shorten the translation and try again."
        )
    return best_layout


def _layout_candidate_rectangles(
    *,
    rectangle: _Rectangle,
    other_rectangles: list[_Rectangle],
    page_width: int,
    page_height: int,
) -> list[_Rectangle]:
    if rectangle.width <= 0 or rectangle.height <= 0:
        return [rectangle]

    expansion_margin = 6
    horizontal_growth = max(160, rectangle.width * 6)
    vertical_growth = max(48, rectangle.height * 6)

    left_bound = max(0, rectangle.left - max(48, rectangle.width * 2))
    right_bound = min(page_width, rectangle.right + horizontal_growth)
    top_bound = max(0, rectangle.top - max(24, rectangle.height * 2))
    bottom_bound = min(page_height, rectangle.bottom + vertical_growth)

    for other_rectangle in other_rectangles:
        if _vertical_overlap(rectangle, other_rectangle):
            if other_rectangle.right <= rectangle.left:
                left_bound = max(left_bound, other_rectangle.right + expansion_margin)
            elif other_rectangle.left >= rectangle.right:
                right_bound = min(right_bound, other_rectangle.left - expansion_margin)
        if _horizontal_overlap(rectangle, other_rectangle):
            if other_rectangle.bottom <= rectangle.top:
                top_bound = max(top_bound, other_rectangle.bottom + expansion_margin)
            elif other_rectangle.top >= rectangle.bottom:
                bottom_bound = min(bottom_bound, other_rectangle.top - expansion_margin)

    candidates = [
        rectangle,
        _Rectangle(left=left_bound, top=rectangle.top, right=right_bound, bottom=rectangle.bottom),
        _Rectangle(left=rectangle.left, top=top_bound, right=rectangle.right, bottom=bottom_bound),
        _Rectangle(left=left_bound, top=top_bound, right=right_bound, bottom=bottom_bound),
    ]
    unique_candidates: list[_Rectangle] = []
    seen_keys: set[tuple[int, int, int, int]] = set()
    for candidate in candidates:
        if candidate.width <= 0 or candidate.height <= 0:
            continue
        candidate_key = (candidate.left, candidate.top, candidate.right, candidate.bottom)
        if candidate_key in seen_keys:
            continue
        seen_keys.add(candidate_key)
        unique_candidates.append(candidate)
    return unique_candidates or [rectangle]


def _wrap_text_to_width(
    *,
    drawing_context: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> str:
    wrapped_lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        paragraph_text = paragraph.strip()
        if paragraph_text == "":
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(
            _wrap_single_paragraph(
                drawing_context=drawing_context,
                text=paragraph_text,
                font=font,
                max_width=max_width,
            )
        )
    return "\n".join(wrapped_lines)


def _wrap_single_paragraph(
    *,
    drawing_context: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    tokens = text.split() if " " in text else list(text)
    lines: list[str] = []
    current_line = ""
    separator = " " if " " in text else ""

    for token in tokens:
        if separator == " " and _text_width(drawing_context, token, font) > max_width:
            oversized_chunks = _break_oversized_token(
                drawing_context=drawing_context,
                token=token,
                font=font,
                max_width=max_width,
            )
            if current_line:
                lines.append(current_line)
                current_line = ""
            lines.extend(oversized_chunks[:-1])
            current_line = oversized_chunks[-1]
            continue
        candidate_line = token if current_line == "" else f"{current_line}{separator}{token}"
        candidate_width = _text_width(drawing_context, candidate_line, font)
        if candidate_width <= max_width or current_line == "":
            current_line = candidate_line
            continue
        lines.append(current_line)
        current_line = token

    if current_line:
        lines.append(current_line)
    return lines


def _break_oversized_token(
    *,
    drawing_context: ImageDraw.ImageDraw,
    token: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    chunks: list[str] = []
    current_chunk = ""
    for character in token:
        candidate_chunk = f"{current_chunk}{character}"
        if current_chunk and _text_width(drawing_context, candidate_chunk, font) > max_width:
            chunks.append(current_chunk)
            current_chunk = character
            continue
        current_chunk = candidate_chunk
    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def _text_width(
    drawing_context: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
) -> int:
    left, _, right, _ = drawing_context.textbbox((0, 0), text, font=font)
    return max(0, right - left)


def _measure_multiline_text(
    *,
    drawing_context: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    spacing: int,
) -> tuple[int, int]:
    left, top, right, bottom = drawing_context.multiline_textbbox(
        (0, 0),
        text,
        font=font,
        spacing=spacing,
    )
    return max(0, right - left), max(0, bottom - top)


def _vertical_overlap(first: _Rectangle, second: _Rectangle) -> bool:
    return min(first.bottom, second.bottom) - max(first.top, second.top) > 2


def _horizontal_overlap(first: _Rectangle, second: _Rectangle) -> bool:
    return min(first.right, second.right) - max(first.left, second.left) > 2


def _sample_background_color(image: Image.Image, rectangle: _Rectangle) -> tuple[int, int, int]:
    sample_margin = max(2, min(rectangle.width, rectangle.height) // 6)
    sample_regions = [
        (rectangle.left, max(0, rectangle.top - sample_margin), rectangle.right, rectangle.top),
        (
            rectangle.left,
            rectangle.bottom,
            rectangle.right,
            min(image.height, rectangle.bottom + sample_margin),
        ),
        (max(0, rectangle.left - sample_margin), rectangle.top, rectangle.left, rectangle.bottom),
        (
            rectangle.right,
            rectangle.top,
            min(image.width, rectangle.right + sample_margin),
            rectangle.bottom,
        ),
    ]
    sample_pixels: list[tuple[int, int, int]] = []
    for region in sample_regions:
        left, top, right, bottom = region
        if right <= left or bottom <= top:
            continue
        region_image = image.crop(region)
        mean_values = ImageStat.Stat(region_image).mean
        sample_pixels.append(
            (
                int(mean_values[0]),
                int(mean_values[1]),
                int(mean_values[2]),
            )
        )

    if not sample_pixels:
        fallback_region = image.crop(
            (
                rectangle.left,
                rectangle.top,
                min(image.width, rectangle.right),
                min(image.height, rectangle.bottom),
            )
        )
        mean_values = ImageStat.Stat(fallback_region).mean
        return int(mean_values[0]), int(mean_values[1]), int(mean_values[2])

    red = sum(pixel[0] for pixel in sample_pixels) // len(sample_pixels)
    green = sum(pixel[1] for pixel in sample_pixels) // len(sample_pixels)
    blue = sum(pixel[2] for pixel in sample_pixels) // len(sample_pixels)
    return red, green, blue


def _locator_rectangle(segment: RenderableOcrSegment) -> _Rectangle:
    box_payload = segment.locator.get("box")
    if box_payload is None:
        raise DocumentLayoutError(
            f"{segment.page_name} {segment.block_label} is missing OCR coordinates."
        )
    try:
        values = json.loads(box_payload)
    except json.JSONDecodeError as exc:
        raise DocumentLayoutError(
            f"{segment.page_name} {segment.block_label} has invalid OCR coordinates."
        ) from exc
    if not isinstance(values, list) or len(values) != 4:
        raise DocumentLayoutError(
            f"{segment.page_name} {segment.block_label} has an unsupported OCR box format."
        )
    left, top, right, bottom = (_coerce_box_value(value, segment=segment) for value in values)
    return _Rectangle(left=left, top=top, right=right, bottom=bottom)


def _coerce_box_value(value: object, *, segment: RenderableOcrSegment) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise DocumentLayoutError(
        f"{segment.page_name} {segment.block_label} has a non-integer OCR box coordinate."
    )


def _locator_int(
    locator: dict[str, str],
    key_name: str,
    *,
    segment: RenderableOcrSegment,
) -> int:
    raw_value = locator.get(key_name)
    if raw_value is None:
        raise DocumentLayoutError(
            f"{segment.page_name} {segment.block_label} is missing {key_name}."
        )
    try:
        return int(raw_value)
    except ValueError as exc:
        raise DocumentLayoutError(
            f"{segment.page_name} {segment.block_label} has invalid {key_name}: {raw_value}."
        ) from exc


def _export_pdf(pages: list[Image.Image]) -> RenderedOcrDocument:
    if not pages:
        raise DocumentLayoutError("No rendered pages are available for PDF export.")
    buffer = io.BytesIO()
    first_page, *remaining_pages = pages
    first_page.save(buffer, format="PDF", save_all=True, append_images=remaining_pages, resolution=144)
    return RenderedOcrDocument(
        file_bytes=buffer.getvalue(),
        output_suffix=".pdf",
        media_type="application/pdf",
    )


def _export_image(pages: list[Image.Image]) -> RenderedOcrDocument:
    if len(pages) != 1:
        raise DocumentLayoutError("Image layout export expects exactly one rendered page.")
    buffer = io.BytesIO()
    pages[0].save(buffer, format="PNG")
    return RenderedOcrDocument(
        file_bytes=buffer.getvalue(),
        output_suffix=".png",
        media_type="image/png",
    )
