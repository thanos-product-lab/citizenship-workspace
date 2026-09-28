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

# Run as an unprivileged user. Celery warned about root on every boot, and rightly: the
# worker parses attacker-supplied PDFs with a C library, and a process that escaped a
# parser would otherwise own the container. The app only reads /app; anything it writes
# (Celery beat's schedule, temporary files) goes to /tmp.
RUN useradd --create-home --uid 10001 app
USER app

# The venv's binaries directly, never `uv run`. `uv run` re-resolves the environment at
# start and, without `--no-sync`, installed the dev group on every boot (~28MB of test
# tooling, over the network, before the app could start). With `--no-sync` it still stayed
# resident as a parent process holding ~170MB, and it wants a writable cache the
# unprivileged user does not have. The image was built with `--no-dev`; calling the
# binaries is how the runtime honours that.
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
