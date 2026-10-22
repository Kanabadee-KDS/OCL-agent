# OCL Agent API + worker (same image, different command)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# tesseract-ocr-{tha,eng}: language data for OCR of scanned pages (MuPDF links its own Tesseract)
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
        tesseract-ocr-tha tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
# dependency layer first (cache), then source
COPY pyproject.toml uv.lock .python-version ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
RUN mkdir -p apps/api/src/ocl_api && touch apps/api/src/ocl_api/__init__.py \
    && uv sync --frozen --no-dev --no-install-workspace
COPY apps/api apps/api
COPY tools tools
RUN uv sync --frozen --no-dev

ENV PATH="/opt/venv/bin:$PATH" \
    DATA_DIR=/server_data \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    INLINE_WORKER=false
RUN useradd -r -u 10001 ocl && mkdir -p /server_data && chown ocl /server_data
USER ocl
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fs http://127.0.0.1:8000/health || exit 1
CMD ["ocl", "api", "--host", "0.0.0.0", "--port", "8000"]
