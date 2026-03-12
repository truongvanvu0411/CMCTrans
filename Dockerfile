FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.10-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TRANSLATOR_HOST=0.0.0.0
ENV TRANSLATOR_PORT=8000
ENV TRANSLATOR_OPEN_BROWSER=false

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY --from=frontend-build /app/frontend/dist /app/frontend_dist

RUN mkdir -p /app/workspace /app/models

EXPOSE 8000

CMD ["python", "-m", "backend.app.launcher", "--no-browser", "--host", "0.0.0.0", "--port", "8000"]
