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
# `ruff format --check` is here deliberately. Without it, formatting drifts in files
# nobody is editing, and the next person to run `ruff format` sweeps a dozen unrelated
# files into their commit — which happened in M5, M6 and twice in M7, and was reverted
# by hand every time. Enforcing it means the drift is fixed once, by whoever introduced
# it, instead of repeatedly by whoever noticed.
lint:
    pnpm run lint
    cd services/platform && uv run ruff check . && uv run ruff format --check .

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
# Selects by marker across the whole suite, not by directory: the invalidation-completeness
# properties are DB-backed and live under tests/assessments, and a directory-scoped recipe
# silently skipped them while still reporting green.
test-rules:
    @if [ -d services/platform/tests ]; then \
        cd services/platform && uv run pytest -m property -q; \
    else \
        echo "test-rules: services/platform/tests not present yet (pre-M3B); skipping."; \
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

# Local MinIO credentials, matching what docker-compose gives the api and worker
# containers. Recipes that run on the *host* need them too and do not get them from
# compose — `just api` and `just seed` both reach object storage now that the seed uploads
# documents, and without these boto3 fails with a bare `NoneType has no attribute
# access_key` that says nothing about what is missing.
#
# Not secrets: these are MinIO's dev defaults, already in docker-compose.yml, and the
# bucket only exists on a developer's machine. A deployment sets them from its own
# environment and never reads this file.
storage_env := "STORAGE_ENDPOINT_URL=http://localhost:9000 STORAGE_BUCKET=citizenship-evidence STORAGE_ACCESS_KEY=minioadmin STORAGE_SECRET_KEY=minioadmin"

# Run the FastAPI app locally with reload (reads services/platform/.env).
api:
    cd services/platform && {{storage_env}} uv run uvicorn app.main:app --reload --port 8000

# Run the Next.js app against the local API.
dev:
    pnpm --filter @cw/web dev

# Load the canonical synthetic demo case (§13 of MVP RFC) via the real command path.
# Pass a signed-in user id to seed it into an account you can open in the browser;
# the default `demo-user` is what the CLI walkthroughs use.
#
# Needs MinIO up (`just up`) as well as Postgres: from M7 slice 4a the seed uploads eleven
# travel documents through the real upload path, so eleven trips have evidence attached and
# trip 6 (Greece) deliberately does not.
seed user_id="demo-user":
    cd services/platform && {{storage_env}} uv run python -m app.seed.demo_case {{user_id}}

# Recalculate a case and print its requirement conclusions (dev walkthrough helper).
recalc case_id user_id="demo-user":
    cd services/platform && uv run python -m scripts.recalc {{case_id}} {{user_id}}

# Print one requirement's full detail: parameters, limitations, input-link provenance, history.
inspect case_id requirement_key user_id="demo-user":
    cd services/platform && uv run python -m scripts.inspect {{case_id}} {{requirement_key}} {{user_id}}

# Edit a trip's return date (fires stale invalidation) — drives the M3B stale demo.
edit-trip case_id departure new_return user_id="demo-user":
    cd services/platform && uv run python -m scripts.edit_trip {{case_id}} {{departure}} {{new_return}} {{user_id}}

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

# AI evaluation suite — NOT run on every commit (AI_EVALUATION_PLAN.md §27).
# Generates the fixture documents first: they are gitignored, for the same reason
# scripts/make_fixtures.py's are — a checked-in PDF is a binary nobody reviews.
eval:
    cd services/platform && uv run python evals/fixtures/make_documents.py >/dev/null
    cd services/platform && uv run python -m evals.runner
