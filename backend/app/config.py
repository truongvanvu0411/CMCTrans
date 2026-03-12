from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppConfig:
    root_dir: Path
    models_dir: Path
    workspace_dir: Path
    database_path: Path
    glossary_path: Path | None = None
    frontend_dist_dir: Path | None = None
    host: str = "127.0.0.1"
    port: int = 8000
    open_browser: bool = False


def _resolve_runtime_root() -> Path:
    override = os.getenv("TRANSLATOR_ROOT_DIR")
    if override:
        return Path(override).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return ROOT_DIR


def _resolve_bundle_root(runtime_root: Path) -> Path:
    override = os.getenv("TRANSLATOR_BUNDLE_DIR")
    if override:
        return Path(override).resolve()
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir is not None:
        return Path(bundle_dir).resolve()
    return runtime_root


def _resolve_frontend_dist(bundle_root: Path) -> Path | None:
    override = os.getenv("TRANSLATOR_FRONTEND_DIST_DIR")
    if override:
        return Path(override).resolve()
    source_dist_dir = bundle_root / "frontend" / "dist"
    if source_dist_dir.exists():
        return source_dist_dir
    packaged_dist_dir = bundle_root / "frontend_dist"
    if packaged_dist_dir.exists():
        return packaged_dist_dir
    return None


def _resolve_glossary_path(bundle_root: Path) -> Path:
    override = os.getenv("TRANSLATOR_GLOSSARY_PATH")
    if override:
        return Path(override).resolve()
    source_glossary_path = bundle_root / "backend" / "app" / "data" / "it_glossary.json"
    if source_glossary_path.exists():
        return source_glossary_path
    packaged_glossary_path = bundle_root / "app_data" / "it_glossary.json"
    if packaged_glossary_path.exists():
        return packaged_glossary_path
    return source_glossary_path


def get_config() -> AppConfig:
    runtime_root = _resolve_runtime_root()
    bundle_root = _resolve_bundle_root(runtime_root)
    workspace_dir = Path(
        os.getenv("TRANSLATOR_WORKSPACE_DIR", str(runtime_root / "workspace"))
    ).resolve()
    models_dir = Path(os.getenv("TRANSLATOR_MODELS_DIR", str(runtime_root / "models"))).resolve()
    return AppConfig(
        root_dir=runtime_root,
        models_dir=models_dir,
        workspace_dir=workspace_dir,
        database_path=workspace_dir / "app.db",
        glossary_path=_resolve_glossary_path(bundle_root),
        frontend_dist_dir=_resolve_frontend_dist(bundle_root),
        host=os.getenv("TRANSLATOR_HOST", "127.0.0.1"),
        port=int(os.getenv("TRANSLATOR_PORT", "8000")),
        open_browser=os.getenv("TRANSLATOR_OPEN_BROWSER", "false").lower() == "true",
    )
