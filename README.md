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

**In active development. Not open to users, and not intended to be.** This is a
portfolio prototype built to demonstrate how an AI-native product can keep model
output from silently becoming truth. It runs on synthetic data only, gives no legal
advice, predicts no outcomes, and submits nothing.

**Built so far — M0 to M4.** Versioned case inputs with immutable history; a
deterministic rules engine covering the Section 6(1) five-year route; assessments
that are never edited in place, each carrying a conclusion, a separate currency, the
exact input versions and rule version behind it, and structured limitations; and a
workspace that renders all of it — an overview, the requirement list, and an
explanation stack that traces any conclusion back to the facts that produced it.

**Next — M6** (issue detection and selective stale invalidation), then M5 (timeline
and application-date simulation), M7 (evidence), M8 (human-in-the-loop document AI).
Build order and cut lines are in
[`docs/IMPLEMENTATION_ROADMAP.md`](docs/IMPLEMENTATION_ROADMAP.md).

### Worth reading first

If you are here to look rather than to run it:

- [`docs/demo-assets/`](docs/demo-assets/) — screens from the current build, and the
  terminal captures they are checked against. The figures in both agree, which is the
  point of keeping them side by side.
- [`docs/decisions/`](docs/decisions/) — the design decisions, each with the
  alternative it rejected and why.
- [`docs/architecture/DOMAIN_MODEL_RFC.md`](docs/architecture/DOMAIN_MODEL_RFC.md) and
  [`DETERMINISTIC_RULES_SPEC.md`](docs/architecture/DETERMINISTIC_RULES_SPEC.md) — the
  model and the date arithmetic, which is where the real difficulty is.

Everything runs locally against synthetic fixtures — see Setup above.
