# Deployment And Packaging Spec

## Goal
- Ship the translator as a portable Windows app for users who do not have Python or Node installed.
- Keep one backend runtime for source mode, Docker mode, and packaged `.exe` mode.
- Serve the built frontend from FastAPI so the application runs from a single local server.

## Modes

### 1. Source Mode
- Audience: developers.
- Run frontend build once, then start backend with `python -m backend.app.launcher`.
- Backend serves `frontend/dist`.

### 2. Docker Mode
- Audience: developers or internal operators comfortable with Docker Desktop.
- Run with `docker compose up --build`.
- Container serves API and frontend from one process.
- `models/` and `workspace/` are mounted as volumes.

### 3. Windows Portable Release
- Audience: internal users without Python.
- Build with PyInstaller in one-folder mode.
- Release layout:
  - `translator.exe`
  - `_internal/`
  - `models/`
  - `workspace/`
  - `start.bat`
  - `README.txt`

## Runtime Rules
- FastAPI serves frontend static files when a built frontend directory exists.
- Frontend routing remains hash-based.
- API stays under `/api/*`.
- Non-API routes serve frontend `index.html`.
- Models remain external to the executable to avoid rebuilding the `.exe` when models change.
- Workspace and database remain writable next to the executable.

## Config Resolution
- Source mode:
  - `root_dir = repo root`
  - `models_dir = <repo>/models`
  - `workspace_dir = <repo>/workspace`
  - `frontend_dist_dir = <repo>/frontend/dist`
- Packaged mode:
  - `root_dir = executable directory`
  - `bundle_dir = PyInstaller _MEIPASS`
  - `models_dir = <exe dir>/models`
  - `workspace_dir = <exe dir>/workspace`
  - `frontend_dist_dir = <bundle>/frontend_dist`
- Optional overrides:
  - `TRANSLATOR_ROOT_DIR`
  - `TRANSLATOR_BUNDLE_DIR`
  - `TRANSLATOR_MODELS_DIR`
  - `TRANSLATOR_WORKSPACE_DIR`
  - `TRANSLATOR_FRONTEND_DIST_DIR`
  - `TRANSLATOR_GLOSSARY_PATH`
  - `TRANSLATOR_HOST`
  - `TRANSLATOR_PORT`
  - `TRANSLATOR_OPEN_BROWSER`

## Build Pipeline

### Frontend
- `npm ci`
- `npm run build`
- Output goes to `frontend/dist`

### PyInstaller Release
- Build frontend first.
- Install backend runtime and packaging requirements.
- Build from `backend.app.launcher`.
- Bundle:
  - `backend/app/data/it_glossary.json`
  - `frontend/dist`
- Copy models into release folder after PyInstaller finishes.

### Docker
- Multi-stage image:
  - Node stage builds frontend
  - Python stage installs backend requirements
- Runtime serves frontend from bundled static files.

## Release Output
- Release root: `release/windows-app/`
- Contents:
  - `translator.exe`
  - `_internal/`
  - `models/`
  - `workspace/`
  - `start.bat`
  - `README.txt`

## Acceptance Criteria
- `python -m backend.app.launcher` serves both `/api/health` and `/`.
- `docker compose up --build` serves the app on `http://127.0.0.1:8000`.
- Packaged release starts with `start.bat` on a Windows machine without Python.
- Frontend and API behave the same in source, Docker, and packaged modes.
