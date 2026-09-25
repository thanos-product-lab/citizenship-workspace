# Deployment

How the prototype is deployed, and how to set it up again from nothing.

| What | Where | Address |
|---|---|---|
| Web (Next.js) | Vercel | `https://citizenship-workspace-web.vercel.app` |
| API, worker, Postgres, Redis | Railway | `https://citizenship-workspace-production.up.railway.app` |
| Uploaded documents | AWS S3, private bucket in `eu-west-2` | the bucket's signed URLs |

Both Vercel and Railway deploy automatically from `main` (ADR-0003). The addresses are
not secrets: the API requires a sign-in token for everything except `/health/*`. They are
written down here because the smoke-test secrets are the only other place they live, and
secrets cannot be read back. Synthetic data only.

You need a Railway account, a Vercel account, an AWS account and the Clerk keys. Sections
A to D are the setup order; E covers storage and F covers local development.

## Things that fail silently

Most deployment mistakes here produce a service that looks healthy. Check these first when
something does not work.

| Symptom | Cause | See |
|---|---|---|
| Every upload fails, API logs are clean | The bucket has no CORS policy for the Vercel origin | E |
| The review screen shows an empty box instead of the document | `STORAGE_ORIGIN` on Vercel does not match the signed URL's host | B |
| Documents stay at "Not read yet" and deleted files are never purged | The worker is running without `--beat` | A.4 |
| The worker says Online but nothing is processed | Variables were added after its last deploy, so the process never got them | A.4 |
| Uploads fail on a deployed API | `STORAGE_ENDPOINT_URL` is unset and defaults to a local MinIO | E |

## A. Railway: API, worker, Postgres, Redis

1. **New Project → Deploy from GitHub repo**, and pick this repo. It builds from
   `infra/docker/platform.Dockerfile` using `railway.json`, with `/health/ready` as the
   health check.
2. **Add Postgres** and **Add Redis** (New → Database) in the same project.
3. **API service variables.** Use Railway's reference variables for the database and cache.

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (the app rewrites the scheme itself) |
   | `REDIS_URL` | `${{Redis.REDIS_URL}}` |
   | `ENVIRONMENT` | `production` |
   | `CLERK_ISSUER` | `https://<your-instance>.clerk.accounts.dev` |
   | `CORS_ALLOW_ORIGINS` | the Vercel URL (fill in after B) |
   | `CLERK_AUTHORIZED_PARTIES` | the Vercel URL, optional, must match exactly |
   | `UPLOAD_TOKEN_SECRET` | 32 or more random characters |
   | `OPENAI_API_KEY` | the provider key |
   | storage variables | see E |

   Generate the secret with
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

   Outside local development the API **refuses to start** without `UPLOAD_TOKEN_SECRET` or
   `OPENAI_API_KEY`:
   - The upload secret signs the token that carries a document's storage key (ADR-0019).
     Without it each process makes up its own key, so with two instances, uploads fail at
     random with errors that look like tampering.
   - Without the model key, every upload would fail at the reading step while
     `/health/ready` still answers 200. Refusing to start names the missing variable
     instead.

   Then **Settings → Networking → Generate Domain** to get the API URL. Set the variables
   before the first deploy, because the health check needs Postgres and Redis.

4. **Worker service.** Add a second service from the same repo.
   - **Start command** (Settings → Deploy):
     ```
     uv run celery -A worker.celery_app.celery_app worker --beat --loglevel info
     ```
     `--beat` runs the scheduler, which drives the outbox relay (the job that turns saved
     events into work). Without it nothing is read or purged, and nothing on screen says
     so. Keep the worker at **one replica** while `--beat` is on; if you ever need more
     workers, move beat into its own service.
   - **Config file** (Settings → Config-as-code): `railway.worker.json`. The default
     `railway.json` belongs to the API. It runs migrations before deploy, which would race
     the API's, and checks `/health/ready`, which a worker never serves. Clearing those in
     the dashboard is not enough, because the config file wins.
   - **Variables:** `DATABASE_URL`, `REDIS_URL`, `ENVIRONMENT=production`,
     `OPENAI_API_KEY` and the storage variables. No Clerk or upload-token variables; the
     worker never checks or signs a token. It also refuses to start without the model key.
   - **Check the running process has them**, not only the dashboard. Railway injects
     variables at deploy time, so one added later is missing until the next deploy. From
     the service's Console tab (prints only whether each is set):
     ```sh
     python -c "import os; print({k: k in os.environ for k in ['REDIS_URL','DATABASE_URL']})"
     ```
     This happened once: the worker ran against a Redis that did not exist for fifteen
     minutes while showing Online. It now fails at startup instead.

5. **Migrations run on every API deploy.** `railway.json` runs `uv run alembic upgrade head`
   before the new version takes traffic, so a failed migration fails the deploy. This also
   creates the `app_rls` database role (ADR-0006). To run them by hand:
   ```
   railway run --service <api-service> uv run alembic upgrade head
   ```

## B. Vercel: web

1. **Add New → Project**, and import this repo.
2. **Root Directory** = `apps/web`. The Next.js preset is detected, and the pnpm workspace
   installs from the repo root.
3. **Environment variables**, for **Production and Preview** (a preview build is a
   production build too):

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_...` |
   | `CLERK_SECRET_KEY` | `sk_...` |
   | `NEXT_PUBLIC_API_BASE_URL` | the Railway API URL from A.3 |
   | `STORAGE_ORIGIN` | the scheme and host of the bucket's signed URLs (below) |

4. **Deploy**, and note the Vercel URL.

### Getting `STORAGE_ORIGIN` right

The review screen shows the user's document in a frame, and `apps/web/next.config.ts` only
allows frames from this origin. A wrong value gives no error, just an empty box. If it is
unset, the build prints a warning and the preview is refused.

It is usually **not** the same as `STORAGE_ENDPOINT_URL`: S3 puts the bucket name in the
host, so an endpoint of `https://s3.eu-west-2.amazonaws.com` produces URLs on
`https://your-bucket.s3.eu-west-2.amazonaws.com`. Read it off a real URL rather than working
it out:

```
GET /api/v1/cases/{case_id}/evidence/{evidence_item_id}/content
→ { "url": "https://your-bucket.s3.eu-west-2.amazonaws.com/cases/…?X-Amz-…", … }
```

Use the scheme and host only, with no path or trailing slash. Locally it defaults to
`http://localhost:9000`.

## C. Connect the origins

- Set the API's `CORS_ALLOW_ORIGINS` (and `CLERK_AUTHORIZED_PARTIES`, if used) to the
  Vercel URL, and redeploy the API.
- In Clerk, add the Vercel domain to the allowed origins. The Clerk development instance is
  fine for a demo; a public launch would need a production instance on a custom domain.

If the Vercel or Railway address ever changes, update the table at the top,
`NEXT_PUBLIC_API_BASE_URL`, `CORS_ALLOW_ORIGINS`, the smoke secrets, and the bucket's CORS
policy together.

## D. Smoke test

- Add the repo secrets `SMOKE_BASE_URL` (Vercel URL) and `SMOKE_API_URL` (Railway API URL),
  then run **Actions → Smoke → Run workflow**. It also runs daily.
- Or locally:
  ```
  pnpm --filter @cw/web exec playwright install chromium
  SMOKE_BASE_URL=<vercel-url> SMOKE_API_URL=<railway-api-url> just e2e
  ```

It checks that the web app loads, that signed-out users are sent to sign-in, and that the
API health endpoint answers.

## E. Object storage (S3)

Railway has no object storage, so documents go to a private S3 bucket. Until it exists the
app runs but every upload fails.

**Create the bucket yourself**, with Block all public access left on. The app only creates
buckets locally, on purpose: credentials that can create a bucket can create a public one.

**Give the app an IAM user with exactly these permissions** (`ListBucket` is for the
startup check; `CreateBucket` is deliberately missing):

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

**Add a CORS policy** on the bucket (Permissions → Cross-origin resource sharing). The
browser uploads straight to S3, so without this every upload fails in the browser while the
API logs look fine:

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

**Set these on both the API and the worker:**

| Variable | Value |
|---|---|
| `STORAGE_ENDPOINT_URL` | `https://s3.<region>.amazonaws.com`, set explicitly: unset means `http://localhost:9000` |
| `STORAGE_BUCKET` | the bucket name |
| `STORAGE_ACCESS_KEY` / `STORAGE_SECRET_KEY` | the IAM user's keys |
| `STORAGE_REGION` | the bucket's region |

Leave `STORAGE_PUBLIC_ENDPOINT_URL` unset in deployment (see F).

### Checking another provider

Uploads use a signed **POST policy**, because that lets the store itself refuse a file over
the size limit. Not every "S3-compatible" provider supports POST uploads. Before switching,
run the storage tests against the candidate:

```bash
cd services/platform
CW_EXPECT_MINIO=1 \
STORAGE_ENDPOINT_URL=<endpoint> STORAGE_BUCKET=<bucket> \
STORAGE_ACCESS_KEY=<key> STORAGE_SECRET_KEY=<secret> STORAGE_REGION=<region> \
uv run pytest tests/evidence/test_storage_minio.py -q
```

Seven passes means it works. AWS S3 passed all seven on 28 August 2026. **Cloudflare R2
fails**: it answers POST uploads with `501 Not Implemented`. It would work only if uploads
moved to signed PUT requests, which is a change to the size control and would need its own
ADR.

## F. Local development: two addresses for MinIO

`docker-compose.yml` gives the API two storage addresses, and both are needed:

```yaml
STORAGE_ENDPOINT_URL:        http://minio:9000      # the API, inside the docker network
STORAGE_PUBLIC_ENDPOINT_URL: http://localhost:9000  # the browser, from your machine
```

Without the second, signed URLs name `minio:9000`, which the browser cannot reach, so
browser uploads fail while the tests (which upload from the server) still pass. It is a
second S3 client rather than a text replacement, because the host is part of the signature.
In deployment both reach S3 at the same address, so the second one stays unset.
