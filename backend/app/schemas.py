from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LanguageOptionModel(BaseModel):
    code: str
    label: str


class LanguagePairModel(BaseModel):
    source: LanguageOptionModel
    targets: list[LanguageOptionModel]


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    source_language: str = Field(..., min_length=2, max_length=8)
    target_language: str = Field(..., min_length=2, max_length=8)


class TranslateResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    source_language: str
    target_language: str
    translation: str
    intermediate_translation: str | None = None
    model_chain: list[str]


class JobSummaryModel(BaseModel):
    id: str
    original_file_name: str
    file_type: str
    status: str
    current_step: str
    progress_percent: int
    processed_segments: int
    total_segments: int
    status_message: str
    current_sheet: str | None
    current_cell: str | None
    preview_ready: bool
    preview_summary: dict[str, object]
    source_language: str | None
    target_language: str | None
    parse_summary: dict[str, object]
    translation_summary: dict[str, object]
    output_file_name: str | None
    updated_at: str


class SegmentModel(BaseModel):
    id: str
    order_index: int
    sheet_name: str
    sheet_index: int
    cell_address: str
    location_type: str
    original_text: str
    normalized_text: str
    machine_translation: str | None
    edited_translation: str | None
    final_text: str | None
    intermediate_translation: str | None
    status: str
    warning_codes: list[str]
    error_message: str | None


class SegmentListResponse(BaseModel):
    items: list[SegmentModel]
    total: int


class ExcelTranslateJobRequest(BaseModel):
    source_language: str = Field(..., min_length=2, max_length=8)
    target_language: str = Field(..., min_length=2, max_length=8)


class PreviewResponse(BaseModel):
    summary: dict[str, object]


class SegmentUpdateRequest(BaseModel):
    final_text: str


class DownloadReadyResponse(BaseModel):
    file_name: str


class GlossaryEntryModel(BaseModel):
    id: str
    source_language: str
    target_language: str
    source_text: str
    translated_text: str
    updated_at: str


class ProtectedTermModel(BaseModel):
    id: str
    term: str
    updated_at: str


class TranslationMemoryEntryModel(BaseModel):
    id: str
    source_language: str
    target_language: str
    source_text: str
    translated_text: str
    updated_at: str


class GlossaryEntryUpsertRequest(BaseModel):
    id: str | None = None
    source_language: str = Field(..., min_length=2, max_length=8)
    target_language: str = Field(..., min_length=2, max_length=8)
    source_text: str = Field(..., min_length=1, max_length=500)
    translated_text: str = Field(..., min_length=1, max_length=1000)


class ProtectedTermUpsertRequest(BaseModel):
    id: str | None = None
    term: str = Field(..., min_length=1, max_length=200)


class TranslationMemoryEntryUpsertRequest(BaseModel):
    id: str | None = None
    source_language: str = Field(..., min_length=2, max_length=8)
    target_language: str = Field(..., min_length=2, max_length=8)
    source_text: str = Field(..., min_length=1, max_length=1000)
    translated_text: str = Field(..., min_length=1, max_length=2000)


class KnowledgeSummaryModel(BaseModel):
    glossary_count: int
    protected_term_count: int
    memory_count: int


class AuthLoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=1, max_length=200)


class UserAccountModel(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool
    created_at: str
    updated_at: str
    last_login_at: str | None


class AuthSessionModel(BaseModel):
    session_token: str
    user: UserAccountModel


class UserAccountUpsertRequest(BaseModel):
    id: str | None = None
    username: str = Field(..., min_length=3, max_length=50)
    role: str = Field(..., min_length=4, max_length=10)
    is_active: bool = True
    password: str | None = Field(default=None, min_length=8, max_length=200)


class ActivityEntryModel(BaseModel):
    id: str
    user_id: str
    username: str
    user_role: str
    action_type: str
    target_type: str
    target_id: str | None
    description: str
    metadata: dict[str, str]
    created_at: str


class ActivityListResponse(BaseModel):
    items: list[ActivityEntryModel]
    total: int
    action_types: list[str]
    target_types: list[str]
