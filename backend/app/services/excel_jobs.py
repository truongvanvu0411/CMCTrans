from __future__ import annotations

import math
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..config import AppConfig
from ..correction_repository import CorrectionRecord, CorrectionRepository
from ..domain import JobRecord, SegmentRecord
from ..memory_repository import TranslationMemoryRepository
from ..repository import JobRepository
from .excel_ooxml import (
    ExcelOOXMLError,
    ExtractedSegment,
    ParsedWorkbook,
    ParseProgress as ExcelParseProgress,
    build_preview_layout,
    build_sheet_name_updates,
    export_workbook,
    list_workbook_sheet_names,
    parse_workbook,
)
from .glossary import GlossaryService
from .ocr_document import (
    DocumentOcrError,
    ExtractedOcrSegment,
    ParsedOcrDocument,
    SupportsDocumentOcr,
)
from .ocr_layout import (
    DocumentLayoutError,
    RenderableOcrSegment,
    SupportsOcrLayoutRenderer,
)
from .pptx_ooxml import (
    ExtractedSlideSegment,
    ParseProgress as PptxParseProgress,
    ParsedPresentation,
    PptxOOXMLError,
    build_presentation_preview,
    export_presentation,
    parse_presentation,
)
from .text_quality import build_clean_correction
from .translation import SupportsTranslation, TranslationError


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _requires_sheet_name_translation(sheet_name: str) -> bool:
    return any(ord(character) > 127 for character in sheet_name)


def _document_label(file_type: str) -> str:
    if file_type == "xlsx":
        return "workbook"
    if file_type == "pptx":
        return "presentation"
    if file_type == "pdf":
        return "PDF document"
    if file_type == "image":
        return "image document"
    return "document"


def _resolve_upload_file_type(file_name: str) -> tuple[str, str]:
    lower_file_name = file_name.lower()
    if lower_file_name.endswith(".xlsx"):
        return "xlsx", ".xlsx"
    if lower_file_name.endswith(".pptx"):
        return "pptx", ".pptx"
    if lower_file_name.endswith(".pdf"):
        return "pdf", ".pdf"
    for image_suffix in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
        if lower_file_name.endswith(image_suffix):
            return "image", image_suffix
    raise ExcelJobError(
        "Only .xlsx, .pptx, .pdf, .png, .jpg, .jpeg, .bmp, and .webp files are supported."
    )


def _parsed_segments(
    parsed_document: ParsedWorkbook | ParsedPresentation | ParsedOcrDocument,
) -> list[ExtractedSegment | ExtractedSlideSegment | ExtractedOcrSegment]:
    return parsed_document.segments


def _parsed_summary(
    parsed_document: ParsedWorkbook | ParsedPresentation | ParsedOcrDocument,
) -> dict[str, object]:
    return parsed_document.parse_summary


def _segment_location_type(
    segment: ExtractedSegment | ExtractedSlideSegment | ExtractedOcrSegment,
) -> str:
    if isinstance(segment, ExtractedSlideSegment):
        return segment.location_type
    if isinstance(segment, ExtractedOcrSegment):
        return segment.location_type
    return "worksheet_cell"


def _segment_group_name(
    segment: ExtractedSegment | ExtractedSlideSegment | ExtractedOcrSegment,
) -> str:
    if isinstance(segment, ExtractedSlideSegment):
        return segment.slide_name
    if isinstance(segment, ExtractedOcrSegment):
        return segment.page_name
    return segment.sheet_name


def _segment_reference(
    segment: ExtractedSegment | ExtractedSlideSegment | ExtractedOcrSegment,
) -> str:
    if isinstance(segment, ExtractedSlideSegment):
        return segment.object_label
    if isinstance(segment, ExtractedOcrSegment):
        return segment.block_label
    return segment.cell_address


def _segment_index(
    segment: ExtractedSegment | ExtractedSlideSegment | ExtractedOcrSegment,
) -> int:
    if isinstance(segment, ExtractedSlideSegment):
        return segment.slide_index
    if isinstance(segment, ExtractedOcrSegment):
        return segment.page_index
    return segment.sheet_index


class ExcelJobError(Exception):
    """Raised when Excel job operations fail."""


@dataclass(frozen=True)
class ExportedWorkbook:
    file_path: Path
    file_name: str


@dataclass(frozen=True)
class PreviewArtifact:
    summary: dict[str, object]


class ExcelJobService:
    def __init__(
        self,
        *,
        config: AppConfig,
        repository: JobRepository,
        memory_repository: TranslationMemoryRepository,
        correction_repository: CorrectionRepository,
        translation_service: SupportsTranslation,
        ocr_service: SupportsDocumentOcr,
        ocr_layout_renderer: SupportsOcrLayoutRenderer,
        glossary: GlossaryService,
    ) -> None:
        self._config = config
        self._repository = repository
        self._memory_repository = memory_repository
        self._correction_repository = correction_repository
        self._translation_service = translation_service
        self._ocr_service = ocr_service
        self._ocr_layout_renderer = ocr_layout_renderer
        self._glossary = glossary
        self._active_jobs: set[str] = set()
        self._active_jobs_lock = threading.Lock()
        (self._config.workspace_dir / "jobs").mkdir(parents=True, exist_ok=True)

    def create_job(self, *, file_name: str, file_bytes: bytes) -> JobRecord:
        file_type, original_suffix = _resolve_upload_file_type(file_name)

        job_id = str(uuid.uuid4())
        job_dir = self._config.workspace_dir / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        original_file_path = job_dir / f"original{original_suffix}"
        original_file_path.write_bytes(file_bytes)

        now = _utc_now()
        initial_record = JobRecord(
            id=job_id,
            original_file_name=file_name,
            original_file_path=str(original_file_path),
            output_file_path=None,
            file_type=file_type,
            status="uploaded",
            current_step="uploaded",
            progress_percent=0,
            processed_segments=0,
            total_segments=0,
            status_message="File uploaded. Ready to start.",
            current_sheet=None,
            current_cell=None,
            preview_ready=False,
            preview_summary={},
            source_language=None,
            target_language=None,
            parse_summary={"status": "not_started"},
            translation_summary={"status": "not_started"},
            created_at=now,
            updated_at=now,
        )
        self._repository.create_job(initial_record)
        created_job = self._repository.get_job(job_id)
        if created_job is None:
            raise ExcelJobError("Created job could not be loaded.")
        return created_job

    def get_job(self, job_id: str) -> JobRecord:
        record = self._repository.get_job(job_id)
        if record is None:
            raise ExcelJobError(f"Job {job_id} was not found.")
        return record

    def list_segments(
        self,
        job_id: str,
        *,
        sheet_name: str | None,
        status: str | None,
        query: str | None,
    ) -> list[SegmentRecord]:
        self.get_job(job_id)
        return self._repository.list_segments(
            job_id,
            sheet_name=sheet_name,
            status=status,
            query=query,
        )

    def delete_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        with self._active_jobs_lock:
            if job_id in self._active_jobs:
                raise ExcelJobError("This job is running and cannot be deleted.")

        job_dir = Path(job.original_file_path).parent
        if not job_dir.exists():
            raise ExcelJobError("Job workspace directory was not found.")
        try:
            shutil.rmtree(job_dir)
        except OSError as exc:
            raise ExcelJobError(f"Could not delete job files: {exc}") from exc
        self._repository.delete_job(job_id)

    def start_job(
        self, job_id: str, *, source_language: str, target_language: str
    ) -> JobRecord:
        job = self.get_job(job_id)
        if job.status not in {"uploaded", "failed"}:
            raise ExcelJobError("Only uploaded or failed jobs can be started.")

        with self._active_jobs_lock:
            if job_id in self._active_jobs:
                raise ExcelJobError("This job is already running.")
            self._active_jobs.add(job_id)

        self._update_job(
            job_id,
            status="queued",
            current_step="queued",
            progress_percent=5,
            processed_segments=0,
            total_segments=0,
            status_message="Job queued and waiting to start parsing.",
            current_sheet=None,
            current_cell=None,
            preview_ready=False,
            preview_summary={},
            source_language=source_language,
            target_language=target_language,
            parse_summary={"status": "queued"},
            translation_summary={"status": "queued"},
            output_file_path=None,
        )

        worker = threading.Thread(
            target=self._process_job,
            args=(job_id, source_language, target_language),
            daemon=True,
        )
        worker.start()
        return self.get_job(job_id)

    def update_segment_final_text(
        self, job_id: str, segment_id: str, final_text: str
    ) -> SegmentRecord:
        job = self.get_job(job_id)
        if job.status not in {"review", "completed"}:
            raise ExcelJobError("Segments can only be edited after translation is complete.")
        segment = self._repository.get_segment(job_id, segment_id)
        if segment is None:
            raise ExcelJobError(f"Segment {segment_id} was not found in job {job_id}.")
        source_language = job.source_language
        target_language = job.target_language
        if source_language is None or target_language is None:
            raise ExcelJobError("Job language route is missing.")
        self._repository.update_segment(
            job_id=job_id,
            segment_id=segment_id,
            machine_translation=segment.machine_translation,
            edited_translation=final_text,
            final_text=final_text,
            intermediate_translation=segment.intermediate_translation,
            status="edited",
            error_message=None,
            updated_at=_utc_now(),
        )
        self._update_job(
            job_id,
            status="review",
            current_step="review",
            progress_percent=96,
            processed_segments=job.processed_segments,
            total_segments=job.total_segments,
            status_message="Review updated. Download will rebuild the document.",
            current_sheet=None,
            current_cell=None,
            preview_ready=False,
            preview_summary={},
            source_language=job.source_language,
            target_language=job.target_language,
            parse_summary=job.parse_summary,
            translation_summary=job.translation_summary,
            output_file_path=job.output_file_path,
        )
        clean_correction = build_clean_correction(
            source_text=segment.normalized_text,
            machine_translation=segment.machine_translation,
            corrected_translation=final_text,
            glossary=self._glossary,
        )
        if clean_correction is not None:
            now = _utc_now()
            self._upsert_bidirectional_memory(
                source_language=source_language,
                target_language=target_language,
                source_text=clean_correction.source_text,
                translated_text=clean_correction.corrected_translation,
                now=now,
            )
            self._correction_repository.create(
                CorrectionRecord(
                    id=str(uuid.uuid4()),
                    job_id=job_id,
                    segment_id=segment_id,
                    source_language=source_language,
                    target_language=target_language,
                    source_text=clean_correction.source_text,
                    machine_translation=clean_correction.machine_translation,
                    corrected_translation=clean_correction.corrected_translation,
                    created_at=now,
                )
            )
        updated_segment = self._repository.get_segment(job_id, segment_id)
        if updated_segment is None:
            raise ExcelJobError("Updated segment could not be loaded.")
        return updated_segment

    def complete_review(self, job_id: str) -> JobRecord:
        job = self.get_job(job_id)
        if job.status != "review":
            raise ExcelJobError("Job must be in review state before marking review done.")
        self._update_job(
            job_id,
            status="completed",
            current_step="review",
            progress_percent=97,
            processed_segments=job.processed_segments,
            total_segments=job.total_segments,
            status_message="Review complete. Download is ready.",
            current_sheet=None,
            current_cell=None,
            preview_ready=job.preview_ready,
            preview_summary=job.preview_summary,
            source_language=job.source_language,
            target_language=job.target_language,
            parse_summary=job.parse_summary,
            translation_summary=job.translation_summary,
            output_file_path=job.output_file_path,
        )
        return self.get_job(job_id)

    def _upsert_bidirectional_memory(
        self,
        *,
        source_language: str,
        target_language: str,
        source_text: str,
        translated_text: str,
        now: datetime,
    ) -> None:
        self._memory_repository.upsert(
            entry_id=str(uuid.uuid4()),
            source_language=source_language,
            target_language=target_language,
            source_text=source_text,
            translated_text=translated_text,
            created_at=now,
            updated_at=now,
        )
        if source_language == target_language:
            return
        self._memory_repository.upsert(
            entry_id=str(uuid.uuid4()),
            source_language=target_language,
            target_language=source_language,
            source_text=translated_text,
            translated_text=source_text,
            created_at=now,
            updated_at=now,
        )

    def _translate_sheet_name_updates(self, job: JobRecord) -> dict[str, str]:
        if job.file_type != "xlsx":
            return {}
        source_language = job.source_language
        target_language = job.target_language
        if source_language is None or target_language is None:
            raise ExcelJobError("Job language route is missing.")
        workbook_bytes = Path(job.original_file_path).read_bytes()
        try:
            original_sheet_names = list_workbook_sheet_names(workbook_bytes)
        except ExcelOOXMLError as exc:
            raise ExcelJobError(str(exc)) from exc
        if not original_sheet_names:
            return {}
        pending_indexes = [
            index
            for index, sheet_name in enumerate(original_sheet_names)
            if _requires_sheet_name_translation(sheet_name)
        ]
        translated_sheet_names = list(original_sheet_names)
        if not pending_indexes:
            try:
                return build_sheet_name_updates(
                    original_sheet_names=original_sheet_names,
                    translated_sheet_names=translated_sheet_names,
                )
            except ExcelOOXMLError as exc:
                raise ExcelJobError(str(exc)) from exc
        try:
            translations = self._translation_service.translate_many(
                [original_sheet_names[index] for index in pending_indexes],
                source_language,
                target_language,
            )
        except TranslationError as exc:
            raise ExcelJobError(str(exc)) from exc
        for index, translation in zip(pending_indexes, translations, strict=True):
            translated_sheet_names[index] = translation.translation
        try:
            return build_sheet_name_updates(
                original_sheet_names=original_sheet_names,
                translated_sheet_names=translated_sheet_names,
            )
        except ExcelOOXMLError as exc:
            raise ExcelJobError(str(exc)) from exc

    def generate_preview(self, job_id: str) -> PreviewArtifact:
        job = self.get_job(job_id)
        if job.status not in {"review", "completed"}:
            raise ExcelJobError("Preview is only available after translation completes.")

        segments = self._repository.list_segments(job_id, sheet_name=None, status=None, query=None)
        preview_segments = [
            segment
            for segment in segments
            if segment.final_text is not None and segment.status in {"translated", "edited", "approved"}
        ]
        if not preview_segments:
            raise ExcelJobError("No final translations are available for preview.")

        sheet_name_updates = self._translate_sheet_name_updates(job)
        original_file_bytes = Path(job.original_file_path).read_bytes()
        try:
            if job.file_type == "xlsx":
                preview_summary = build_preview_layout(
                    original_file_bytes=original_file_bytes,
                    translated_segments=[
                        {
                            "sheet_name": segment.sheet_name,
                            "cell_address": segment.cell_address,
                            "original_text": segment.original_text,
                            "final_text": segment.final_text,
                            "status": segment.status,
                        }
                        for segment in preview_segments
                    ],
                    sheet_name_updates=sheet_name_updates,
                )
            elif job.file_type == "pptx":
                preview_summary = build_presentation_preview(
                    original_file_bytes=original_file_bytes,
                    translated_segments=[
                        {
                            "segment_id": segment.id,
                            "slide_name": segment.sheet_name,
                            "object_label": segment.cell_address,
                            "original_text": segment.original_text,
                            "final_text": segment.final_text,
                            "status": segment.status,
                            "locator": segment.locator,
                        }
                        for segment in preview_segments
                    ],
                )
            else:
                raise ExcelJobError(f"Unsupported file type: {job.file_type}.")
        except (ExcelOOXMLError, PptxOOXMLError) as exc:
            raise ExcelJobError(str(exc)) from exc
        preview_summary["edited_segments"] = len(
            [segment for segment in preview_segments if segment.status == "edited"]
        )
        preview_summary["total_preview_rows"] = len(preview_segments)
        if job.file_type == "pptx":
            self._apply_pptx_layout_warnings(job_id, preview_segments, preview_summary)
        self._update_job(
            job_id,
            status="review",
            current_step="preview",
            progress_percent=98,
            processed_segments=job.processed_segments,
            total_segments=job.total_segments,
            status_message="Preview is ready.",
            current_sheet=None,
            current_cell=None,
            preview_ready=True,
            preview_summary=preview_summary,
            source_language=job.source_language,
            target_language=job.target_language,
            parse_summary=job.parse_summary,
            translation_summary=job.translation_summary,
            output_file_path=job.output_file_path,
        )
        return PreviewArtifact(summary=preview_summary)

    def _apply_pptx_layout_warnings(
        self,
        job_id: str,
        preview_segments: list[SegmentRecord],
        preview_summary: dict[str, object],
    ) -> None:
        layout_warning_ids = {
            str(item["segment_id"])
            for item in preview_summary.get("layout_warnings", [])
            if isinstance(item, dict) and item.get("segment_id")
        }
        now = _utc_now()
        updates: list[tuple[str, list[str], datetime]] = []
        for segment in preview_segments:
            next_warning_codes = [
                warning_code
                for warning_code in segment.warning_codes
                if warning_code != "layout_review_required"
            ]
            if segment.id in layout_warning_ids:
                next_warning_codes.append("layout_review_required")
            if next_warning_codes != segment.warning_codes:
                updates.append((segment.id, next_warning_codes, now))
        if updates:
            self._repository.bulk_update_segment_warning_codes(job_id=job_id, updates=updates)

    def download_job(self, job_id: str) -> ExportedWorkbook:
        job = self.get_job(job_id)
        if job.status not in {"review", "completed"}:
            raise ExcelJobError("Finish review before download.")

        export_status = "completed" if job.status == "completed" else "review"
        export_progress = 97 if export_status == "completed" else 96
        export_message = (
            "Review complete. Download is ready."
            if export_status == "completed"
            else "Translation complete. Open the editor to review and download when ready."
        )

        self._update_job(
            job_id,
            status="exporting",
            current_step="download",
            progress_percent=99,
            processed_segments=job.processed_segments,
            total_segments=job.total_segments,
            status_message=f"Building translated {_document_label(job.file_type)}.",
            current_sheet=None,
            current_cell=None,
            preview_ready=job.preview_ready,
            preview_summary=job.preview_summary,
            source_language=job.source_language,
            target_language=job.target_language,
            parse_summary=job.parse_summary,
            translation_summary=job.translation_summary,
            output_file_path=job.output_file_path,
        )

        segments = self._repository.list_segments(job_id, sheet_name=None, status=None, query=None)
        exportable_segments = [
            segment
            for segment in segments
            if segment.final_text is not None and segment.status in {"translated", "edited", "approved"}
        ]
        if not exportable_segments:
            raise ExcelJobError("No final translations are available for export.")

        target_language = job.target_language
        if target_language is None:
            raise ExcelJobError("Job target language is missing.")
        sheet_name_updates = self._translate_sheet_name_updates(job)
        original_file_bytes = Path(job.original_file_path).read_bytes()
        try:
            if job.file_type == "xlsx":
                exported_bytes = export_workbook(
                    original_file_bytes=original_file_bytes,
                    segment_updates=[
                        (segment.locator, segment.final_text or "")
                        for segment in exportable_segments
                    ],
                    sheet_name_updates=sheet_name_updates,
                )
            elif job.file_type == "pptx":
                exported_bytes = export_presentation(
                    original_file_bytes=original_file_bytes,
                    segment_updates=[
                        (segment.locator, segment.final_text or "")
                        for segment in exportable_segments
                    ],
                )
            elif job.file_type in {"pdf", "image"}:
                rendered_document = self._ocr_layout_renderer.render_document(
                    file_path=Path(job.original_file_path),
                    file_type=job.file_type,
                    translated_segments=[
                        RenderableOcrSegment(
                            page_name=segment.sheet_name,
                            block_label=segment.cell_address,
                            locator=segment.locator,
                            final_text=segment.final_text or "",
                        )
                        for segment in exportable_segments
                    ],
                )
                exported_bytes = rendered_document.file_bytes
            else:
                raise ExcelJobError(f"Unsupported file type: {job.file_type}.")
        except (ExcelOOXMLError, PptxOOXMLError, DocumentOcrError, DocumentLayoutError) as exc:
            self._update_job(
                job_id,
                status=export_status,
                current_step="review",
                progress_percent=export_progress,
                processed_segments=job.processed_segments,
                total_segments=job.total_segments,
                status_message=str(exc),
                current_sheet=None,
                current_cell=None,
                preview_ready=job.preview_ready,
                preview_summary=job.preview_summary,
                source_language=job.source_language,
                target_language=job.target_language,
                parse_summary=job.parse_summary,
                translation_summary=job.translation_summary,
                output_file_path=job.output_file_path,
            )
            raise ExcelJobError(str(exc)) from exc

        if job.file_type == "xlsx":
            output_suffix = ".xlsx"
        elif job.file_type == "pptx":
            output_suffix = ".pptx"
        elif job.file_type in {"pdf", "image"}:
            output_suffix = rendered_document.output_suffix
        else:
            raise ExcelJobError(f"Unsupported file type: {job.file_type}.")
        output_file_name = f"{Path(job.original_file_name).stem}.{target_language}{output_suffix}"
        output_file_path = Path(job.original_file_path).parent / output_file_name
        output_file_path.write_bytes(exported_bytes)

        self._update_job(
            job_id,
            status="completed",
            current_step="download",
            progress_percent=100,
            processed_segments=job.processed_segments,
            total_segments=job.total_segments,
            status_message="Download is ready.",
            current_sheet=None,
            current_cell=None,
            preview_ready=job.preview_ready,
            preview_summary=job.preview_summary,
            source_language=job.source_language,
            target_language=job.target_language,
            parse_summary=job.parse_summary,
            translation_summary=job.translation_summary,
            output_file_path=str(output_file_path),
        )
        return ExportedWorkbook(file_path=output_file_path, file_name=output_file_name)

    def _process_job(self, job_id: str, source_language: str, target_language: str) -> None:
        try:
            self._run_parse(job_id, source_language, target_language)
            self._run_translation(job_id, source_language, target_language)
        except ExcelJobError as exc:
            self._fail_job(job_id, str(exc))
        except Exception as exc:
            self._fail_job(job_id, f"Unexpected processing error: {exc}")
        finally:
            with self._active_jobs_lock:
                self._active_jobs.discard(job_id)

    def _run_parse(self, job_id: str, source_language: str, target_language: str) -> None:
        job = self.get_job(job_id)

        def on_excel_parse_progress(progress: ExcelParseProgress) -> None:
            total_cells = max(progress.total_cells, 1)
            parse_percent = 10 + math.floor((progress.scanned_cells / total_cells) * 25)
            self._update_job(
                job_id,
                status="parsing",
                current_step="parsing",
                progress_percent=min(parse_percent, 35),
                processed_segments=0,
                total_segments=0,
                status_message="Parsing workbook content.",
                current_sheet=progress.current_sheet,
                current_cell=progress.current_cell,
                preview_ready=False,
                preview_summary={},
                source_language=source_language,
                target_language=target_language,
                parse_summary={"status": "running"},
                translation_summary={"status": "queued"},
                output_file_path=job.output_file_path,
            )

        def on_pptx_parse_progress(progress: PptxParseProgress) -> None:
            total_nodes = max(progress.total_nodes, 1)
            parse_percent = 10 + math.floor((progress.scanned_nodes / total_nodes) * 25)
            self._update_job(
                job_id,
                status="parsing",
                current_step="parsing",
                progress_percent=min(parse_percent, 35),
                processed_segments=0,
                total_segments=0,
                status_message="Parsing presentation content.",
                current_sheet=progress.current_slide,
                current_cell=progress.current_object,
                preview_ready=False,
                preview_summary={},
                source_language=source_language,
                target_language=target_language,
                parse_summary={"status": "running"},
                translation_summary={"status": "queued"},
                output_file_path=job.output_file_path,
            )

        self._update_job(
            job_id,
            status="parsing",
            current_step="parsing",
            progress_percent=10,
            processed_segments=0,
            total_segments=0,
            status_message="Parsing document content.",
            current_sheet=None,
            current_cell=None,
            preview_ready=False,
            preview_summary={},
            source_language=source_language,
            target_language=target_language,
            parse_summary={"status": "running"},
            translation_summary={"status": "queued"},
            output_file_path=job.output_file_path,
        )
        try:
            if job.file_type == "xlsx":
                parsed_document = parse_workbook(
                    Path(job.original_file_path).read_bytes(),
                    progress_callback=on_excel_parse_progress,
                )
            elif job.file_type == "pptx":
                parsed_document = parse_presentation(
                    Path(job.original_file_path).read_bytes(),
                    progress_callback=on_pptx_parse_progress,
                )
            elif job.file_type in {"pdf", "image"}:
                parsed_document = self._ocr_service.parse_document(
                    file_path=Path(job.original_file_path),
                    file_type=job.file_type,
                    source_language=source_language,
                )
            else:
                raise ExcelJobError(f"Unsupported file type: {job.file_type}.")
        except (ExcelOOXMLError, PptxOOXMLError, DocumentOcrError) as exc:
            raise ExcelJobError(str(exc)) from exc

        now = _utc_now()
        segments = [
            SegmentRecord(
                id=str(uuid.uuid4()),
                job_id=job_id,
                order_index=index,
                sheet_name=_segment_group_name(segment),
                sheet_index=_segment_index(segment),
                cell_address=_segment_reference(segment),
                location_type=_segment_location_type(segment),
                original_text=segment.original_text,
                normalized_text=segment.normalized_text,
                machine_translation=None,
                edited_translation=None,
                final_text=None,
                intermediate_translation=None,
                status="new",
                warning_codes=segment.warning_codes,
                locator=segment.locator,
                error_message=None,
                created_at=now,
                updated_at=now,
            )
            for index, segment in enumerate(_parsed_segments(parsed_document))
        ]
        self._repository.replace_segments(job_id, segments)
        self._update_job(
            job_id,
            status="translating",
            current_step="translating",
            progress_percent=35,
            processed_segments=0,
            total_segments=len(segments),
            status_message="Translating extracted segments.",
            current_sheet=None,
            current_cell=None,
            preview_ready=False,
            preview_summary={},
            source_language=source_language,
            target_language=target_language,
            parse_summary=_parsed_summary(parsed_document),
            translation_summary={"status": "running"},
            output_file_path=job.output_file_path,
        )

    def _run_translation(self, job_id: str, source_language: str, target_language: str) -> None:
        job = self.get_job(job_id)
        segments = self._repository.list_segments(job_id, sheet_name=None, status=None, query=None)
        if not segments:
            raise ExcelJobError(f"This {_document_label(job.file_type)} has no translatable segments.")
        empty_segments = [segment for segment in segments if not segment.normalized_text]
        if empty_segments:
            locations = ", ".join(
                f"{segment.sheet_name}!{segment.cell_address}" for segment in empty_segments[:10]
            )
            raise ExcelJobError(
                f"Encountered empty translatable segments after parsing: {locations}."
            )

        batch_size = 8
        processed_count = 0
        total_segments = len(segments)
        for offset in range(0, total_segments, batch_size):
            batch = segments[offset : offset + batch_size]
            try:
                results = self._translation_service.translate_many(
                    [segment.normalized_text for segment in batch],
                    source_language,
                    target_language,
                )
            except TranslationError as exc:
                raise ExcelJobError(str(exc)) from exc

            updates = []
            for segment, result in zip(batch, results, strict=True):
                updates.append(
                    (
                        segment.id,
                        result.translation,
                        None,
                        result.translation,
                        result.intermediate_translation,
                        "translated",
                        None,
                        _utc_now(),
                    )
                )
            self._repository.bulk_update_segments(updates, job_id=job_id)
            processed_count += len(batch)
            progress_percent = 35 + math.floor((processed_count / total_segments) * 60)
            current_segment = batch[-1]
            self._update_job(
                job_id,
                status="translating",
                current_step="translating",
                progress_percent=min(progress_percent, 95),
                processed_segments=processed_count,
                total_segments=total_segments,
                status_message="Translating extracted segments.",
                current_sheet=current_segment.sheet_name,
                current_cell=current_segment.cell_address,
                preview_ready=False,
                preview_summary={},
                source_language=source_language,
                target_language=target_language,
                parse_summary=job.parse_summary,
                translation_summary={
                    "status": "running",
                    "translated_segments": processed_count,
                    "total_segments": total_segments,
                },
                output_file_path=job.output_file_path,
            )

        self._update_job(
            job_id,
            status="review",
            current_step="review",
            progress_percent=96,
            processed_segments=total_segments,
            total_segments=total_segments,
            status_message="Translation complete. Open the editor to review and download when ready.",
            current_sheet=None,
            current_cell=None,
            preview_ready=False,
            preview_summary={},
            source_language=source_language,
            target_language=target_language,
            parse_summary=job.parse_summary,
            translation_summary={
                "status": "completed",
                "translated_segments": total_segments,
                "total_segments": total_segments,
            },
            output_file_path=job.output_file_path,
        )

    def _fail_job(self, job_id: str, error_message: str) -> None:
        job = self.get_job(job_id)
        self._update_job(
            job_id,
            status="failed",
            current_step="failed",
            progress_percent=job.progress_percent,
            processed_segments=job.processed_segments,
            total_segments=job.total_segments,
            status_message=error_message,
            current_sheet=job.current_sheet,
            current_cell=job.current_cell,
            preview_ready=job.preview_ready,
            preview_summary=job.preview_summary,
            source_language=job.source_language,
            target_language=job.target_language,
            parse_summary=job.parse_summary,
            translation_summary=job.translation_summary,
            output_file_path=job.output_file_path,
        )

    def _update_job(
        self,
        job_id: str,
        *,
        status: str,
        current_step: str,
        progress_percent: int,
        processed_segments: int,
        total_segments: int,
        status_message: str,
        current_sheet: str | None,
        current_cell: str | None,
        preview_ready: bool,
        preview_summary: dict[str, object],
        source_language: str | None,
        target_language: str | None,
        parse_summary: dict[str, object],
        translation_summary: dict[str, object],
        output_file_path: str | None,
    ) -> None:
        self._repository.update_job(
            job_id,
            status=status,
            current_step=current_step,
            progress_percent=progress_percent,
            processed_segments=processed_segments,
            total_segments=total_segments,
            status_message=status_message,
            current_sheet=current_sheet,
            current_cell=current_cell,
            preview_ready=preview_ready,
            preview_summary=preview_summary,
            source_language=source_language,
            target_language=target_language,
            parse_summary=parse_summary,
            translation_summary=translation_summary,
            output_file_path=output_file_path,
            updated_at=_utc_now(),
        )
