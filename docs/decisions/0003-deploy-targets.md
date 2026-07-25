# ADR-0003: Deploy targets — Vercel (web) + Railway (API, worker, Postgres, Redis)

**Status:** Accepted
**Date:** 2026-07-25
**Milestone:** M1 slice 6 (deploy)

## Context

M1's last slice deploys the stack so every milestone is demoable. The Technical
Architecture RFC §28 lists web → Vercel and API → Railway or Fly, with managed
Postgres and Redis. We need to pick the API/worker host. The priority at this
stage is a demoable deployment with the least operational overhead, not
infrastructure breadth.

## Decision

- **Web → Vercel.** Best Next.js DX, preview deploys, native GitHub integration.
- **API + Celery worker → Railway**, as two services built from the existing
  `infra/docker/platform.Dockerfile` (same image, different start commands).
- **Managed Postgres + Redis → Railway plugins**, linked to the API and worker.
- Both providers deploy automatically from GitHub `main`, so **no custom CD
  workflow** is needed.
- **Object storage (S3) is deferred to M7** — there is no evidence upload yet, so
  M1's deploy does not provision it.

## Alternatives rejected

- **Fly.io.** Credible and more capable (global machines, fine-grained control),
  but adds per-app `fly.toml` config and separate Postgres/Redis provisioning we
  do not need at this stage. More ops for no M1 benefit.
- **All-Railway (web included).** Fewer accounts, but Vercel is the stronger
  Next.js host and is RFC-specified; the marginal simplicity isn't worth losing
  Vercel's build/preview tooling.
- **AWS/Kubernetes.** On the rejected list (CLAUDE.md §10) — disproportionate ops
  for a portfolio prototype.

## Consequences

- Two dashboards (Vercel, Railway); secrets live in each provider's store.
- Railway injects `DATABASE_URL`/`REDIS_URL`; Postgres arrives as bare
  `postgresql://`, so the app normalizes it to `postgresql+psycopg://`.
- The deployed web origin must be added to the API's `CORS_ALLOW_ORIGINS`, and
  the Clerk keys set in both providers.
- Revisit if the worker or Postgres outgrows Railway's tiers.

## Invariants touched

None of CLAUDE.md §2. The public demo remains synthetic-data-only (§2.9); no real
personal data is deployed.
