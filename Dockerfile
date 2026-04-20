# ── Stage 1: Builder ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir --prefix=/install .

# ── Stage 2: Runtime ───────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="XBRLValidator Team"
LABEL description="XBRL/iXBRL Validator Engine — API Server"

RUN apt-get update && \
    apt-get install -y --no-install-recommends libxml2 libxslt1.1 curl && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --gid 1000 xbrl && \
    useradd --uid 1000 --gid xbrl --shell /bin/bash --create-home xbrl

COPY --from=builder /install /usr/local

WORKDIR /app
COPY src/ src/

RUN mkdir -p /home/xbrl/.xbrl-validator/cache && \
    chown -R xbrl:xbrl /app /home/xbrl/.xbrl-validator

USER xbrl

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    XBRL_ENV=production \
    XBRL_LOG_LEVEL=INFO \
    XBRL_LOG_FORMAT=json \
    XBRL_API_HOST=0.0.0.0 \
    XBRL_API_PORT=8000 \
    XBRL_API_WORKERS=4

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.api.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--access-log"]
