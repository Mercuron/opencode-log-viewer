# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build
# vite.config.ts writes straight to ../viewer/static, i.e. /app/viewer/static

FROM python:3.12-slim AS runtime
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock.txt ./
RUN pip install --require-hashes --no-deps -r requirements.lock.txt

COPY pyproject.toml README.md ./
COPY viewer/ ./viewer/
COPY migrations/ ./migrations/
COPY --from=frontend /app/viewer/static ./viewer/static

RUN pip install --no-deps .

ENV VIEWER_DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8080

CMD ["uvicorn", "viewer.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
