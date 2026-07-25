# Shared image for the FastAPI API and the Celery worker.
# Build context is the repo root; the service is copied from services/platform.
FROM python:3.12-slim

# uv for reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (better layer caching). Lockfile is optional until
# it is committed; fall back to a plain resolve when absent.
COPY services/platform/pyproject.toml services/platform/uv.lock* ./
RUN if [ -f uv.lock ]; then uv sync --frozen --no-dev; else uv sync --no-dev; fi

# Then the application code.
COPY services/platform/ ./

EXPOSE 8000
# $PORT is provided by the platform (Railway); defaults to 8000 locally.
CMD ["sh", "-c", "uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
