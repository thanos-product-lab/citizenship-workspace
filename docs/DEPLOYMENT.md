# Deployment

**Web → Vercel. API + Celery worker + Postgres + Redis → Railway.** Both deploy
automatically from `main` (no custom CD). See ADR-0003. Object storage (S3) is
added in M7. Public demos use synthetic data only.

Prerequisites: a Railway account, a Vercel account, and your Clerk keys.

## A. Railway — API, worker, Postgres, Redis

1. **New Project → Deploy from GitHub repo** → select this repo. It builds from
   `infra/docker/platform.Dockerfile` via `railway.json` (health check
   `/health/ready`).
2. **Add Postgres** and **Add Redis** (New → Database) in the same project.
3. **API service** — set variables (use Railway *reference variables* for the
   database and cache):
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}` (the app rewrites the scheme to
     `postgresql+psycopg://` automatically)
   - `REDIS_URL` = `${{Redis.REDIS_URL}}`
   - `ENVIRONMENT` = `production`
   - `CLERK_ISSUER` = `https://<your-instance>.clerk.accounts.dev`
   - `CORS_ALLOW_ORIGINS` = your Vercel URL (fill in after step B)
   - `CLERK_AUTHORIZED_PARTIES` = your Vercel URL (optional; must match exactly)

   Then **Settings → Networking → Generate Domain** and note the **API URL**.
   Set the env before the first successful deploy — `/health/ready` needs Postgres
   and Redis reachable, or the health check fails.
4. **Worker service** — New service from the **same repo**; under
   **Settings → Deploy → Start Command** set:
   ```
   uv run celery -A worker.celery_app.celery_app worker --loglevel info
   ```
   Give it `DATABASE_URL` and `REDIS_URL` (same references). No domain / health
   check needed. **Clear its Pre-Deploy Command** (Settings → Deploy) so the worker
   does not also run migrations — the API's pre-deploy owns them (see below), and two
   services running `alembic upgrade head` at once can race on a migration-bearing
   deploy.
5. **Migrations run automatically.** `railway.json` sets the API's
   `deploy.preDeployCommand` to `uv run alembic upgrade head`, so every API deploy
   applies pending migrations (in the built image, with `DATABASE_URL`) *before* the
   new version serves traffic; a failed migration fails the deploy rather than
   booting against a stale schema. This creates the M2 schema and the `app_rls` RLS
   role (ADR-0006). To apply migrations out of band you can still run:
   ```
   railway run --service <api-service> uv run alembic upgrade head
   ```

## B. Vercel — web

1. **Add New → Project** → import this repo.
2. **Root Directory** = `apps/web`. Framework preset **Next.js** (auto). Vercel
   installs the pnpm workspace from the repo root automatically.
3. **Environment Variables**:
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` = `pk_...`
   - `CLERK_SECRET_KEY` = `sk_...`
   - `NEXT_PUBLIC_API_BASE_URL` = the Railway **API URL** from A.3
4. **Deploy**, then note the **Vercel URL**.

## C. Wire the origins together

- Set the Railway API's `CORS_ALLOW_ORIGINS` (and `CLERK_AUTHORIZED_PARTIES`, if
  used) to the Vercel URL, and redeploy the API.
- In Clerk, add the Vercel domain to the instance's allowed origins. For a
  portfolio demo the Clerk **dev** instance is fine; a public launch wants a
  Clerk **production** instance on a custom domain.

## D. Smoke test the deployment

- Add repo secrets **`SMOKE_BASE_URL`** (Vercel URL) and **`SMOKE_API_URL`**
  (Railway API URL), then run **Actions → Smoke → Run workflow**. It also runs
  daily.
- Or locally:
  ```
  pnpm --filter @cw/web exec playwright install chromium
  SMOKE_BASE_URL=<vercel-url> SMOKE_API_URL=<railway-api-url> just e2e
  ```

The smoke checks the web app is reachable and gates unauthenticated users to
sign-in, and that the API health endpoint is live.
