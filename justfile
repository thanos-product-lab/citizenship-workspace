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
    cd services/platform && uv run mypy .

# All tests (frontend + backend).
test: test-fe test-be

# Backend tests (pytest: unit + integration + property-based).
test-be:
    cd services/platform && uv run pytest

# Hypothesis property suite for the deterministic rules (DETERMINISTIC_RULES_SPEC.md §10).
# Exits 0 when the rule tests do not exist yet (pre-M3B) so the PostToolUse hook
# does not error.
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

# Bring up local infra: postgres, redis, minio, api, worker (M1 slice 2).
up:
    @echo "just up: not until M1 slice 2 (Docker Compose)."

# Run Next.js against the local API (M1 slice 5).
dev:
    @echo "just dev: not until M1 slice 5 (web shell)."

# alembic upgrade head (M1 slice 2).
migrate:
    @echo "just migrate: not until M1 slice 2 (Alembic baseline)."

# Load the canonical synthetic demo case (M3A).
seed:
    @echo "just seed: not until M3A (synthetic demo case)."

# Regenerate packages/api-client from the FastAPI OpenAPI schema (M1 slice 3).
api-client:
    @echo "just api-client: not until M1 slice 3 (contract pipeline)."

# Playwright end-to-end (M1 slice 6).
e2e:
    @echo "just e2e: not until M1 slice 6 (deploy + smoke)."

# AI evaluation suite — NOT run on every commit (M8).
eval:
    @echo "just eval: not until M8 (AI evaluation harness)."
