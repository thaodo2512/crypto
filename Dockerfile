# ── Build stage ──────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage (bot) ─────────────────────────────────
FROM python:3.11-slim AS bot

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

COPY --from=builder /install /usr/local

COPY main.py .
COPY custom/ custom/
COPY config/ config/
COPY freqtrade/ freqtrade/
COPY dashboard/ dashboard/

RUN mkdir -p data logs && chown -R appuser:appuser /app

VOLUME ["/app/data", "/app/logs"]

USER appuser

ENTRYPOINT ["python", "main.py"]

# ── Dashboard target ────────────────────────────────────
FROM bot AS dashboard

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
