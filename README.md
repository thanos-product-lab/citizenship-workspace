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

`packages/api-client` is generated from the API's OpenAPI schema by
`just api-client`. CI fails if it drifts from the schema, so it is regenerated as part
of any change to a request or response.

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

Two environment files, both gitignored, each read by exactly one thing.

**`services/platform/.env`** — the API and the worker. Start from the committed
template, which documents every variable and why it exists:

```
cp services/platform/.env.example services/platform/.env
```

The template lives beside the file it describes because `Settings(env_file=".env")`
resolves relative to the working directory, and both processes run from
`services/platform`. A `.env` anywhere else is read by nothing.

Nothing in it is required for local development: the API boots without secrets, and
`check_backing_services`, `check_upload_secret` and `check_ai_configuration` only
refuse to start when `ENVIRONMENT` is not local. Set what you need.

**`apps/web/.env.local`** — the Next.js app.

```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### Auth

Auth uses [Clerk](https://clerk.com): the web app signs the user in and sends the
session JWT as a bearer token, and the API verifies it against Clerk's JWKS. Create a
Clerk application, then add to `services/platform/.env`:

```
CLERK_ISSUER=https://<your-instance>.clerk.accounts.dev
# optional: restrict the accepted authorized party (azp)
CLERK_AUTHORIZED_PARTIES=http://localhost:3000
```

The API derives the JWKS URL from the issuer. With the API up (`just up`) and
`just dev` running the web app, open http://localhost:3000, sign in, and the
shell shows your account from `/api/v1/me`.

### AI provider

Only needed once you are working on M8 (document AI). Without a key the API still
boots and serves; document extraction is what fails.

```
OPENAI_API_KEY=sk-...
```

`AI_DAILY_SPEND_CEILING_USD` is a hard stop, deployment-wide, resetting at 00:00 UTC.
It defaults to a low number on purpose — it exists to bound a loop, not ordinary use.
See `services/platform/.env.example` for the rest, and
[`docs/evaluations/AI_SPIKE_FINDINGS.md`](docs/evaluations/AI_SPIKE_FINDINGS.md) §4
for where the timeout and deadline values come from.

## Deployment

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — web to Vercel, API + worker +
Postgres + Redis to Railway, both auto-deploying from `main`.

## Status

**In active development. Not open to users, and not intended to be.** This is a
portfolio prototype built to demonstrate how an AI-native product can keep model
output from silently becoming truth. It runs on synthetic data only, gives no legal
advice, predicts no outcomes, and submits nothing.

**Built so far — M0 to M6.** (M6 precedes M5 by design: stale-state is the thesis,
the timeline is the showcase and the safer cut.)

Versioned case inputs with immutable history; a deterministic rules engine covering
the Section 6(1) five-year route; assessments that are never edited in place, each
carrying a conclusion, a separate currency, the exact input versions and rule version
behind it, and structured limitations.

On top of that: **selective invalidation** — changing an input marks stale exactly the
conclusions that declared a dependency on it, resolved from the rule catalogue rather
than a hand-maintained list — and a **durable issue queue** that opens when a cause
appears and closes when it is fixed, including when a recalculation itself fails.

Most recently, **application-date simulation**: preview a candidate date and see what
the rules would conclude at it, against your real records, with nothing written. That
preview writes no run, no result and no provenance — a simulated result has no field
in which to record any, so persisting one is a type error rather than a guard someone
can delete. And a **residence timeline** — a chronological table of every trip with the
days each contributes to the qualifying window, and a visual band above it that adds a
shape and no facts.

**Next — M7** (private evidence storage and asynchronous processing), then M8
(human-in-the-loop document AI, the first live model calls). Build order and cut lines
are in [`docs/IMPLEMENTATION_ROADMAP.md`](docs/IMPLEMENTATION_ROADMAP.md).

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
