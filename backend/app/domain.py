from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TranslateResult:
    translation: str
    intermediate_translation: str | None
    model_chain: list[str]


@dataclass(frozen=True)
class SegmentRecord:
    id: str
    job_id: str
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
    locator: dict[str, str]
    error_message: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class JobRecord:
    id: str
    original_file_name: str
    original_file_path: str
    output_file_path: str | None
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
    created_at: datetime
    updated_at: datetime
