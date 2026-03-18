from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse


def register_frontend_delivery(
    app: FastAPI,
    *,
    frontend_dist_dir: Path | None,
    brand_logo_path: Path | None = None,
) -> None:
    if frontend_dist_dir is None:
        return
    resolved_dist_dir = frontend_dist_dir.resolve()
    index_path = resolved_dist_dir / "index.html"
    if not resolved_dist_dir.exists() or not index_path.exists():
        return
    resolved_brand_logo_path = brand_logo_path.resolve() if brand_logo_path is not None else None

    def resolve_frontend_path(request_path: str) -> Path:
        safe_relative_path = request_path.strip("/") or "index.html"
        candidate = (resolved_dist_dir / safe_relative_path).resolve()
        if resolved_dist_dir not in candidate.parents and candidate != resolved_dist_dir:
            raise HTTPException(status_code=404, detail="Frontend asset was not found.")
        return candidate

    @app.get("/brand/logo-trans.png", include_in_schema=False)
    def serve_brand_logo() -> FileResponse:
        if resolved_brand_logo_path is None or not resolved_brand_logo_path.is_file():
            raise HTTPException(status_code=404, detail="Brand logo was not found.")
        return FileResponse(resolved_brand_logo_path, media_type="image/png")

    @app.get("/", include_in_schema=False)
    def serve_frontend_index() -> FileResponse:
        return FileResponse(index_path)

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend_asset(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Route was not found.")
        asset_path = resolve_frontend_path(full_path)
        if asset_path.is_file():
            return FileResponse(asset_path)
        return FileResponse(index_path)
