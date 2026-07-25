# Cross-language command runner for citizenship-workspace.
# Keep this in sync with CLAUDE.md §5. Recipes for later milestones are stubs
# that exit cleanly until their slice lands.

# List available recipes.
default:
    @just --list

# --- setup ---

# Install all dependencies (frontend via pnpm, backend via uv).
install:
    pnpm install
    cd services/platform && uv sync

# --- quality gates ---

# Lint everything (eslint + ruff).
lint:
    pnpm run lint
    cd services/platform && uv run ruff check .

# Strict type-check everything (tsc + mypy).
typecheck:
    pnpm run typecheck
    cd services/platform && uv run mypy

# All tests (frontend + backend).
test: test-fe test-be

# Backend tests (pytest: unit + integration + property-based).
test-be:
    cd services/platform && uv run pytest

# Exits 0 when the rule tests do not exist yet (pre-M3B) so the PostToolUse hook
# does not error.

# Hypothesis property suite for the deterministic rules (DETERMINISTIC_RULES_SPEC.md §10).
test-rules:
    @if [ -d services/platform/tests/rules ]; then \
        cd services/platform && uv run pytest tests/rules -m property -q; \
    else \
        echo "test-rules: services/platform/tests/rules not present yet (pre-M3B); skipping."; \
    fi

# Frontend tests (vitest + testing-library).
test-fe:
    pnpm -r --if-present test

# --- not yet implemented (land in the noted slice/milestone) ---

# Bring up local infra + services (postgres, redis, minio, api, worker).
up:
    docker compose up --build -d

# Stop and remove local services.
down:
    docker compose down

# Follow local service logs.
logs:
    docker compose logs -f

# Apply database migrations (alembic upgrade head).
migrate:
    cd services/platform && uv run alembic upgrade head

# Run the FastAPI app locally with reload (reads services/platform/.env).
api:
    cd services/platform && uv run uvicorn app.main:app --reload --port 8000

# Run the Next.js app against the local API.
dev:
    pnpm --filter @cw/web dev

# Load the canonical synthetic demo case (M3A).
seed:
    @echo "just seed: not until M3A (synthetic demo case)."

# Regenerate packages/api-client from the FastAPI OpenAPI schema.
api-client:
    mkdir -p packages/api-client/generated
    cd services/platform && uv run python -m scripts.export_openapi > ../../packages/api-client/generated/openapi.json
    pnpm exec openapi-typescript packages/api-client/generated/openapi.json -o packages/api-client/generated/schema.d.ts

# Playwright smoke test against a deployed (or local) URL.
# First install browsers: pnpm --filter @cw/web exec playwright install chromium
# Set SMOKE_BASE_URL / SMOKE_API_URL to target a deployment.
e2e:
    pnpm --filter @cw/web exec playwright test

# AI evaluation suite — NOT run on every commit (M8).
eval:
    @echo "just eval: not until M8 (AI evaluation harness)."
