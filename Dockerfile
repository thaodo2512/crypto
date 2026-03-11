# ── Frontend build stage ──────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# ── Python build stage ────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────
FROM python:3.11-slim AS bot

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

COPY --from=builder /install /usr/local
COPY --from=frontend-builder /build/dist/ /app/static/

COPY main.py .
COPY custom/ custom/
COPY config/ config/
COPY freqtrade/ freqtrade/

RUN mkdir -p data logs && chown -R appuser:appuser /app

VOLUME ["/app/data", "/app/logs"]

EXPOSE 8080

USER appuser

ENTRYPOINT ["python", "main.py"]
