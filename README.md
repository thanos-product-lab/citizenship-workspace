# citizenship-workspace

Evidence-first guidance for UK citizenship applications, with explainable
readiness checks, document workflows, and AI-assisted support.

A private, portfolio-grade prototype that helps an adult who already holds ILR,
indefinite leave to enter, or EU settled status prepare a UK naturalisation
readiness case under the standard Section 6(1) five-year route. It is not legal
advice, not an approval predictor, and not an application-submission tool.

See [`CLAUDE.md`](CLAUDE.md) for the operating manual and [`docs/`](docs/) for the
source-of-truth product, architecture, and rules documents. Build order lives in
[`docs/IMPLEMENTATION_ROADMAP.md`](docs/IMPLEMENTATION_ROADMAP.md).

## Repository layout

```
apps/web/                Next.js workspace (TypeScript)
services/platform/       FastAPI modular monolith + Celery worker (Python)
packages/
  api-client/            GENERATED from the OpenAPI schema — do not hand-edit
  design-system/         domain-meaning components + tokens
  test-fixtures/         shared synthetic fixtures (FE + BE + evals)
docs/                    product · architecture · design · decisions  ← source of truth
```

`packages/api-client` is generated in a later M1 slice and is intentionally
absent until then.

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Node | 22 LTS (see `.nvmrc`) | `nvm use` |
| pnpm | 10+ | `corepack enable` |
| Python | 3.12 (see `services/platform/.python-version`) | — |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| just | latest | `brew install just` (or see casey/just) |

## Setup

```bash
# Frontend + backend dependencies
just install

# Quality gates (run before declaring any change done)
just lint          # eslint + ruff
just typecheck     # tsc (strict) + mypy (strict)
just test          # frontend + backend tests
```

Without `just`, the same gates run directly:

```bash
pnpm install
pnpm run lint && pnpm run typecheck

cd services/platform
uv sync
uv run ruff check . && uv run mypy . && uv run pytest
```

## Authentication & environment

Auth uses [Clerk](https://clerk.com): the web app signs the user in and sends the
session JWT as a bearer token, and the API verifies it against Clerk's JWKS.
Create a Clerk application, then add the keys (all gitignored):

`apps/web/.env.local`

```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

`services/platform/.env`

```
CLERK_ISSUER=https://<your-instance>.clerk.accounts.dev
# optional: restrict the accepted authorized party (azp)
CLERK_AUTHORIZED_PARTIES=http://localhost:3000
```

The API derives the JWKS URL from the issuer. With the API up (`just up`) and
`just dev` running the web app, open http://localhost:3000, sign in, and the
shell shows your account from `/api/v1/me`.

## Deployment

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — web to Vercel, API + worker +
Postgres + Redis to Railway, both auto-deploying from `main`.

## Status

Milestone 1 — platform foundation. The tooling spine, backend service, contract
pipeline, design tokens, an authenticated Next.js shell (Clerk + JWKS), and the
deploy configuration are in place. The domain model begins at M2.
