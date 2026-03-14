from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.app.services.excel_ooxml import parse_workbook
from backend.app.services.pptx_ooxml import parse_presentation
from backend.app.services.text_quality import classify_text, normalize_text_for_lookup, postprocess_translation


SUPPORTED_EXTENSIONS = {".xlsx", ".pptx"}
DEFAULT_TARGET_LANGUAGE = "vi"
POLL_INTERVAL_SECONDS = 2.0
POLL_TIMEOUT_SECONDS = 60.0 * 60.0


class ApiError(RuntimeError):
    """Raised when the local translator API returns an error."""


class LocalGlossary:
    def __init__(self, protected_terms: set[str]) -> None:
        self._protected_terms = {term.strip() for term in protected_terms if term.strip()}

    def is_protected(self, token: str) -> bool:
        return token.strip() in self._protected_terms


@dataclass(frozen=True)
class FilePlan:
    path: Path
    file_type: str
    segment_count: int | None
    detected_source_language: str | None
    skipped_reason: str | None


def _api_request(
    *,
    base_url: str,
    method: str,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    request = urllib.request.Request(
        urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/")),
        method=method,
        data=body,
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response_body = response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise ApiError(f"{method} {path} failed: {exc.code} {payload}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"{method} {path} failed: {exc.reason}") from exc

    if "application/json" in content_type:
        return json.loads(response_body.decode("utf-8"))
    return response_body


def _fetch_protected_terms(base_url: str) -> set[str]:
    payload = _api_request(
        base_url=base_url,
        method="GET",
        path="/api/knowledge/protected-terms",
    )
    return {str(item["term"]) for item in payload}


def _detect_source_language(texts: list[str]) -> str:
    sample = " ".join(texts[:200])
    counts = {"ja": 0, "vi": 0, "en": 0}
    vietnamese_chars = set(
        "ăâđêôơưĂÂĐÊÔƠƯáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệ"
        "óòỏõọốồổỗộớờởỡợúùủũụứừửữựíìỉĩịýỳỷỹỵ"
    )
    for char in sample:
        code_point = ord(char)
        if 0x3040 <= code_point <= 0x30FF or 0x4E00 <= code_point <= 0x9FFF:
            counts["ja"] += 1
        elif char in vietnamese_chars:
            counts["vi"] += 1
        elif ("A" <= char <= "Z") or ("a" <= char <= "z"):
            counts["en"] += 1
    return max(counts, key=counts.get)


def _plan_file(path: Path) -> FilePlan:
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return FilePlan(
            path=path,
            file_type=path.suffix.lower().lstrip("."),
            segment_count=None,
            detected_source_language=None,
            skipped_reason=f"Unsupported extension {path.suffix}.",
        )

    try:
        data = path.read_bytes()
        if path.suffix.lower() == ".xlsx":
            parsed = parse_workbook(data)
        else:
            parsed = parse_presentation(data)
    except Exception as exc:
        return FilePlan(
            path=path,
            file_type=path.suffix.lower().lstrip("."),
            segment_count=None,
            detected_source_language=None,
            skipped_reason=str(exc),
        )

    texts = [segment.original_text for segment in parsed.segments]
    return FilePlan(
        path=path,
        file_type=path.suffix.lower().lstrip("."),
        segment_count=int(parsed.parse_summary["total_extracted_segments"]),
        detected_source_language=_detect_source_language(texts),
        skipped_reason=None,
    )


def _target_language_for(source_language: str, preferred_target: str) -> str:
    if source_language != preferred_target:
        return preferred_target
    for fallback in ("ja", "en", "vi"):
        if fallback != source_language:
            return fallback
    raise RuntimeError(f"Could not choose a target language for source={source_language}.")


def _upload_job(base_url: str, plan: FilePlan) -> str:
    if plan.file_type == "xlsx":
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif plan.file_type == "pptx":
        content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    else:
        raise RuntimeError(f"Unsupported file type {plan.file_type}.")

    payload = _api_request(
        base_url=base_url,
        method="POST",
        path=f"/api/excel/jobs/upload?file_name={urllib.parse.quote(plan.path.name)}",
        body=plan.path.read_bytes(),
        headers={"Content-Type": content_type},
    )
    return str(payload["id"])


def _start_job(base_url: str, job_id: str, source_language: str, target_language: str) -> None:
    _api_request(
        base_url=base_url,
        method="POST",
        path=f"/api/excel/jobs/{job_id}/start",
        body=json.dumps(
            {
                "source_language": source_language,
                "target_language": target_language,
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


def _wait_for_review(base_url: str, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        payload = _api_request(
            base_url=base_url,
            method="GET",
            path=f"/api/excel/jobs/{job_id}",
        )
        status = str(payload["status"])
        if status == "review":
            return payload
        if status == "failed":
            raise ApiError(f"Job {job_id} failed: {payload.get('status_message', 'unknown error')}")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise ApiError(f"Job {job_id} did not reach review state within timeout.")


def _fetch_segments(base_url: str, job_id: str) -> list[dict[str, Any]]:
    payload = _api_request(
        base_url=base_url,
        method="GET",
        path=f"/api/excel/jobs/{job_id}/segments",
    )
    return list(payload["items"])


def _prepare_download(base_url: str, job_id: str) -> str:
    payload = _api_request(
        base_url=base_url,
        method="POST",
        path=f"/api/excel/jobs/{job_id}/download",
    )
    return str(payload["file_name"])


def _build_preview(base_url: str, job_id: str) -> None:
    _api_request(
        base_url=base_url,
        method="POST",
        path=f"/api/excel/jobs/{job_id}/preview",
    )


def _download_output(base_url: str, job_id: str, destination: Path) -> None:
    data = _api_request(
        base_url=base_url,
        method="GET",
        path=f"/api/excel/jobs/{job_id}/download",
    )
    if not isinstance(data, bytes):
        raise ApiError(f"Expected binary download for job {job_id}.")
    destination.write_bytes(data)


def _update_segment(base_url: str, job_id: str, segment_id: str, final_text: str) -> None:
    _api_request(
        base_url=base_url,
        method="PATCH",
        path=f"/api/excel/jobs/{job_id}/segments/{segment_id}",
        body=json.dumps({"final_text": final_text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


def _save_memory_entry(
    *,
    base_url: str,
    source_language: str,
    target_language: str,
    source_text: str,
    translated_text: str,
) -> None:
    _api_request(
        base_url=base_url,
        method="POST",
        path="/api/knowledge/memory",
        body=json.dumps(
            {
                "source_language": source_language,
                "target_language": target_language,
                "source_text": source_text,
                "translated_text": translated_text,
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


def _char_ratio(text: str, predicate: re.Pattern[str]) -> float:
    if not text:
        return 0.0
    matches = predicate.findall(text)
    return len(matches) / max(len(text), 1)


JAPANESE_CHAR_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
LATIN_CHAR_RE = re.compile(r"[A-Za-z]")
NUMERIC_ONLY_RE = re.compile(r"^[+-]?(?:\d+(?:[.,]\d+)?%?)$")


def _review_translation(
    *,
    glossary: LocalGlossary,
    source_language: str,
    target_language: str,
    source_text: str,
    translated_text: str,
) -> tuple[str, list[str]]:
    normalized_source = normalize_text_for_lookup(source_text)
    cleaned = postprocess_translation(
        source_text=normalized_source,
        translated_text=translated_text,
        glossary=glossary,
    )
    source_classification = classify_text(normalized_source, glossary)
    translated_classification = classify_text(cleaned, glossary)

    reasons: list[str] = []
    if source_classification.category in {"empty", "symbol", "protected"}:
        return cleaned, reasons
    if not cleaned:
        reasons.append("empty_translation")
        return cleaned, reasons
    if cleaned == normalized_source and not NUMERIC_ONLY_RE.fullmatch(cleaned):
        reasons.append("unchanged_from_source")
    if target_language == "vi" and _char_ratio(cleaned, JAPANESE_CHAR_RE) > 0.2:
        reasons.append("contains_too_much_japanese")
    if source_language == "en" and target_language == "vi":
        if translated_classification.category in {"label", "sentence"} and _char_ratio(cleaned, LATIN_CHAR_RE) > 0.85:
            reasons.append("looks_untranslated_english")
    if len(cleaned) <= 1 and len(normalized_source) > 4:
        reasons.append("too_short")
    return cleaned, reasons


def _should_save_to_memory(
    *,
    glossary: LocalGlossary,
    source_text: str,
    translated_text: str,
) -> bool:
    source_classification = classify_text(source_text, glossary)
    translated_classification = classify_text(translated_text, glossary)
    if source_classification.category in {"empty", "symbol", "protected"}:
        return False
    if translated_classification.category in {"empty", "symbol"}:
        return False
    return True


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        return {"files": {}, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _save_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Batch-train translation memory from local training documents.")
    parser.add_argument(
        "--api-base",
        default="http://host.docker.internal:8000",
        help="Base URL for the running translator API.",
    )
    parser.add_argument(
        "--input-dir",
        default="training doc",
        help="Folder containing source documents.",
    )
    parser.add_argument(
        "--run-dir",
        default="workspace/training_kb_batch",
        help="Directory used for manifests, reports, and downloaded outputs.",
    )
    parser.add_argument(
        "--preferred-target-language",
        default=DEFAULT_TARGET_LANGUAGE,
        choices=["ja", "en", "vi"],
        help="Preferred target language for source documents.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Optional limit for a single run.",
    )
    args = parser.parse_args(argv)

    input_dir = Path(args.input_dir)
    run_dir = Path(args.run_dir)
    output_dir = run_dir / "outputs"
    report_dir = run_dir / "reports"
    manifest_path = run_dir / "manifest.json"
    run_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    glossary = LocalGlossary(_fetch_protected_terms(args.api_base))
    manifest = _load_manifest(manifest_path)

    plans = [_plan_file(path) for path in sorted(input_dir.iterdir()) if path.is_file()]
    valid_plans = [plan for plan in plans if plan.skipped_reason is None]
    valid_plans.sort(key=lambda item: ((item.segment_count or 10**9), item.path.name.lower()))
    if args.max_files is not None:
        valid_plans = valid_plans[: args.max_files]

    for plan in plans:
        if plan.skipped_reason is None:
            continue
        manifest["files"].setdefault(
            plan.path.name,
            {
                "status": "skipped",
                "reason": plan.skipped_reason,
            },
        )
    _save_manifest(manifest_path, manifest)

    for index, plan in enumerate(valid_plans, start=1):
        existing = manifest["files"].get(plan.path.name)
        if existing is not None and existing.get("status") == "completed":
            print(f"[skip {index}/{len(valid_plans)}] {plan.path.name} already completed.")
            continue

        assert plan.detected_source_language is not None
        assert plan.segment_count is not None
        target_language = _target_language_for(
            plan.detected_source_language,
            args.preferred_target_language,
        )
        print(
            f"[start {index}/{len(valid_plans)}] {plan.path.name} | "
            f"{plan.detected_source_language}->{target_language} | {plan.segment_count} segments"
        )
        manifest["files"][plan.path.name] = {
            "status": "running",
            "source_language": plan.detected_source_language,
            "target_language": target_language,
            "segment_count": plan.segment_count,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _save_manifest(manifest_path, manifest)

        flagged_segments: list[dict[str, Any]] = []
        try:
            job_id = _upload_job(args.api_base, plan)
            manifest["files"][plan.path.name]["job_id"] = job_id
            _save_manifest(manifest_path, manifest)

            _start_job(args.api_base, job_id, plan.detected_source_language, target_language)
            _wait_for_review(args.api_base, job_id)
            segments = _fetch_segments(args.api_base, job_id)

            accepted_count = 0
            corrected_count = 0
            skipped_count = 0
            for segment in segments:
                source_text = normalize_text_for_lookup(str(segment["original_text"]))
                machine_translation = normalize_text_for_lookup(str(segment["final_text"] or ""))
                if not source_text or not machine_translation:
                    skipped_count += 1
                    continue

                reviewed_text, reasons = _review_translation(
                    glossary=glossary,
                    source_language=plan.detected_source_language,
                    target_language=target_language,
                    source_text=source_text,
                    translated_text=machine_translation,
                )
                if reasons:
                    skipped_count += 1
                    flagged_segments.append(
                        {
                            "segment_id": segment["id"],
                            "sheet_name": segment["sheet_name"],
                            "cell_address": segment["cell_address"],
                            "location_type": segment["location_type"],
                            "source_text": source_text,
                            "machine_translation": machine_translation,
                            "reviewed_text": reviewed_text,
                            "reasons": reasons,
                        }
                    )
                    continue

                if reviewed_text != machine_translation:
                    _update_segment(args.api_base, job_id, str(segment["id"]), reviewed_text)
                    corrected_count += 1
                elif _should_save_to_memory(
                    glossary=glossary,
                    source_text=source_text,
                    translated_text=reviewed_text,
                ):
                    _save_memory_entry(
                        base_url=args.api_base,
                        source_language=plan.detected_source_language,
                        target_language=target_language,
                        source_text=source_text,
                        translated_text=reviewed_text,
                    )
                accepted_count += 1

            output_error: str | None = None
            destination: Path | None = None
            try:
                _build_preview(args.api_base, job_id)
                prepared_file_name = _prepare_download(args.api_base, job_id)
                destination = output_dir / prepared_file_name
                _download_output(args.api_base, job_id, destination)
            except Exception as exc:
                output_error = str(exc)

            report_path = report_dir / f"{plan.path.stem}.flagged.json"
            report_path.write_text(
                json.dumps(flagged_segments, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            manifest["files"][plan.path.name] = {
                "status": "completed",
                "job_id": job_id,
                "source_language": plan.detected_source_language,
                "target_language": target_language,
                "segment_count": plan.segment_count,
                "accepted_segments": accepted_count,
                "corrected_segments": corrected_count,
                "flagged_segments": len(flagged_segments),
                "skipped_segments": skipped_count,
                "output_file": str(destination) if destination is not None else None,
                "output_error": output_error,
                "flagged_report": str(report_path),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            _save_manifest(manifest_path, manifest)
            print(
                f"[done  {index}/{len(valid_plans)}] {plan.path.name} | "
                f"accepted={accepted_count} corrected={corrected_count} flagged={len(flagged_segments)}"
                + (f" output_error={output_error}" if output_error else "")
            )
        except Exception as exc:
            manifest["files"][plan.path.name] = {
                "status": "failed",
                "source_language": plan.detected_source_language,
                "target_language": target_language,
                "segment_count": plan.segment_count,
                "error": str(exc),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            _save_manifest(manifest_path, manifest)
            print(f"[fail  {index}/{len(valid_plans)}] {plan.path.name} | {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
