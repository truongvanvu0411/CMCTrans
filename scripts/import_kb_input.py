from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from backend.app.services.kb_dataset_import import (
    KnowledgeDatasetImportError,
    import_datasets_into_translation_memory,
)


def _default_backup_path(database_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return database_path.with_name(f"{database_path.stem}.backup-{timestamp}{database_path.suffix}")


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Import data/kb_input JSON datasets into translation_memory."
    )
    parser.add_argument(
        "--database",
        default="workspace/app.db",
        help="SQLite database path for the translator workspace.",
    )
    parser.add_argument(
        "--input-dir",
        default="data/kb_input",
        help="Directory containing ja/en/vi JSON dataset files.",
    )
    parser.add_argument(
        "--backup-path",
        default=None,
        help="Optional explicit backup path. Defaults to a timestamped backup next to the database.",
    )
    args = parser.parse_args(argv)

    database_path = Path(args.database)
    input_dir = Path(args.input_dir)
    if not database_path.exists():
        raise KnowledgeDatasetImportError(f"Database was not found: {database_path}")
    if not input_dir.exists():
        raise KnowledgeDatasetImportError(f"Input directory was not found: {input_dir}")

    dataset_paths = sorted(path for path in input_dir.iterdir() if path.suffix.lower() == ".json")
    if not dataset_paths:
        raise KnowledgeDatasetImportError(f"No JSON dataset files were found in {input_dir}")

    backup_path = Path(args.backup_path) if args.backup_path else _default_backup_path(database_path)
    summary = import_datasets_into_translation_memory(
        database_path=database_path,
        dataset_paths=dataset_paths,
        backup_path=backup_path,
    )
    print(f"Imported {summary.dataset_records} dataset records from {summary.dataset_files} files.")
    print(f"Upserted {summary.imported_pairs} translation-memory pairs.")
    print(f"translation_memory now contains {summary.translation_memory_rows} rows.")
    if summary.backup_path is not None:
        print(f"Backup written to {summary.backup_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run(sys.argv[1:]))
    except KnowledgeDatasetImportError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
