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
# `--no-sync` is load-bearing, not a micro-optimisation. Plain `uv run` re-resolves the
# environment against pyproject.toml at *start* time and installs the dev group, so
# every container boot downloaded mypy, ruff, hypothesis and pygments — ~28MB of test
# tooling into a production image, on every restart, over the network. Visible in the
# deploy log as "Installed 18 packages" seconds before the app starts.
#
# Three costs, and the third is the one that matters: it is slow, it puts developer
# tooling in production, and it makes a *network fetch* a prerequisite for a process
# that has already been built. A registry outage would then stop a container that has
# everything it needs on disk. The image was built with `--no-dev` above; this makes
# the runtime honour that rather than quietly undo it.
CMD ["sh", "-c", "uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
