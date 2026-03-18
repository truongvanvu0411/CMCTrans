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
ENV PIP_DEFAULT_TIMEOUT=300
ENV PIP_RETRIES=10

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --prefer-binary -r /app/backend/requirements.txt

COPY backend /app/backend
COPY logo /app/logo
COPY --from=frontend-build /app/frontend/dist /app/frontend_dist

RUN mkdir -p /app/workspace /app/models

EXPOSE 8000

CMD ["python", "-m", "backend.app.launcher", "--no-browser", "--host", "0.0.0.0", "--port", "8000"]
