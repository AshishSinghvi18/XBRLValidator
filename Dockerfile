FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
COPY config/ config/
RUN pip install --no-cache-dir .

FROM python:3.12-slim
WORKDIR /app
RUN useradd -m -r validator && mkdir -p /var/cache/xbrl && chown validator:validator /var/cache/xbrl
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/xbrl-* /usr/local/bin/
COPY --from=builder /app/src /app/src
COPY --from=builder /app/config /app/config
USER validator
ENV XBRL_TAXONOMY_CACHE_DIR=/var/cache/xbrl
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/v1/health || exit 1
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
