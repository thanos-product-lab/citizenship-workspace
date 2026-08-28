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

To make it work, provision a private bucket on an S3-compatible provider **that
implements POST Object** (see the compatibility note below — this rules out Cloudflare R2)
and set on **both** the API and the worker:

   - `STORAGE_ENDPOINT_URL` — for real AWS S3 set it **explicitly** to
     `https://s3.<region>.amazonaws.com`. "Omit it" is wrong and the failure is quiet:
     the setting defaults to `http://localhost:9000`, so an *unset* variable points a
     deployed service at a MinIO that is not there. (An explicitly *empty* value also
     works — `S3Storage` maps `""` to `None` and boto3 then picks the regional endpoint —
     but empty-means-default is easy to misread in a config file, so name it.)
   - `STORAGE_BUCKET`
   - `STORAGE_ACCESS_KEY` / `STORAGE_SECRET_KEY`
   - `STORAGE_REGION` if the provider needs one

**Create the bucket yourself.** `ensure_bucket()` runs only under
`ENVIRONMENT=local`/`docker`, deliberately: an application whose credentials can create a
bucket can create a *public* one. Scope the credentials to object read/write on that one
bucket, not to bucket administration.

### Check a provider before wiring it up

The upload path signs a **POST policy** (`generate_presigned_post`), not a presigned PUT,
because the policy is what carries `content-length-range` — that is how the size limit
becomes something the *store* refuses rather than something the API notices afterwards
(§18). S3 POST Object is less universally implemented than PUT, so a provider can be
"S3-compatible" and still not serve this path.

Rather than find out through a broken upload, point the storage suite at the candidate.
It asserts exactly the properties that decide whether a store is usable — private bucket,
expiring URL, store-enforced size ceiling, deleted object staying deleted — with the same
code that guards the real thing:

```bash
cd services/platform
CW_EXPECT_MINIO=1 \
STORAGE_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com \
STORAGE_BUCKET=<your-bucket> \
STORAGE_ACCESS_KEY=<token-id> STORAGE_SECRET_KEY=<token-secret> \
STORAGE_REGION=auto \
uv run pytest tests/evidence/test_storage_minio.py -q
```

Seven passes means the provider serves every operation this product needs. A failure in
`test_an_upload_cannot_declare_a_different_content_type_than_the_one_signed` or
`test_an_oversized_body_is_refused_by_the_store_and_nothing_is_written` means POST policies
are not honoured — use a provider that does, rather than weakening the upload path.

### Cloudflare R2 does not work — measured, 2026-08-28

R2 answers a presigned POST with **`501 Not Implemented`**. Not a signature problem, not a
permissions problem: the request authenticates and R2 replies that it does not implement
the operation. All seven storage tests fail, because every one of them uploads first.

Everything else about R2 is fine, which is what makes this worth recording rather than
just avoiding. Verified against a live bucket:

| Operation | Result |
|---|---|
| `head_bucket` with an Object Read & Write token | OK |
| Presigned **PUT** upload | 200 |
| Presigned GET | 200 |
| `delete_object` | OK |
| Presigned **POST** upload | **501** |

So R2 becomes available the day the upload path moves from a signed POST policy to a
signed PUT — which is a real option, not a workaround, but it is a change to the control
that bounds upload size and belongs in its own slice with its own ADR. A presigned PUT can
sign `Content-Length`, so the store still refuses a body that does not match what was
authorised; what changes is that the ceiling is enforced against the client's *declared*
size (already refused above `max_upload_bytes` at presign) rather than by a range condition
in a policy. Equivalent in effect, different in shape, and not something to swap in
mid-milestone to save a few pounds a month.

Until then, use a provider that implements POST Object. **Verify before wiring**, with the
command above — that is what it is for.

### AWS S3 — verified 2026-08-28

All seven storage tests pass against a live bucket in `eu-west-2`: private bucket,
expiring URL, content-type bound by the signature, store-enforced size ceiling, zero-byte
body refused, deleted object unreachable through an old URL, download disposition
preserved. POST Object is implemented, so the upload path works unchanged.

A bucket with **Block all public access** left on (the default), plus an IAM user whose
policy covers exactly the four operations this product performs — and no more. `ListBucket`
is there for `head_bucket`; with it granted, `ensure_bucket` never reaches `CreateBucket`,
which is the permission deliberately withheld (§ above: credentials that can create a
bucket can create a public one).

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::YOUR-BUCKET" },
    { "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::YOUR-BUCKET/*" }
  ]
}
```

Then `STORAGE_REGION` = the bucket's region, and a **CORS configuration** on the bucket
(S3 → bucket → Permissions → Cross-origin resource sharing):

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["POST", "GET"],
    "AllowedOrigins": ["https://citizenship-workspace-web.vercel.app"],
    "ExposeHeaders": ["ETag"]
  }
]
```

**This is not optional and its absence is invisible server-side.** The browser uploads
straight to S3, so without it every upload dies at preflight while the API logs stay
perfectly clean — presigning succeeded, and the API never learns the upload was refused.
Confirmed on this deployment: the same request with `mode: "no-cors"` reaches S3 and
returns an opaque response, while the ordinary request throws `Failed to fetch`. That pair
is how you tell a CORS refusal from a broken endpoint.

## Deployed URLs

| | |
|---|---|
| Web (Vercel) | `https://citizenship-workspace-web.vercel.app` |
| API (Railway) | `https://citizenship-workspace-production.up.railway.app` |

Recorded here rather than only in repository secrets because neither is a secret — they are
public addresses, and the API requires a bearer token for everything except `/health/*`.
Keeping them only in `SMOKE_BASE_URL` / `SMOKE_API_URL` means the one place they are
written down is the one place you cannot read them from. Both also appear as
`NEXT_PUBLIC_API_BASE_URL` (Vercel) and `CORS_ALLOW_ORIGINS` (Railway); if either moves,
all four need updating together.

**If you do use R2 later:** endpoint is `https://<account-id>.r2.cloudflarestorage.com`;
region must be `auto` (anything else fails as `SignatureDoesNotMatch`, which says nothing
about regions). Buckets are private by default — do not attach a public development URL or
a custom domain. Browser uploads go directly to the bucket, so a **CORS policy** allowing
the upload verb from the Vercel origin is required, or every upload fails preflight while
the API logs look perfectly healthy.

The bucket must be **private**, and the application does not create it: an application
whose credentials can create buckets is an application whose credentials can create a
*public* one. `ensure_bucket()` runs only under `ENVIRONMENT=local`/`docker`.
4. **Worker service** — New service from the **same repo**; under
   **Settings → Deploy → Start Command** set:
   ```
   uv run celery -A worker.celery_app.celery_app worker --beat --loglevel info
   ```
   Give it `DATABASE_URL`, `REDIS_URL` (same references), `ENVIRONMENT=production` and
   the storage variables from the section below. It needs no domain, and **no Clerk or
   upload-token variables**: it never verifies a token or signs one.

   **Set the variables before the first deploy, and confirm the running deployment has
   them** — not just the dashboard. Railway injects variables at deploy time, so a
   variable added afterwards is absent from the container until something redeploys. The
   check, from the service's **Console** tab, prints presence and no values:

   ```sh
   python -c "import os; print({k: k in os.environ for k in ['REDIS_URL','DATABASE_URL']})"
   ```

   This is not hypothetical bookkeeping. On the first M7 worker deploy the variables were
   listed in the dashboard and absent from the process; the worker fell back to
   `redis://localhost:6379/0`, retried for fifteen minutes, and reported **Online** the
   entire time while uploaded documents sat at `UPLOADED`. Two guards now make that loud
   rather than silent (`check_backing_services`, and `broker_connection_retry_on_startup`
   in `worker/celery_app.py`) — but `ENVIRONMENT` is what lets the first of them tell you
   *which* variable is missing, so it is worth setting for that alone.

   Then **Settings → Config-as-code**, set the path to **`railway.worker.json`**.

   That file exists because `railway.json` is the *API's* config and every service built
   from this repo reads it by default — including two settings a worker must not have:

   - `preDeployCommand: alembic upgrade head`, which would have the worker race the API
     on migrations. Two services running that at once on a migration-bearing deploy is
     how you get a half-applied schema.
   - `healthcheckPath: /health/ready`. A Celery worker serves no HTTP at all, so the check
     can never pass; Railway marks the deploy unhealthy and restarts it, and the symptom
     is a worker that looks like it is crashing when it is only failing a question it was
     never meant to be asked.

   Clearing those two fields in the dashboard is **not** reliably enough: config-as-code
   takes precedence over dashboard settings for the keys it defines, so the file would put
   them back. A second file is also the version-controlled answer — the difference between
   the two services is visible in the repo rather than living in one person's console.

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
