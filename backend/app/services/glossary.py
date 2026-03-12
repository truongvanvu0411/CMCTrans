from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..glossary_repository import (
    GlossaryExactRecord,
    GlossaryRepository,
    ProtectedTermRecord,
)


@dataclass(frozen=True)
class GlossaryEntry:
    source_language: str
    target_language: str
    source_text: str
    translated_text: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class GlossaryService:
    def __init__(
        self,
        glossary_path: Path,
        repository: GlossaryRepository | None = None,
    ) -> None:
        self._glossary_path = glossary_path
        self._repository = repository
        if self._repository is None:
            self._load_from_file_only()
        else:
            self._seed_defaults_if_needed()
            self._reload_cache()

    def find_exact(
        self,
        *,
        source_language: str,
        target_language: str,
        source_text: str,
    ) -> GlossaryEntry | None:
        return self._exact_terms.get(
            (
                source_language,
                target_language,
                source_text.strip().casefold(),
            )
        )

    def is_protected(self, token: str) -> bool:
        return token.strip() in self._protected_terms

    def protected_terms(self) -> set[str]:
        return set(self._protected_terms)

    def list_exact_entries(self) -> list[GlossaryExactRecord]:
        if self._repository is None:
            raise ValueError("Glossary management is unavailable without a backing repository.")
        return self._repository.list_exact_entries()

    def save_exact_entry(
        self,
        *,
        entry_id: str | None,
        source_language: str,
        target_language: str,
        source_text: str,
        translated_text: str,
    ) -> GlossaryExactRecord:
        normalized_source_text = source_text.strip()
        normalized_translated_text = translated_text.strip()
        if not normalized_source_text or not normalized_translated_text:
            raise ValueError("Glossary source text and translated text must not be empty.")
        if self._repository is None:
            raise ValueError("Glossary management is unavailable without a backing repository.")

        now = _utc_now()
        if entry_id is None:
            resolved_id = str(uuid.uuid4())
            try:
                self._repository.upsert_exact_entry(
                    entry_id=resolved_id,
                    source_language=source_language,
                    target_language=target_language,
                    source_text=normalized_source_text,
                    translated_text=normalized_translated_text,
                    created_at=now,
                    updated_at=now,
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("A glossary entry with the same language pair and source text already exists.") from exc
        else:
            existing_entry = self._repository.get_exact_entry(entry_id)
            if existing_entry is None:
                raise ValueError(f"Glossary entry {entry_id} was not found.")
            try:
                self._repository.replace_exact_entry(
                    entry_id=entry_id,
                    source_language=source_language,
                    target_language=target_language,
                    source_text=normalized_source_text,
                    translated_text=normalized_translated_text,
                    updated_at=now,
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("A glossary entry with the same language pair and source text already exists.") from exc
        self._reload_cache()
        updated_entry = self._find_exact_record(
            source_language=source_language,
            target_language=target_language,
            source_text=normalized_source_text,
        )
        if updated_entry is None:
            raise ValueError("Saved glossary entry could not be reloaded.")
        return updated_entry

    def delete_exact_entry(self, entry_id: str) -> None:
        if self._repository is None:
            raise ValueError("Glossary management is unavailable without a backing repository.")
        if self._repository.get_exact_entry(entry_id) is None:
            raise ValueError(f"Glossary entry {entry_id} was not found.")
        self._repository.delete_exact_entry(entry_id)
        self._reload_cache()

    def list_protected_terms(self) -> list[ProtectedTermRecord]:
        if self._repository is None:
            raise ValueError("Protected term management is unavailable without a backing repository.")
        return self._repository.list_protected_terms()

    def save_protected_term(self, *, term_id: str | None, term: str) -> ProtectedTermRecord:
        normalized_term = term.strip()
        if not normalized_term:
            raise ValueError("Protected term must not be empty.")
        if self._repository is None:
            raise ValueError("Protected term management is unavailable without a backing repository.")
        now = _utc_now()
        if term_id is None:
            resolved_id = str(uuid.uuid4())
            try:
                self._repository.upsert_protected_term(
                    term_id=resolved_id,
                    term=normalized_term,
                    created_at=now,
                    updated_at=now,
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("This protected term already exists.") from exc
        else:
            if self._repository.get_protected_term(term_id) is None:
                raise ValueError(f"Protected term {term_id} was not found.")
            try:
                self._repository.replace_protected_term(
                    term_id=term_id,
                    term=normalized_term,
                    updated_at=now,
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("This protected term already exists.") from exc
        self._reload_cache()
        updated_term = self._find_protected_record(normalized_term)
        if updated_term is None:
            raise ValueError("Saved protected term could not be reloaded.")
        return updated_term

    def delete_protected_term(self, term_id: str) -> None:
        if self._repository is None:
            raise ValueError("Protected term management is unavailable without a backing repository.")
        if self._repository.get_protected_term(term_id) is None:
            raise ValueError(f"Protected term {term_id} was not found.")
        self._repository.delete_protected_term(term_id)
        self._reload_cache()

    def _load_from_file_only(self) -> None:
        payload = json.loads(self._glossary_path.read_text(encoding="utf-8"))
        self._protected_terms = {
            str(term).strip()
            for term in payload.get("protected_terms", [])
            if str(term).strip()
        }
        self._exact_terms = {}
        for raw_entry in payload.get("exact_terms", []):
            entry = GlossaryEntry(
                source_language=str(raw_entry["source_language"]).strip(),
                target_language=str(raw_entry["target_language"]).strip(),
                source_text=str(raw_entry["source_text"]).strip(),
                translated_text=str(raw_entry["translated_text"]).strip(),
            )
            self._exact_terms[
                (
                    entry.source_language,
                    entry.target_language,
                    entry.source_text.casefold(),
                )
            ] = entry

    def _reload_cache(self) -> None:
        self._protected_term_records = self._repository.list_protected_terms()
        self._exact_term_records = self._repository.list_exact_entries()
        self._protected_terms = {
            record.term.strip()
            for record in self._protected_term_records
            if record.term.strip()
        }
        self._exact_terms: dict[tuple[str, str, str], GlossaryEntry] = {}
        for record in self._exact_term_records:
            entry = GlossaryEntry(
                source_language=record.source_language,
                target_language=record.target_language,
                source_text=record.source_text.strip(),
                translated_text=record.translated_text.strip(),
            )
            self._exact_terms[
                (
                    entry.source_language,
                    entry.target_language,
                    entry.source_text.casefold(),
                )
            ] = entry

    def _seed_defaults_if_needed(self) -> None:
        payload = json.loads(self._glossary_path.read_text(encoding="utf-8"))
        now = _utc_now()
        if self._repository.count_protected_terms() == 0:
            for raw_term in payload.get("protected_terms", []):
                normalized_term = str(raw_term).strip()
                if not normalized_term:
                    continue
                self._repository.upsert_protected_term(
                    term_id=str(uuid.uuid4()),
                    term=normalized_term,
                    created_at=now,
                    updated_at=now,
                )
        if self._repository.count_exact_entries() == 0:
            for raw_entry in payload.get("exact_terms", []):
                source_language = str(raw_entry["source_language"]).strip()
                target_language = str(raw_entry["target_language"]).strip()
                source_text = str(raw_entry["source_text"]).strip()
                translated_text = str(raw_entry["translated_text"]).strip()
                if not source_text or not translated_text:
                    continue
                self._repository.upsert_exact_entry(
                    entry_id=str(uuid.uuid4()),
                    source_language=source_language,
                    target_language=target_language,
                    source_text=source_text,
                    translated_text=translated_text,
                    created_at=now,
                    updated_at=now,
                )

    def _find_exact_record(
        self,
        *,
        source_language: str,
        target_language: str,
        source_text: str,
    ) -> GlossaryExactRecord | None:
        for record in self._repository.list_exact_entries():
            if (
                record.source_language == source_language
                and record.target_language == target_language
                and record.source_text == source_text
            ):
                return record
        return None

    def _find_protected_record(self, term: str) -> ProtectedTermRecord | None:
        for record in self._repository.list_protected_terms():
            if record.term == term:
                return record
        return None
