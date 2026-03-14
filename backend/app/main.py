from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import AppConfig, get_config
from .correction_repository import CorrectionRepository
from .database import connect_database, initialize_database
from .domain import JobRecord, SegmentRecord
from .glossary_repository import GlossaryExactRecord, GlossaryRepository, ProtectedTermRecord
from .memory_repository import TranslationMemoryRecord, TranslationMemoryRepository
from .repository import JobRepository
from .frontend_delivery import register_frontend_delivery
from .schemas import (
    ExcelTranslateJobRequest,
    DownloadReadyResponse,
    GlossaryEntryModel,
    GlossaryEntryUpsertRequest,
    JobSummaryModel,
    KnowledgeSummaryModel,
    LanguagePairModel,
    PreviewResponse,
    ProtectedTermModel,
    ProtectedTermUpsertRequest,
    SegmentListResponse,
    SegmentModel,
    SegmentUpdateRequest,
    TranslateRequest,
    TranslateResponse,
    TranslationMemoryEntryModel,
    TranslationMemoryEntryUpsertRequest,
)
from .services.excel_jobs import ExcelJobError, ExcelJobService
from .services.glossary import GlossaryService
from .services.knowledge_base import KnowledgeBaseError, KnowledgeBaseService
from .services.knowledge_translation import KnowledgeAwareTranslationService
from .services.ocr_document import PaddleOcrService, SupportsDocumentOcr
from .services.ocr_layout import PillowOcrLayoutRenderer, SupportsOcrLayoutRenderer
from .services.translation import SupportsTranslation, TranslationError, TranslationService


class AppState:
    def __init__(
        self,
        *,
        config: AppConfig,
        connection: sqlite3.Connection,
        repository: JobRepository,
        memory_repository: TranslationMemoryRepository,
        correction_repository: CorrectionRepository,
        translation_service: SupportsTranslation,
        ocr_service: SupportsDocumentOcr,
        ocr_layout_renderer: SupportsOcrLayoutRenderer,
        excel_job_service: ExcelJobService,
        glossary: GlossaryService,
        knowledge_base_service: KnowledgeBaseService,
    ) -> None:
        self.config = config
        self.connection = connection
        self.repository = repository
        self.memory_repository = memory_repository
        self.correction_repository = correction_repository
        self.translation_service = translation_service
        self.ocr_service = ocr_service
        self.ocr_layout_renderer = ocr_layout_renderer
        self.excel_job_service = excel_job_service
        self.glossary = glossary
        self.knowledge_base_service = knowledge_base_service


def create_app(
    *,
    config: AppConfig | None = None,
    translation_service: SupportsTranslation | None = None,
    ocr_service: SupportsDocumentOcr | None = None,
    ocr_layout_renderer: SupportsOcrLayoutRenderer | None = None,
) -> FastAPI:
    app_config = config or get_config()
    connection = connect_database(app_config.database_path)
    initialize_database(connection)
    repository = JobRepository(connection)
    memory_repository = TranslationMemoryRepository(connection)
    correction_repository = CorrectionRepository(connection)
    glossary_repository = GlossaryRepository(connection)
    glossary = GlossaryService(
        glossary_path=app_config.glossary_path
        or app_config.root_dir / "backend" / "app" / "data" / "it_glossary.json",
        repository=glossary_repository,
    )
    knowledge_base_service = KnowledgeBaseService(
        glossary=glossary,
        memory_repository=memory_repository,
    )
    base_translation_service = translation_service or TranslationService(
        models_dir=app_config.models_dir
    )
    resolved_translation_service = KnowledgeAwareTranslationService(
        delegate=base_translation_service,
        memory_repository=memory_repository,
        glossary=glossary,
    )
    resolved_ocr_service = ocr_service or PaddleOcrService(
        models_dir=app_config.models_dir
    )
    resolved_ocr_layout_renderer = ocr_layout_renderer or PillowOcrLayoutRenderer()
    excel_job_service = ExcelJobService(
        config=app_config,
        repository=repository,
        memory_repository=memory_repository,
        correction_repository=correction_repository,
        translation_service=resolved_translation_service,
        ocr_service=resolved_ocr_service,
        ocr_layout_renderer=resolved_ocr_layout_renderer,
        glossary=glossary,
    )
    app_state = AppState(
        config=app_config,
        connection=connection,
        repository=repository,
        memory_repository=memory_repository,
        correction_repository=correction_repository,
        translation_service=resolved_translation_service,
        ocr_service=resolved_ocr_service,
        ocr_layout_renderer=resolved_ocr_layout_renderer,
        excel_job_service=excel_job_service,
        glossary=glossary,
        knowledge_base_service=knowledge_base_service,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        app_state.connection.close()

    app = FastAPI(title="Local Translator API", version="0.2.0", lifespan=lifespan)
    app.state.services = app_state
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_routes(app)
    register_frontend_delivery(app, frontend_dist_dir=app_config.frontend_dist_dir)
    return app


def get_state(app: FastAPI) -> AppState:
    return app.state.services


def _job_to_model(job: JobRecord) -> JobSummaryModel:
    output_file_name = Path(job.output_file_path).name if job.output_file_path else None
    preview_summary = dict(job.preview_summary)
    if job.preview_ready and "kind" not in preview_summary:
        preview_summary["kind"] = job.file_type
    return JobSummaryModel(
        id=job.id,
        original_file_name=job.original_file_name,
        file_type=job.file_type,
        status=job.status,
        current_step=job.current_step,
        progress_percent=job.progress_percent,
        processed_segments=job.processed_segments,
        total_segments=job.total_segments,
        status_message=job.status_message,
        current_sheet=job.current_sheet,
        current_cell=job.current_cell,
        preview_ready=job.preview_ready,
        preview_summary=preview_summary,
        source_language=job.source_language,
        target_language=job.target_language,
        parse_summary=job.parse_summary,
        translation_summary=job.translation_summary,
        output_file_name=output_file_name,
        updated_at=job.updated_at.isoformat() + "Z",
    )


def _segment_to_model(segment: SegmentRecord) -> SegmentModel:
    return SegmentModel(
        id=segment.id,
        order_index=segment.order_index,
        sheet_name=segment.sheet_name,
        sheet_index=segment.sheet_index,
        cell_address=segment.cell_address,
        location_type=segment.location_type,
        original_text=segment.original_text,
        normalized_text=segment.normalized_text,
        machine_translation=segment.machine_translation,
        edited_translation=segment.edited_translation,
        final_text=segment.final_text,
        intermediate_translation=segment.intermediate_translation,
        status=segment.status,
        warning_codes=segment.warning_codes,
        error_message=segment.error_message,
    )


def _glossary_entry_to_model(entry: GlossaryExactRecord) -> GlossaryEntryModel:
    return GlossaryEntryModel(
        id=entry.id,
        source_language=entry.source_language,
        target_language=entry.target_language,
        source_text=entry.source_text,
        translated_text=entry.translated_text,
        updated_at=entry.updated_at.isoformat() + "Z",
    )


def _protected_term_to_model(term: ProtectedTermRecord) -> ProtectedTermModel:
    return ProtectedTermModel(
        id=term.id,
        term=term.term,
        updated_at=term.updated_at.isoformat() + "Z",
    )


def _memory_entry_to_model(entry: TranslationMemoryRecord) -> TranslationMemoryEntryModel:
    return TranslationMemoryEntryModel(
        id=entry.id,
        source_language=entry.source_language,
        target_language=entry.target_language,
        source_text=entry.source_text,
        translated_text=entry.translated_text,
        updated_at=entry.updated_at.isoformat() + "Z",
    )


def register_routes(app: FastAPI) -> None:
    def media_type_from_suffix(suffix: str) -> str:
        if suffix == ".xlsx":
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if suffix == ".pptx":
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        if suffix == ".pdf":
            return "application/pdf"
        if suffix == ".png":
            return "image/png"
        if suffix in {".jpg", ".jpeg"}:
            return "image/jpeg"
        if suffix == ".bmp":
            return "image/bmp"
        if suffix == ".webp":
            return "image/webp"
        raise HTTPException(status_code=400, detail=f"Unsupported file suffix: {suffix}.")

    def download_media_type(job: JobRecord) -> str:
        if job.output_file_path:
            return media_type_from_suffix(Path(job.output_file_path).suffix.lower())
        if job.file_type == "xlsx":
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if job.file_type == "pptx":
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        if job.file_type == "pdf":
            return "application/pdf"
        if job.file_type == "image":
            return "image/png"
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {job.file_type}.")

    def source_media_type(job: JobRecord) -> str:
        return media_type_from_suffix(Path(job.original_file_path).suffix.lower())

    @app.get("/api/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/languages", response_model=list[LanguagePairModel])
    def list_languages() -> list[dict[str, object]]:
        service = get_state(app).translation_service
        return service.available_pairs()

    @app.get("/api/knowledge/summary", response_model=KnowledgeSummaryModel)
    def knowledge_summary() -> KnowledgeSummaryModel:
        summary = get_state(app).knowledge_base_service.summary()
        return KnowledgeSummaryModel(
            glossary_count=summary.glossary_count,
            protected_term_count=summary.protected_term_count,
            memory_count=summary.memory_count,
        )

    @app.get("/api/knowledge/glossary", response_model=list[GlossaryEntryModel])
    def list_glossary_entries() -> list[GlossaryEntryModel]:
        entries = get_state(app).knowledge_base_service.list_glossary_entries()
        return [_glossary_entry_to_model(entry) for entry in entries]

    @app.post("/api/knowledge/glossary", response_model=GlossaryEntryModel)
    def save_glossary_entry(payload: GlossaryEntryUpsertRequest) -> GlossaryEntryModel:
        service = get_state(app).knowledge_base_service
        try:
            entry = service.save_glossary_entry(
                entry_id=payload.id,
                source_language=payload.source_language,
                target_language=payload.target_language,
                source_text=payload.source_text,
                translated_text=payload.translated_text,
            )
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _glossary_entry_to_model(entry)

    @app.delete("/api/knowledge/glossary/{entry_id}", status_code=204)
    def delete_glossary_entry(entry_id: str) -> Response:
        service = get_state(app).knowledge_base_service
        try:
            service.delete_glossary_entry(entry_id)
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.get("/api/knowledge/protected-terms", response_model=list[ProtectedTermModel])
    def list_protected_terms() -> list[ProtectedTermModel]:
        terms = get_state(app).knowledge_base_service.list_protected_terms()
        return [_protected_term_to_model(term) for term in terms]

    @app.post("/api/knowledge/protected-terms", response_model=ProtectedTermModel)
    def save_protected_term(payload: ProtectedTermUpsertRequest) -> ProtectedTermModel:
        service = get_state(app).knowledge_base_service
        try:
            term = service.save_protected_term(term_id=payload.id, term=payload.term)
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _protected_term_to_model(term)

    @app.delete("/api/knowledge/protected-terms/{term_id}", status_code=204)
    def delete_protected_term(term_id: str) -> Response:
        service = get_state(app).knowledge_base_service
        try:
            service.delete_protected_term(term_id)
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.get("/api/knowledge/memory", response_model=list[TranslationMemoryEntryModel])
    def list_translation_memory_entries() -> list[TranslationMemoryEntryModel]:
        entries = get_state(app).knowledge_base_service.list_memory_entries()
        return [_memory_entry_to_model(entry) for entry in entries]

    @app.post("/api/knowledge/memory", response_model=TranslationMemoryEntryModel)
    def save_translation_memory_entry(
        payload: TranslationMemoryEntryUpsertRequest,
    ) -> TranslationMemoryEntryModel:
        service = get_state(app).knowledge_base_service
        try:
            entry = service.save_memory_entry(
                entry_id=payload.id,
                source_language=payload.source_language,
                target_language=payload.target_language,
                source_text=payload.source_text,
                translated_text=payload.translated_text,
            )
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _memory_entry_to_model(entry)

    @app.delete("/api/knowledge/memory/{entry_id}", status_code=204)
    def delete_translation_memory_entry(entry_id: str) -> Response:
        service = get_state(app).knowledge_base_service
        try:
            service.delete_memory_entry(entry_id)
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.post("/api/translate", response_model=TranslateResponse)
    def translate(payload: TranslateRequest) -> TranslateResponse:
        service = get_state(app).translation_service
        try:
            result = service.translate(
                payload.text,
                payload.source_language,
                payload.target_language,
            )
        except TranslationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return TranslateResponse(
            source_language=payload.source_language,
            target_language=payload.target_language,
            translation=result.translation,
            intermediate_translation=result.intermediate_translation,
            model_chain=result.model_chain,
        )

    @app.post("/api/excel/jobs/upload", response_model=JobSummaryModel)
    async def upload_excel_job(
        request: Request,
        file_name: str = Query(..., min_length=1),
    ) -> JobSummaryModel:
        file_bytes = await request.body()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        service = get_state(app).excel_job_service
        try:
            job = service.create_job(file_name=file_name, file_bytes=file_bytes)
        except ExcelJobError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _job_to_model(job)

    @app.get("/api/excel/jobs", response_model=list[JobSummaryModel])
    def list_excel_jobs() -> list[JobSummaryModel]:
        repository = get_state(app).repository
        return [_job_to_model(job) for job in repository.list_jobs()]

    @app.get("/api/excel/jobs/{job_id}", response_model=JobSummaryModel)
    def get_excel_job(job_id: str) -> JobSummaryModel:
        service = get_state(app).excel_job_service
        try:
            job = service.get_job(job_id)
        except ExcelJobError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _job_to_model(job)

    @app.delete("/api/excel/jobs/{job_id}", status_code=204)
    def delete_excel_job(job_id: str) -> Response:
        service = get_state(app).excel_job_service
        try:
            service.delete_job(job_id)
        except ExcelJobError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.get("/api/excel/jobs/{job_id}/segments", response_model=SegmentListResponse)
    def list_excel_segments(
        job_id: str,
        sheet_name: str | None = Query(default=None),
        status: str | None = Query(default=None),
        query: str | None = Query(default=None),
    ) -> SegmentListResponse:
        service = get_state(app).excel_job_service
        try:
            segments = service.list_segments(
                job_id,
                sheet_name=sheet_name,
                status=status,
                query=query,
            )
        except ExcelJobError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        items = [_segment_to_model(segment) for segment in segments]
        return SegmentListResponse(items=items, total=len(items))

    @app.post("/api/excel/jobs/{job_id}/start", response_model=JobSummaryModel)
    def start_excel_job(job_id: str, payload: ExcelTranslateJobRequest) -> JobSummaryModel:
        service = get_state(app).excel_job_service
        try:
            job = service.start_job(
                job_id,
                source_language=payload.source_language,
                target_language=payload.target_language,
            )
        except ExcelJobError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _job_to_model(job)

    @app.patch("/api/excel/jobs/{job_id}/segments/{segment_id}", response_model=SegmentModel)
    def update_excel_segment(
        job_id: str,
        segment_id: str,
        payload: SegmentUpdateRequest,
    ) -> SegmentModel:
        service = get_state(app).excel_job_service
        try:
            segment = service.update_segment_final_text(
                job_id,
                segment_id,
                payload.final_text,
            )
        except ExcelJobError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _segment_to_model(segment)

    @app.post("/api/excel/jobs/{job_id}/review-complete", response_model=JobSummaryModel)
    def complete_excel_job_review(job_id: str) -> JobSummaryModel:
        service = get_state(app).excel_job_service
        try:
            job = service.complete_review(job_id)
        except ExcelJobError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _job_to_model(job)

    @app.post("/api/excel/jobs/{job_id}/preview", response_model=PreviewResponse)
    def preview_excel_job(job_id: str) -> PreviewResponse:
        service = get_state(app).excel_job_service
        try:
            preview = service.generate_preview(job_id)
        except ExcelJobError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return PreviewResponse(summary=preview.summary)

    @app.post("/api/excel/jobs/{job_id}/download", response_model=DownloadReadyResponse)
    def prepare_download(job_id: str) -> DownloadReadyResponse:
        service = get_state(app).excel_job_service
        try:
            exported = service.download_job(job_id)
        except ExcelJobError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return DownloadReadyResponse(file_name=exported.file_name)

    @app.get("/api/excel/jobs/{job_id}/download")
    def download_excel_job(job_id: str) -> Response:
        service = get_state(app).excel_job_service
        try:
            job = service.get_job(job_id)
        except ExcelJobError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if job.output_file_path is None:
            raise HTTPException(status_code=404, detail="Exported document was not found.")
        return FileResponse(
            path=job.output_file_path,
            media_type=download_media_type(job),
            filename=Path(job.output_file_path).name,
        )

    @app.get("/api/excel/jobs/{job_id}/source-document")
    def source_excel_job_document(job_id: str) -> Response:
        service = get_state(app).excel_job_service
        try:
            job = service.get_job(job_id)
        except ExcelJobError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(
            path=job.original_file_path,
            media_type=source_media_type(job),
            filename=Path(job.original_file_path).name,
        )


@lru_cache
def get_app() -> FastAPI:
    return create_app()


app = get_app()
