from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from ..domain import TranslateResult
from .glossary import GlossaryService


SYMBOL_ONLY_RE = re.compile(r"^[\W_]+$", re.UNICODE)
ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_./:+-]*")
MULTISPACE_RE = re.compile(r"\s+")
EDGE_PUNCTUATION_RE = re.compile(r"^[\s,.;:!?()（）［］【】]+|[\s,.;:!?()（）［］【】]+$")

SHORT_TEXT_RULES: dict[tuple[str, str, str], str] = {
    ("ja", "en", "〇"): "〇",
    ("ja", "vi", "〇"): "〇",
    ("ja", "en", "○"): "○",
    ("ja", "vi", "○"): "○",
    ("ja", "en", "o"): "O",
    ("ja", "vi", "o"): "O",
    ("ja", "en", "O"): "O",
    ("ja", "vi", "O"): "O",
    ("ja", "en", "×"): "×",
    ("ja", "vi", "×"): "×",
    ("ja", "en", "No"): "No",
    ("ja", "vi", "No"): "Không",
    ("ja", "en", "Yes"): "Yes",
    ("ja", "vi", "Yes"): "Có",
    ("ja", "en", "任意"): "Optional",
    ("ja", "vi", "任意"): "Tùy chọn",
}


@dataclass(frozen=True)
class TextClassification:
    category: str
    normalized_text: str
    protected_tokens: list[str]
    token_count: int


@dataclass(frozen=True)
class CleanCorrection:
    source_text: str
    machine_translation: str | None
    corrected_translation: str


def normalize_text_for_lookup(text: str) -> str:
    normalized = MULTISPACE_RE.sub(" ", text.strip())
    return normalized


def classify_text(text: str, glossary: GlossaryService) -> TextClassification:
    normalized = normalize_text_for_lookup(text)
    protected_tokens = [token for token in ASCII_TOKEN_RE.findall(normalized) if glossary.is_protected(token)]
    if not normalized:
        return TextClassification(
            category="empty",
            normalized_text=normalized,
            protected_tokens=protected_tokens,
            token_count=0,
        )
    if len(normalized) == 1 or SYMBOL_ONLY_RE.match(normalized):
        return TextClassification(
            category="symbol",
            normalized_text=normalized,
            protected_tokens=protected_tokens,
            token_count=1,
        )
    tokens = normalized.split()
    token_count = len(tokens)
    if glossary.is_protected(normalized):
        category = "protected"
    elif token_count <= 2 or len(normalized) <= 12:
        category = "short_text"
    elif protected_tokens:
        category = "mixed_technical"
    elif len(normalized) <= 40:
        category = "label"
    else:
        category = "sentence"
    return TextClassification(
        category=category,
        normalized_text=normalized,
        protected_tokens=protected_tokens,
        token_count=token_count,
    )


def try_rule_based_translation(
    *,
    text: str,
    source_language: str,
    target_language: str,
    classification: TextClassification,
    glossary: GlossaryService,
) -> TranslateResult | None:
    glossary_entry = glossary.find_exact(
        source_language=source_language,
        target_language=target_language,
        source_text=classification.normalized_text,
    )
    if glossary_entry is not None:
        return TranslateResult(
            translation=glossary_entry.translated_text,
            intermediate_translation=None,
            model_chain=[f"glossary:{source_language}->{target_language}"],
        )

    short_text_rule = SHORT_TEXT_RULES.get(
        (
            source_language,
            target_language,
            classification.normalized_text,
        )
    )
    if short_text_rule is not None:
        return TranslateResult(
            translation=short_text_rule,
            intermediate_translation=None,
            model_chain=[f"rule:{source_language}->{target_language}"],
        )

    if classification.category in {"symbol", "protected"}:
        return TranslateResult(
            translation=classification.normalized_text,
            intermediate_translation=None,
            model_chain=[f"passthrough:{source_language}->{target_language}"],
        )

    return None


def remove_duplicate_phrases(text: str) -> str:
    normalized = normalize_text_for_lookup(text)
    if not normalized:
        return normalized

    comma_parts = [part.strip() for part in normalized.split(",")]
    if len(comma_parts) == 2:
        left = _normalize_duplicate_fragment(comma_parts[0])
        right = _normalize_duplicate_fragment(comma_parts[1])
        if left and left.casefold() == right.casefold():
            return left

    words = normalized.split()
    deduped_words: list[str] = []
    for word in words:
        previous_word = deduped_words[-1] if deduped_words else None
        if (
            previous_word is not None
            and _normalize_duplicate_fragment(previous_word).casefold()
            == _normalize_duplicate_fragment(word).casefold()
        ):
            continue
        deduped_words.append(word)
    deduped_text = " ".join(deduped_words)

    doubled_match = re.fullmatch(r"(.+?)\s+\1", deduped_text, flags=re.IGNORECASE)
    if doubled_match is not None:
        return doubled_match.group(1)

    return deduped_text


def _normalize_duplicate_fragment(text: str) -> str:
    return EDGE_PUNCTUATION_RE.sub("", text).strip()


def preserve_protected_tokens(
    *,
    source_text: str,
    translated_text: str,
    glossary: GlossaryService,
) -> str:
    result = translated_text
    for token in ASCII_TOKEN_RE.findall(source_text):
        if glossary.is_protected(token) and token not in result:
            if result.endswith(":"):
                result = f"{result} {token}"
            else:
                result = f"{result} {token}".strip()
    return result.strip()


def postprocess_translation(
    *,
    source_text: str,
    translated_text: str,
    glossary: GlossaryService,
) -> str:
    deduped = remove_duplicate_phrases(translated_text)
    protected = preserve_protected_tokens(
        source_text=source_text,
        translated_text=deduped,
        glossary=glossary,
    )
    return normalize_text_for_lookup(protected)


def fuzzy_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_text_for_lookup(left), normalize_text_for_lookup(right)).ratio()


def build_clean_correction(
    *,
    source_text: str,
    machine_translation: str | None,
    corrected_translation: str,
    glossary: GlossaryService,
) -> CleanCorrection | None:
    normalized_source = normalize_text_for_lookup(source_text)
    normalized_corrected = normalize_text_for_lookup(corrected_translation)
    normalized_machine = (
        normalize_text_for_lookup(machine_translation)
        if machine_translation is not None
        else None
    )
    if not normalized_source or not normalized_corrected:
        return None
    if normalized_machine == normalized_corrected:
        return None

    source_classification = classify_text(normalized_source, glossary)
    corrected_classification = classify_text(normalized_corrected, glossary)
    if source_classification.category in {"empty", "symbol", "protected"}:
        return None
    if corrected_classification.category in {"empty", "symbol"}:
        return None

    return CleanCorrection(
        source_text=normalized_source,
        machine_translation=normalized_machine,
        corrected_translation=normalized_corrected,
    )
