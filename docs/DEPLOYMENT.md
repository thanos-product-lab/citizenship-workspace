# Deployment

**Web → Vercel. API + Celery worker (with its scheduler) + Postgres + Redis → Railway.** Both deploy
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
   - `UPLOAD_TOKEN_SECRET` = 32+ random characters. **The API refuses to boot without
     it** whenever `ENVIRONMENT` is anything but `local`/`docker`/`test`. Generate one
     with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

   Then **Settings → Networking → Generate Domain** and note the **API URL**.
   Set the env before the first successful deploy — `/health/ready` needs Postgres
   and Redis reachable, or the health check fails.

   > **Why `UPLOAD_TOKEN_SECRET` is fatal rather than a warning.** It signs the token
   > that carries an evidence upload's storage key back from the browser (ADR-0019).
   > Unset, the key is per-process — fine for one instance, and silently wrong for two:
   > a token signed by one replica is rejected by the other, and the symptom is
   > intermittent 422s indistinguishable from tampering. Discovering that from a support
   > conversation is worse than failing at boot.

### Object storage for evidence (M7)

**Evidence upload does not work on Railway until an S3-compatible bucket exists.** There
is no managed object storage on Railway, and the storage settings default to a local
MinIO — so on a deployed instance the API boots and the Evidence destination lists
nothing, but any upload fails. Reads of existing rows are unaffected; nothing touches
storage until an upload or a content URL is requested.

To make it work, provision a private bucket anywhere S3-compatible (Cloudflare R2, AWS
S3, Backblaze B2, or a MinIO service in the same Railway project) and set on **both** the
API and the worker:

   - `STORAGE_ENDPOINT_URL` (omit for real AWS S3)
   - `STORAGE_BUCKET`
   - `STORAGE_ACCESS_KEY` / `STORAGE_SECRET_KEY`
   - `STORAGE_REGION` if the provider needs one

The bucket must be **private**, and the application does not create it: an application
whose credentials can create buckets is an application whose credentials can create a
*public* one. `ensure_bucket()` runs only under `ENVIRONMENT=local`/`docker`.
4. **Worker service** — New service from the **same repo**; under
   **Settings → Deploy → Start Command** set:
   ```
   uv run celery -A worker.celery_app.celery_app worker --beat --loglevel info
   ```
   Give it `DATABASE_URL`, `REDIS_URL` (same references) and the storage variables
   from the section below. It needs no domain, and **no Clerk or upload-token variables**:
   it never verifies a token or signs one.

   Two things to clear under **Settings → Deploy**, both because `railway.json` sits at
   the repo root and every service built from this repo reads it:

   - **Pre-Deploy Command** — otherwise the worker also runs `alembic upgrade head`, and
     two services racing that on a migration-bearing deploy is how you get a half-applied
     schema.
   - **Healthcheck Path** — `railway.json` sets `/health/ready` for the API. A Celery
     worker serves no HTTP at all, so the check can never pass; Railway marks the deploy
     unhealthy and restarts it, and the symptom is a worker that looks like it is crashing
     when it is only unreachable in a way it was never meant to be reachable.

   > **`--beat` is not optional, and its absence is silent.** The scheduler is what runs
   > the outbox relay, and the relay is what turns a written event into work: without it
   > an uploaded document stays in `UPLOADED` for ever and a deleted one's bytes are never
   > purged. The API still returns 204 and the row still disappears, so nothing on screen
   > says anything is wrong.
   >
   > This deployment had no scheduler at all until M7 slice 5 — `docker-compose.yml` ran a
   > separate `beat` container that these instructions never mentioned, so local worked and
   > deployed did not. Compose now runs the same one-service shape for that reason.
   >
   > **Keep this service at one replica while `--beat` is on.** Each replica would carry
   > its own scheduler. That is *not* the disaster it sounds like — `claim_unpublished`
   > takes its batch `FOR UPDATE SKIP LOCKED`, so two relays claim different rows and no
   > row is ever dispatched twice — but a deployment that genuinely needs several workers
   > should split beat back into its own single-replica service rather than multiply it.
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
