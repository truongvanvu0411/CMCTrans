from __future__ import annotations

import sqlite3
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .activity_repository import ActivityRepository
from .auth_repository import SessionRepository, UserRepository
from .config import AppConfig, get_config
from .correction_repository import CorrectionRepository
from .database import connect_database, initialize_database
from .domain import ActivityRecord, JobRecord, SegmentRecord, UserRecord
from .glossary_repository import GlossaryExactRecord, GlossaryRepository, ProtectedTermRecord
from .memory_repository import TranslationMemoryRecord, TranslationMemoryRepository
from .repository import JobRepository
from .frontend_delivery import register_frontend_delivery
from .schemas import (
    ActivityEntryModel,
    ActivityListResponse,
    AuthLoginRequest,
    AuthSessionModel,
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
    UserAccountModel,
    UserAccountUpsertRequest,
)
from .services.activity import ActivityQuery, ActivityService
from .services.auth import AccountService, AuthError, AuthService, AuthenticatedSession
from .services.excel_jobs import ExcelJobError, ExcelJobService
from .services.glossary import GlossaryService
from .services.knowledge_base import KnowledgeBaseError, KnowledgeBaseService
from .services.knowledge_translation import KnowledgeAwareTranslationService
from .services.legacy_excel import ExcelComLegacyConverter, SupportsLegacyExcelConverter
from .services.lazy_runtime import LazyDocumentOcrService, LazyTranslationService
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
        user_repository: UserRepository,
        translation_service: SupportsTranslation,
        ocr_service: SupportsDocumentOcr,
        ocr_layout_renderer: SupportsOcrLayoutRenderer,
        excel_job_service: ExcelJobService,
        glossary: GlossaryService,
        knowledge_base_service: KnowledgeBaseService,
        auth_service: AuthService,
        account_service: AccountService,
        activity_service: ActivityService,
    ) -> None:
        self.config = config
        self.connection = connection
        self.repository = repository
        self.memory_repository = memory_repository
        self.correction_repository = correction_repository
        self.user_repository = user_repository
        self.translation_service = translation_service
        self.ocr_service = ocr_service
        self.ocr_layout_renderer = ocr_layout_renderer
        self.excel_job_service = excel_job_service
        self.glossary = glossary
        self.knowledge_base_service = knowledge_base_service
        self.auth_service = auth_service
        self.account_service = account_service
        self.activity_service = activity_service


def create_app(
    *,
    config: AppConfig | None = None,
    translation_service: SupportsTranslation | None = None,
    ocr_service: SupportsDocumentOcr | None = None,
    ocr_layout_renderer: SupportsOcrLayoutRenderer | None = None,
    legacy_excel_converter: SupportsLegacyExcelConverter | None = None,
) -> FastAPI:
    app_config = config or get_config()
    connection = connect_database(app_config.database_path)
    initialize_database(connection)
    repository_lock = threading.RLock()
    repository = JobRepository(connection, lock=repository_lock)
    memory_repository = TranslationMemoryRepository(connection, lock=repository_lock)
    correction_repository = CorrectionRepository(connection, lock=repository_lock)
    user_repository = UserRepository(connection, lock=repository_lock)
    session_repository = SessionRepository(connection, lock=repository_lock)
    activity_repository = ActivityRepository(connection, lock=repository_lock)
    glossary_repository = GlossaryRepository(connection, lock=repository_lock)
    glossary = GlossaryService(
        glossary_path=app_config.glossary_path
        or app_config.root_dir / "backend" / "app" / "data" / "it_glossary.json",
        repository=glossary_repository,
    )
    knowledge_base_service = KnowledgeBaseService(
        glossary=glossary,
        memory_repository=memory_repository,
    )
    auth_service = AuthService(
        user_repository=user_repository,
        session_repository=session_repository,
    )
    account_service = AccountService(
        user_repository=user_repository,
        session_repository=session_repository,
    )
    activity_service = ActivityService(repository=activity_repository)
    base_translation_service = translation_service or LazyTranslationService(
        factory=lambda: TranslationService(models_dir=app_config.models_dir)
    )
    resolved_translation_service = KnowledgeAwareTranslationService(
        delegate=base_translation_service,
        memory_repository=memory_repository,
        glossary=glossary,
    )
    resolved_ocr_service = ocr_service or LazyDocumentOcrService(
        factory=lambda: PaddleOcrService(models_dir=app_config.models_dir)
    )
    resolved_ocr_layout_renderer = ocr_layout_renderer or PillowOcrLayoutRenderer()
    resolved_legacy_excel_converter = legacy_excel_converter or ExcelComLegacyConverter()
    excel_job_service = ExcelJobService(
        config=app_config,
        repository=repository,
        memory_repository=memory_repository,
        correction_repository=correction_repository,
        translation_service=resolved_translation_service,
        ocr_service=resolved_ocr_service,
        ocr_layout_renderer=resolved_ocr_layout_renderer,
        glossary=glossary,
        legacy_excel_converter=resolved_legacy_excel_converter,
    )
    app_state = AppState(
        config=app_config,
        connection=connection,
        repository=repository,
        memory_repository=memory_repository,
        correction_repository=correction_repository,
        user_repository=user_repository,
        translation_service=resolved_translation_service,
        ocr_service=resolved_ocr_service,
        ocr_layout_renderer=resolved_ocr_layout_renderer,
        excel_job_service=excel_job_service,
        glossary=glossary,
        knowledge_base_service=knowledge_base_service,
        auth_service=auth_service,
        account_service=account_service,
        activity_service=activity_service,
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
    register_frontend_delivery(
        app,
        frontend_dist_dir=app_config.frontend_dist_dir,
        brand_logo_path=app_config.root_dir / "logo" / "logo-trans.png",
    )
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


def _user_to_model(user: UserRecord) -> UserAccountModel:
    return UserAccountModel(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() + "Z",
        updated_at=user.updated_at.isoformat() + "Z",
        last_login_at=user.last_login_at.isoformat() + "Z" if user.last_login_at else None,
    )


def _activity_to_model(entry: ActivityRecord) -> ActivityEntryModel:
    return ActivityEntryModel(
        id=entry.id,
        user_id=entry.user_id,
        username=entry.username,
        user_role=entry.user_role,
        action_type=entry.action_type,
        target_type=entry.target_type,
        target_id=entry.target_id,
        description=entry.description,
        metadata=entry.metadata,
        created_at=entry.created_at.isoformat() + "Z",
    )


def register_routes(app: FastAPI) -> None:
    def media_type_from_suffix(suffix: str) -> str:
        if suffix == ".xls":
            return "application/vnd.ms-excel"
        if suffix == ".xlsx":
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if suffix == ".pptx":
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        if suffix == ".docx":
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
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
        if job.file_type == "xls":
            return "application/vnd.ms-excel"
        if job.output_file_path:
            return media_type_from_suffix(Path(job.output_file_path).suffix.lower())
        if job.file_type == "xlsx":
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if job.file_type == "pptx":
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        if job.file_type == "docx":
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if job.file_type == "pdf":
            return "application/pdf"
        if job.file_type == "image":
            return "image/png"
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {job.file_type}.")

    def source_media_type(job: JobRecord) -> str:
        return media_type_from_suffix(Path(job.original_file_path).suffix.lower())

    def _extract_bearer_token(authorization: str | None) -> str:
        if authorization is None:
            raise HTTPException(status_code=401, detail="Authentication is required.")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(status_code=401, detail="Invalid authorization header.")
        return token.strip()

    def _current_session(
        authorization: str | None = Header(default=None),
    ) -> AuthenticatedSession:
        session_token = _extract_bearer_token(authorization)
        try:
            return get_state(app).auth_service.current_session(session_token)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def _current_user(
        session: AuthenticatedSession = Depends(_current_session),
    ) -> UserRecord:
        return session.user

    def _current_admin_user(
        user: UserRecord = Depends(_current_user),
    ) -> UserRecord:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access is required.")
        return user

    def _ensure_job_access(user: UserRecord, job_id: str) -> JobRecord:
        job = get_state(app).excel_job_service.get_job(job_id)
        if user.role == "admin":
            return job
        if job.owner_user_id != user.id:
            raise HTTPException(status_code=403, detail="You do not have access to this job.")
        return job

    def _parse_activity_datetime(value: str | None) -> datetime | None:
        if value is None or not value.strip():
            return None
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid datetime filter: {value}") from exc
        return parsed.replace(tzinfo=None)

    @app.get("/api/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/auth/login", response_model=AuthSessionModel)
    def login(payload: AuthLoginRequest) -> AuthSessionModel:
        try:
            authenticated_session = get_state(app).auth_service.authenticate(
                username=payload.username,
                password=payload.password,
            )
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        get_state(app).activity_service.log(
            user=authenticated_session.user,
            action_type="login",
            target_type="session",
            target_id=authenticated_session.user.id,
            description="Signed in.",
            metadata={"username": authenticated_session.user.username},
        )
        return AuthSessionModel(
            session_token=authenticated_session.session_token,
            user=_user_to_model(authenticated_session.user),
        )

    @app.get("/api/auth/session", response_model=AuthSessionModel)
    def current_session(session: AuthenticatedSession = Depends(_current_session)) -> AuthSessionModel:
        return AuthSessionModel(
            session_token=session.session_token,
            user=_user_to_model(session.user),
        )

    @app.post("/api/auth/logout", status_code=204)
    def logout(session: AuthenticatedSession = Depends(_current_session)) -> Response:
        get_state(app).auth_service.logout(session.session_token)
        get_state(app).activity_service.log(
            user=session.user,
            action_type="logout",
            target_type="session",
            target_id=session.user.id,
            description="Signed out.",
            metadata={"username": session.user.username},
        )
        return Response(status_code=204)

    @app.get("/api/languages", response_model=list[LanguagePairModel])
    def list_languages() -> list[dict[str, object]]:
        service = get_state(app).translation_service
        return service.available_pairs()

    @app.get("/api/admin/accounts", response_model=list[UserAccountModel])
    def list_accounts(
        query: str | None = Query(default=None),
        role: str | None = Query(default=None),
        is_active: bool | None = Query(default=None),
        _: UserRecord = Depends(_current_admin_user),
    ) -> list[UserAccountModel]:
        accounts = get_state(app).account_service.list_accounts(
            query=query,
            role=role,
            is_active=is_active,
        )
        return [_user_to_model(account) for account in accounts]

    @app.post("/api/admin/accounts", response_model=UserAccountModel)
    def save_account(
        payload: UserAccountUpsertRequest,
        user: UserRecord = Depends(_current_admin_user),
    ) -> UserAccountModel:
        try:
            account = get_state(app).account_service.save_account(
                account_id=payload.id,
                username=payload.username,
                role=payload.role,
                is_active=payload.is_active,
                password=payload.password,
                actor_user=user,
            )
        except AuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        get_state(app).activity_service.log(
            user=user,
            action_type="account_save",
            target_type="account",
            target_id=account.id,
            description=f"Saved account {account.username}.",
            metadata={"role": account.role, "is_active": str(account.is_active).lower()},
        )
        return _user_to_model(account)

    @app.delete("/api/admin/accounts/{account_id}", status_code=204)
    def delete_account(account_id: str, user: UserRecord = Depends(_current_admin_user)) -> Response:
        try:
            get_state(app).account_service.delete_account(account_id=account_id, actor_user=user)
        except AuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        get_state(app).activity_service.log(
            user=user,
            action_type="account_delete",
            target_type="account",
            target_id=account_id,
            description=f"Deleted account {account_id}.",
            metadata={},
        )
        return Response(status_code=204)

    @app.get("/api/admin/activity", response_model=ActivityListResponse)
    def list_activity(
        user_id: str | None = Query(default=None),
        action_type: str | None = Query(default=None),
        target_type: str | None = Query(default=None),
        query: str | None = Query(default=None),
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
        _: UserRecord = Depends(_current_admin_user),
    ) -> ActivityListResponse:
        activity_service = get_state(app).activity_service
        entries = activity_service.list_entries(
            ActivityQuery(
                user_id=user_id,
                action_type=action_type,
                target_type=target_type,
                query=query,
                date_from=_parse_activity_datetime(date_from),
                date_to=_parse_activity_datetime(date_to),
            )
        )
        items = [_activity_to_model(entry) for entry in entries]
        return ActivityListResponse(
            items=items,
            total=len(items),
            action_types=activity_service.list_action_types(),
            target_types=activity_service.list_target_types(),
        )

    @app.get("/api/knowledge/summary", response_model=KnowledgeSummaryModel)
    def knowledge_summary(_: UserRecord = Depends(_current_admin_user)) -> KnowledgeSummaryModel:
        summary = get_state(app).knowledge_base_service.summary()
        return KnowledgeSummaryModel(
            glossary_count=summary.glossary_count,
            protected_term_count=summary.protected_term_count,
            memory_count=summary.memory_count,
        )

    @app.get("/api/knowledge/glossary", response_model=list[GlossaryEntryModel])
    def list_glossary_entries(_: UserRecord = Depends(_current_admin_user)) -> list[GlossaryEntryModel]:
        entries = get_state(app).knowledge_base_service.list_glossary_entries()
        return [_glossary_entry_to_model(entry) for entry in entries]

    @app.post("/api/knowledge/glossary", response_model=GlossaryEntryModel)
    def save_glossary_entry(
        payload: GlossaryEntryUpsertRequest,
        user: UserRecord = Depends(_current_admin_user),
    ) -> GlossaryEntryModel:
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
        get_state(app).activity_service.log(
            user=user,
            action_type="glossary_save",
            target_type="glossary_entry",
            target_id=entry.id,
            description=f"Saved glossary entry {entry.source_text}.",
            metadata={
                "source_language": entry.source_language,
                "target_language": entry.target_language,
            },
        )
        return _glossary_entry_to_model(entry)

    @app.delete("/api/knowledge/glossary/{entry_id}", status_code=204)
    def delete_glossary_entry(
        entry_id: str,
        user: UserRecord = Depends(_current_admin_user),
    ) -> Response:
        service = get_state(app).knowledge_base_service
        try:
            service.delete_glossary_entry(entry_id)
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        get_state(app).activity_service.log(
            user=user,
            action_type="glossary_delete",
            target_type="glossary_entry",
            target_id=entry_id,
            description=f"Deleted glossary entry {entry_id}.",
            metadata={},
        )
        return Response(status_code=204)

    @app.get("/api/knowledge/protected-terms", response_model=list[ProtectedTermModel])
    def list_protected_terms(_: UserRecord = Depends(_current_admin_user)) -> list[ProtectedTermModel]:
        terms = get_state(app).knowledge_base_service.list_protected_terms()
        return [_protected_term_to_model(term) for term in terms]

    @app.post("/api/knowledge/protected-terms", response_model=ProtectedTermModel)
    def save_protected_term(
        payload: ProtectedTermUpsertRequest,
        user: UserRecord = Depends(_current_admin_user),
    ) -> ProtectedTermModel:
        service = get_state(app).knowledge_base_service
        try:
            term = service.save_protected_term(term_id=payload.id, term=payload.term)
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        get_state(app).activity_service.log(
            user=user,
            action_type="protected_term_save",
            target_type="protected_term",
            target_id=term.id,
            description=f"Saved protected term {term.term}.",
            metadata={},
        )
        return _protected_term_to_model(term)

    @app.delete("/api/knowledge/protected-terms/{term_id}", status_code=204)
    def delete_protected_term(
        term_id: str,
        user: UserRecord = Depends(_current_admin_user),
    ) -> Response:
        service = get_state(app).knowledge_base_service
        try:
            service.delete_protected_term(term_id)
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        get_state(app).activity_service.log(
            user=user,
            action_type="protected_term_delete",
            target_type="protected_term",
            target_id=term_id,
            description=f"Deleted protected term {term_id}.",
            metadata={},
        )
        return Response(status_code=204)

    @app.get("/api/knowledge/memory", response_model=list[TranslationMemoryEntryModel])
    def list_translation_memory_entries(
        _: UserRecord = Depends(_current_admin_user),
    ) -> list[TranslationMemoryEntryModel]:
        entries = get_state(app).knowledge_base_service.list_memory_entries()
        return [_memory_entry_to_model(entry) for entry in entries]

    @app.post("/api/knowledge/memory", response_model=TranslationMemoryEntryModel)
    def save_translation_memory_entry(
        payload: TranslationMemoryEntryUpsertRequest,
        user: UserRecord = Depends(_current_admin_user),
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
        get_state(app).activity_service.log(
            user=user,
            action_type="memory_save",
            target_type="translation_memory",
            target_id=entry.id,
            description=f"Saved translation memory for {entry.source_text}.",
            metadata={
                "source_language": entry.source_language,
                "target_language": entry.target_language,
            },
        )
        return _memory_entry_to_model(entry)

    @app.delete("/api/knowledge/memory/{entry_id}", status_code=204)
    def delete_translation_memory_entry(
        entry_id: str,
        user: UserRecord = Depends(_current_admin_user),
    ) -> Response:
        service = get_state(app).knowledge_base_service
        try:
            service.delete_memory_entry(entry_id)
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        get_state(app).activity_service.log(
            user=user,
            action_type="memory_delete",
            target_type="translation_memory",
            target_id=entry_id,
            description=f"Deleted translation memory entry {entry_id}.",
            metadata={},
        )
        return Response(status_code=204)

    @app.post("/api/translate", response_model=TranslateResponse)
    def translate(
        payload: TranslateRequest,
        _: UserRecord = Depends(_current_user),
    ) -> TranslateResponse:
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
        user: UserRecord = Depends(_current_user),
    ) -> JobSummaryModel:
        file_bytes = await request.body()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        service = get_state(app).excel_job_service
        try:
            job = service.create_job(
                file_name=file_name,
                file_bytes=file_bytes,
                owner_user_id=user.id,
            )
        except ExcelJobError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        get_state(app).activity_service.log(
            user=user,
            action_type="job_upload",
            target_type="job",
            target_id=job.id,
            description=f"Uploaded {file_name}.",
            metadata={"file_type": job.file_type},
        )
        return _job_to_model(job)

    @app.get("/api/excel/jobs", response_model=list[JobSummaryModel])
    def list_excel_jobs(user: UserRecord = Depends(_current_user)) -> list[JobSummaryModel]:
        repository = get_state(app).repository
        jobs = repository.list_jobs() if user.role == "admin" else repository.list_jobs_for_owner(user.id)
        return [_job_to_model(job) for job in jobs]

    @app.get("/api/excel/jobs/{job_id}", response_model=JobSummaryModel)
    def get_excel_job(job_id: str, user: UserRecord = Depends(_current_user)) -> JobSummaryModel:
        job = _ensure_job_access(user, job_id)
        return _job_to_model(job)

    @app.delete("/api/excel/jobs/{job_id}", status_code=204)
    def delete_excel_job(job_id: str, user: UserRecord = Depends(_current_user)) -> Response:
        _ensure_job_access(user, job_id)
        service = get_state(app).excel_job_service
        try:
            service.delete_job(job_id)
        except ExcelJobError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        get_state(app).activity_service.log(
            user=user,
            action_type="job_delete",
            target_type="job",
            target_id=job_id,
            description=f"Deleted job {job_id}.",
            metadata={},
        )
        return Response(status_code=204)

    @app.get("/api/excel/jobs/{job_id}/segments", response_model=SegmentListResponse)
    def list_excel_segments(
        job_id: str,
        sheet_name: str | None = Query(default=None),
        status: str | None = Query(default=None),
        query: str | None = Query(default=None),
        user: UserRecord = Depends(_current_user),
    ) -> SegmentListResponse:
        _ensure_job_access(user, job_id)
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
    def start_excel_job(
        job_id: str,
        payload: ExcelTranslateJobRequest,
        user: UserRecord = Depends(_current_user),
    ) -> JobSummaryModel:
        _ensure_job_access(user, job_id)
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
        user: UserRecord = Depends(_current_user),
    ) -> SegmentModel:
        _ensure_job_access(user, job_id)
        service = get_state(app).excel_job_service
        try:
            segment = service.update_segment_final_text(
                job_id,
                segment_id,
                payload.final_text,
            )
        except ExcelJobError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        get_state(app).activity_service.log(
            user=user,
            action_type="segment_save",
            target_type="segment",
            target_id=segment.id,
            description=f"Saved segment {segment.cell_address} in {segment.sheet_name}.",
            metadata={"job_id": job_id},
        )
        return _segment_to_model(segment)

    @app.post(
        "/api/excel/jobs/{job_id}/segments/{segment_id}/share-memory",
        response_model=TranslationMemoryEntryModel,
    )
    def share_excel_segment_to_memory(
        job_id: str,
        segment_id: str,
        user: UserRecord = Depends(_current_user),
    ) -> TranslationMemoryEntryModel:
        _ensure_job_access(user, job_id)
        service = get_state(app).excel_job_service
        try:
            entry = service.share_segment_to_memory(job_id, segment_id)
        except ExcelJobError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        get_state(app).activity_service.log(
            user=user,
            action_type="segment_share_memory",
            target_type="translation_memory",
            target_id=entry.id,
            description=f"Shared segment {segment_id} to the system knowledge base.",
            metadata={
                "job_id": job_id,
                "source_language": entry.source_language,
                "target_language": entry.target_language,
            },
        )
        return _memory_entry_to_model(entry)

    @app.post("/api/excel/jobs/{job_id}/review-complete", response_model=JobSummaryModel)
    def complete_excel_job_review(
        job_id: str,
        user: UserRecord = Depends(_current_user),
    ) -> JobSummaryModel:
        _ensure_job_access(user, job_id)
        service = get_state(app).excel_job_service
        try:
            job = service.complete_review(job_id)
        except ExcelJobError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        get_state(app).activity_service.log(
            user=user,
            action_type="job_start",
            target_type="job",
            target_id=job.id,
            description=f"Started translation for {job.original_file_name}.",
            metadata={
                "source_language": payload.source_language,
                "target_language": payload.target_language,
            },
        )
        return _job_to_model(job)

    @app.post("/api/excel/jobs/{job_id}/preview", response_model=PreviewResponse)
    def preview_excel_job(
        job_id: str,
        user: UserRecord = Depends(_current_user),
    ) -> PreviewResponse:
        _ensure_job_access(user, job_id)
        service = get_state(app).excel_job_service
        try:
            preview = service.generate_preview(job_id)
        except ExcelJobError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return PreviewResponse(summary=preview.summary)

    @app.post("/api/excel/jobs/{job_id}/download", response_model=DownloadReadyResponse)
    def prepare_download(
        job_id: str,
        user: UserRecord = Depends(_current_user),
    ) -> DownloadReadyResponse:
        _ensure_job_access(user, job_id)
        service = get_state(app).excel_job_service
        try:
            exported = service.download_job(job_id)
        except ExcelJobError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        get_state(app).activity_service.log(
            user=user,
            action_type="job_export",
            target_type="job",
            target_id=job_id,
            description=f"Prepared export {exported.file_name}.",
            metadata={"file_name": exported.file_name},
        )
        return DownloadReadyResponse(file_name=exported.file_name)

    @app.get("/api/excel/jobs/{job_id}/download")
    def download_excel_job(job_id: str, user: UserRecord = Depends(_current_user)) -> Response:
        job = _ensure_job_access(user, job_id)
        if job.output_file_path is None:
            raise HTTPException(status_code=404, detail="Exported document was not found.")
        return FileResponse(
            path=job.output_file_path,
            media_type=download_media_type(job),
            filename=Path(job.output_file_path).name,
        )

    @app.get("/api/excel/jobs/{job_id}/source-document")
    def source_excel_job_document(job_id: str, user: UserRecord = Depends(_current_user)) -> Response:
        job = _ensure_job_access(user, job_id)
        return FileResponse(
            path=job.original_file_path,
            media_type=source_media_type(job),
            filename=Path(job.original_file_path).name,
        )


@lru_cache
def get_app() -> FastAPI:
    return create_app()


app = get_app()
