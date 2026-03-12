from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from ..memory_repository import TranslationMemoryRecord, TranslationMemoryRepository
from .glossary import GlossaryService


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class KnowledgeBaseError(Exception):
    """Raised when glossary or translation memory management fails."""


@dataclass(frozen=True)
class SavedKnowledgeState:
    glossary_count: int
    protected_term_count: int
    memory_count: int


class KnowledgeBaseService:
    def __init__(
        self,
        *,
        glossary: GlossaryService,
        memory_repository: TranslationMemoryRepository,
    ) -> None:
        self._glossary = glossary
        self._memory_repository = memory_repository

    def list_glossary_entries(self):
        return self._glossary.list_exact_entries()

    def save_glossary_entry(
        self,
        *,
        entry_id: str | None,
        source_language: str,
        target_language: str,
        source_text: str,
        translated_text: str,
    ):
        try:
            return self._glossary.save_exact_entry(
                entry_id=entry_id,
                source_language=source_language,
                target_language=target_language,
                source_text=source_text,
                translated_text=translated_text,
            )
        except ValueError as exc:
            raise KnowledgeBaseError(str(exc)) from exc

    def delete_glossary_entry(self, entry_id: str) -> None:
        try:
            self._glossary.delete_exact_entry(entry_id)
        except ValueError as exc:
            raise KnowledgeBaseError(str(exc)) from exc

    def list_protected_terms(self):
        return self._glossary.list_protected_terms()

    def save_protected_term(self, *, term_id: str | None, term: str):
        try:
            return self._glossary.save_protected_term(term_id=term_id, term=term)
        except ValueError as exc:
            raise KnowledgeBaseError(str(exc)) from exc

    def delete_protected_term(self, term_id: str) -> None:
        try:
            self._glossary.delete_protected_term(term_id)
        except ValueError as exc:
            raise KnowledgeBaseError(str(exc)) from exc

    def list_memory_entries(self) -> list[TranslationMemoryRecord]:
        return self._memory_repository.list_entries()

    def save_memory_entry(
        self,
        *,
        entry_id: str | None,
        source_language: str,
        target_language: str,
        source_text: str,
        translated_text: str,
    ) -> TranslationMemoryRecord:
        normalized_source_text = source_text.strip()
        normalized_translated_text = translated_text.strip()
        if not normalized_source_text or not normalized_translated_text:
            raise KnowledgeBaseError("Translation memory source text and translated text must not be empty.")

        now = _utc_now()
        if entry_id is None:
            try:
                self._memory_repository.upsert(
                    entry_id=str(uuid.uuid4()),
                    source_language=source_language,
                    target_language=target_language,
                    source_text=normalized_source_text,
                    translated_text=normalized_translated_text,
                    created_at=now,
                    updated_at=now,
                )
            except sqlite3.IntegrityError as exc:
                raise KnowledgeBaseError(
                    "A translation memory entry with the same language pair and source text already exists."
                ) from exc
            created_entry = self._find_memory_entry(
                source_language=source_language,
                target_language=target_language,
                source_text=normalized_source_text,
            )
            if created_entry is None:
                raise KnowledgeBaseError("Saved translation memory entry could not be reloaded.")
            return created_entry

        existing_entry = self._memory_repository.get_entry(entry_id)
        if existing_entry is None:
            raise KnowledgeBaseError(f"Translation memory entry {entry_id} was not found.")
        try:
            self._memory_repository.replace_entry(
                entry_id=entry_id,
                source_language=source_language,
                target_language=target_language,
                source_text=normalized_source_text,
                translated_text=normalized_translated_text,
                updated_at=now,
            )
        except sqlite3.IntegrityError as exc:
            raise KnowledgeBaseError(
                "A translation memory entry with the same language pair and source text already exists."
            ) from exc
        updated_entry = self._memory_repository.get_entry(entry_id)
        if updated_entry is None:
            raise KnowledgeBaseError("Updated translation memory entry could not be reloaded.")
        return updated_entry

    def delete_memory_entry(self, entry_id: str) -> None:
        if self._memory_repository.get_entry(entry_id) is None:
            raise KnowledgeBaseError(f"Translation memory entry {entry_id} was not found.")
        self._memory_repository.delete_entry(entry_id)

    def summary(self) -> SavedKnowledgeState:
        return SavedKnowledgeState(
            glossary_count=len(self._glossary.list_exact_entries()),
            protected_term_count=len(self._glossary.list_protected_terms()),
            memory_count=len(self._memory_repository.list_entries()),
        )

    def _find_memory_entry(
        self,
        *,
        source_language: str,
        target_language: str,
        source_text: str,
    ) -> TranslationMemoryRecord | None:
        exact_entry = self._memory_repository.find_exact(
            source_language=source_language,
            target_language=target_language,
            source_text=source_text,
        )
        return exact_entry
