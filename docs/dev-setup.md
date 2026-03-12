# Dev Setup

## Option 1: Docker

```powershell
docker compose up --build
```

App runs at `http://127.0.0.1:8000`.

## Option 2: Local Python + Node

1. Install backend requirements:

```powershell
python -m pip install -r backend/requirements.txt
```

2. Install frontend dependencies:

```powershell
cd frontend
npm ci
npm run build
cd ..
```

3. Download models:

```powershell
.\scripts\download-models.ps1
```

4. Start the app:

```powershell
python -m backend.app.launcher --open-browser
```
