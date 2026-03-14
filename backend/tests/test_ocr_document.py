from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from backend.app.services.ocr_layout import (
    PillowOcrLayoutRenderer,
    RenderableOcrSegment,
)
from backend.app.services.ocr_document import _build_page_segments


def build_test_ocr_image() -> bytes:
    image = Image.new("RGB", (400, 200), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def build_test_ocr_pdf() -> bytes:
    first_page = Image.new("RGB", (400, 200), "white")
    second_page = Image.new("RGB", (400, 200), "white")
    buffer = io.BytesIO()
    first_page.save(
        buffer,
        format="PDF",
        save_all=True,
        append_images=[second_page],
        resolution=144,
    )
    return buffer.getvalue()


def _resolve_test_font_path() -> Path:
    candidate_paths = [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arialuni.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate_path in candidate_paths:
        if candidate_path.exists():
            return candidate_path
    raise AssertionError("A test font path is required for OCR layout rendering tests.")


class _ShapeStub:
    def __init__(self, *, height: int, width: int) -> None:
        self.shape = (height, width, 3)


class OcrDocumentTests(unittest.TestCase):
    def test_build_page_segments_merges_sentence_fragments_on_same_column(self) -> None:
        segments = _build_page_segments(
            payload={
                "rec_texts": [
                    "現在会社が持っているデータの",
                    "ままを使い、ChatBot用のデ",
                    "ータ構築は自動",
                ],
                "rec_boxes": [
                    [120, 100, 320, 118],
                    [120, 121, 324, 139],
                    [120, 142, 252, 160],
                ],
                "rec_scores": [0.99, 0.98, 0.97],
                "doc_preprocessor_res": {
                    "output_img": _ShapeStub(height=400, width=600),
                },
            },
            page_name="Page 1",
            page_index=0,
        )

        self.assertEqual(len(segments), 1)
        self.assertEqual(
            segments[0].original_text,
            "現在会社が持っているデータのままを使い、ChatBot用のデータ構築は自動",
        )
        self.assertEqual(
            segments[0].locator["source_block_indexes"],
            "[0, 1, 2]",
        )

    def test_build_page_segments_merges_same_line_fragments_without_merging_other_rows(self) -> None:
        segments = _build_page_segments(
            payload={
                "rec_texts": [
                    "5ヶ月（2024年～現",
                    "Website",
                    "在)",
                ],
                "rec_boxes": [
                    [120, 100, 260, 118],
                    [120, 140, 220, 160],
                    [262, 100, 292, 118],
                ],
                "rec_scores": [0.99, 0.98, 0.97],
                "doc_preprocessor_res": {
                    "output_img": _ShapeStub(height=400, width=600),
                },
            },
            page_name="Page 1",
            page_index=0,
        )

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].original_text, "5ヶ月（2024年～現在)")
        self.assertEqual(segments[1].original_text, "Website")

    def test_render_image_document_exports_png_with_original_size(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "screen.png"
            image_path.write_bytes(build_test_ocr_image())
            renderer = PillowOcrLayoutRenderer(font_path=_resolve_test_font_path())

            rendered = renderer.render_document(
                file_path=image_path,
                file_type="image",
                translated_segments=[
                    RenderableOcrSegment(
                        page_name="Image 1",
                        block_label="Block 1",
                        locator={
                            "page_index": "0",
                            "block_index": "0",
                            "page_width": "400",
                            "page_height": "200",
                            "box": "[40, 40, 220, 90]",
                        },
                        final_text="Rendered image translation",
                    )
                ],
            )

            self.assertEqual(rendered.output_suffix, ".png")
            self.assertEqual(rendered.media_type, "image/png")
            self.assertEqual(rendered.file_bytes[:8], b"\x89PNG\r\n\x1a\n")
            rendered_image = Image.open(io.BytesIO(rendered.file_bytes))
            self.assertEqual(rendered_image.size, (400, 200))

    def test_render_image_document_wraps_single_word_to_fit_narrow_ocr_box(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "narrow-screen.png"
            image_path.write_bytes(build_test_ocr_image())
            renderer = PillowOcrLayoutRenderer(font_path=_resolve_test_font_path())

            rendered = renderer.render_document(
                file_path=image_path,
                file_type="image",
                translated_segments=[
                    RenderableOcrSegment(
                        page_name="Image 1",
                        block_label="Block 22",
                        locator={
                            "page_index": "0",
                            "block_index": "0",
                            "page_width": "400",
                            "page_height": "200",
                            "box": "[40, 40, 68, 120]",
                        },
                        final_text="camera",
                    )
                ],
            )

            self.assertEqual(rendered.output_suffix, ".png")
            self.assertEqual(rendered.media_type, "image/png")
            self.assertEqual(rendered.file_bytes[:8], b"\x89PNG\r\n\x1a\n")

    def test_render_image_document_expands_tight_ocr_box_for_longer_translation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "tight-screen.png"
            image_path.write_bytes(build_test_ocr_image())
            renderer = PillowOcrLayoutRenderer(font_path=_resolve_test_font_path())

            rendered = renderer.render_document(
                file_path=image_path,
                file_type="image",
                translated_segments=[
                    RenderableOcrSegment(
                        page_name="Image 1",
                        block_label="Block 22",
                        locator={
                            "page_index": "0",
                            "block_index": "0",
                            "page_width": "400",
                            "page_height": "200",
                            "box": "[120, 60, 193, 74]",
                        },
                        final_text="Noi chuyen voi van ban",
                    )
                ],
            )

            self.assertEqual(rendered.output_suffix, ".png")
            self.assertEqual(rendered.media_type, "image/png")
            self.assertEqual(rendered.file_bytes[:8], b"\x89PNG\r\n\x1a\n")

    def test_render_pdf_document_exports_pdf_with_original_page_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "scan.pdf"
            pdf_path.write_bytes(build_test_ocr_pdf())
            renderer = PillowOcrLayoutRenderer(font_path=_resolve_test_font_path())

            rendered = renderer.render_document(
                file_path=pdf_path,
                file_type="pdf",
                translated_segments=[
                    RenderableOcrSegment(
                        page_name="Page 1",
                        block_label="Block 1",
                        locator={
                            "page_index": "0",
                            "block_index": "0",
                            "page_width": "400",
                            "page_height": "200",
                            "box": "[40, 40, 180, 90]",
                        },
                        final_text="Rendered pdf heading",
                    ),
                    RenderableOcrSegment(
                        page_name="Page 2",
                        block_label="Block 1",
                        locator={
                            "page_index": "1",
                            "block_index": "0",
                            "page_width": "400",
                            "page_height": "200",
                            "box": "[40, 40, 220, 90]",
                        },
                        final_text="Rendered pdf body",
                    ),
                ],
            )

            self.assertEqual(rendered.output_suffix, ".pdf")
            self.assertEqual(rendered.media_type, "application/pdf")
            self.assertTrue(rendered.file_bytes.startswith(b"%PDF"))
            temp_output = Path(temp_dir) / "rendered.pdf"
            temp_output.write_bytes(rendered.file_bytes)

            import pypdfium2 as pdfium

            pdf_document = pdfium.PdfDocument(str(temp_output))
            try:
                self.assertEqual(len(pdf_document), 2)
            finally:
                pdf_document.close()


if __name__ == "__main__":
    unittest.main()
