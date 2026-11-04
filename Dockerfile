# syntax=docker/dockerfile:1.7

# ---- build: resolve and install dependencies with uv into /app/.venv
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
ARG EXTRAS="--extra anthropic --extra mcp --extra ocr"
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project ${EXTRAS}
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable ${EXTRAS}

# ---- runtime: slim image, OCR for scanned CCTPs, optional LibreOffice for DOCX pages
FROM python:3.12-slim AS runtime
ARG WITH_LIBREOFFICE=false
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra curl \
    && if [ "$WITH_LIBREOFFICE" = "true" ]; then \
         apt-get install -y --no-install-recommends libreoffice-writer-nogui; fi \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 zelles
COPY --from=build --chown=zelles:zelles /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    ZELLES_DATA_DIR=/data \
    ZELLES_LOG_JSON=true
RUN mkdir /data && chown zelles:zelles /data
USER zelles
WORKDIR /home/zelles
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1
CMD ["zelles", "serve", "--host", "0.0.0.0", "--port", "8000"]
