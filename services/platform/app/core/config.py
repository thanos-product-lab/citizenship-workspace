"""Application settings, loaded from the environment (12-factor)."""

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Environments where a localhost backing service is the arrangement rather than a
#: defect. Shared with `check_upload_secret`, which draws the same line for the same
#: reason: what is a convenience on one machine is a fault on a platform.
LOCAL_ENVIRONMENTS = frozenset({"local", "docker", "test"})

#: Hosts that resolve to the container itself. A backing service here means the URL was
#: never supplied and the default below is what is in force.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "local"
    service_name: str = "citizenship-platform"

    # Sync drivers: psycopg3 for Postgres, redis-py for Redis.
    database_url: str = "postgresql+psycopg://citizenship:citizenship@localhost:5432/citizenship"
    redis_url: str = "redis://localhost:6379/0"

    # Clerk auth. Empty by default so the app imports without secrets (tests,
    # OpenAPI export, CI); verification fails closed when unconfigured.
    clerk_issuer: str = ""
    clerk_jwks_url: str = ""
    clerk_audience: str | None = None
    # Comma-separated allow-list of `azp` values (e.g. "http://localhost:3000").
    clerk_authorized_parties: str = ""

    # Comma-separated browser origins allowed to call the API (CORS).
    cors_allow_origins: str = "http://localhost:3000"

    # Private object storage for evidence files. S3-compatible: MinIO locally,
    # any S3 in deployment. `memory` selects the in-process fake, which exists so
    # the seed and the non-storage test suites do not require a running MinIO —
    # it asserts behaviour only and must never be used to claim a security
    # property (SECURITY_AND_PRIVACY_THREAT_MODEL §12).
    storage_backend: Literal["s3", "memory"] = "s3"
    storage_endpoint_url: str = "http://localhost:9000"
    # The address the *browser* reaches the store at, when it differs from the one the
    # server uses. Unset means they are the same, which is the deployed case and the one
    # to keep: a second endpoint is a second thing that can be wrong. Local compose sets
    # it because the API reaches MinIO over the docker network at `minio:9000`, which
    # does not resolve on the host.
    storage_public_endpoint_url: str = ""
    storage_bucket: str = "citizenship-evidence"
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_region: str = "us-east-1"

    # Short, per threat model §12. Long enough for a browser to follow a redirect,
    # too short to be worth passing on. Presigned URLs cannot be revoked, so this
    # is the whole of the bound on an issued URL's life (ADR-0018).
    storage_presign_ttl_seconds: int = 60

    # HMAC key for the signed upload token that carries a storage key back from the
    # client (app/evidence/upload_token.py). Unset means a per-process key, which is
    # fine for one API and wrong for several — `check_upload_secret` warns at boot,
    # the same shape as the superuser-login-role warning.
    upload_token_secret: str = ""

    # Hard ceiling on an uploaded file. Enforced twice: declared size at presign
    # (cheap, pre-upload) and actual size at completion (authoritative — a client
    # controls what it declares, not what the store reports).
    max_upload_bytes: int = 20 * 1024 * 1024

    # --- AI provider -------------------------------------------------------------
    # Empty by default so the app imports without secrets, the same shape as Clerk
    # above. `check_ai_configuration` refuses to boot deployed without it.
    openai_api_key: str = ""
    ai_provider: Literal["openai", "fake"] = "openai"

    # One provider call. 5x the P95 and 4.6x the slowest single call the spike
    # observed (AI_SPIKE_FINDINGS §4) — generous for a slow-but-honest response.
    ai_request_timeout_seconds: float = 15.0
    # The bound that actually matters. A per-request timeout bounds one call; a task
    # makes several, and it is the *task* Celery kills. 45s leaves 15s of headroom
    # under `task_soft_time_limit = 60`, so a hung provider fails here with a state
    # to show for it rather than by the worker being killed mid-write.
    ai_task_deadline_seconds: float = 45.0
    # Attempts per invocation, terminal provider errors excluded (see provider.py).
    ai_max_attempts: int = 3

    # USD per day across the whole deployment, all capabilities, all tenants.
    # Deliberately low: at the spike's ~$0.00026 per document this is thousands of
    # documents, so it does not bound ordinary use — it bounds a loop. Reaching it
    # is a hard stop with a user-visible reason, never a silent skip.
    ai_daily_spend_ceiling_usd: float = 5.0

    # Capability invocations one case may make per rolling 24 hours. The deployment-wide
    # ceiling above bounds the *bill*; this bounds one case's share of it, which is a
    # different control. Without it, a retry loop on a single document is 3 billable
    # requests every 30 seconds — ~8,600 a day — and the first tenant to run one
    # exhausts the shared ceiling, putting every other user's documents into
    # REFUSED_NO_BUDGET until midnight. Generous against real use: the canonical demo
    # case has twelve documents.
    ai_case_daily_call_limit: int = 200

    # Capability invocations one *user* may make per rolling 24 hours, across every case
    # they own. The case limit alone cannot bound a user, because nothing bounds how many
    # cases a person opens: 200 per case times an unbounded number of cases is unbounded.
    #
    # The three limits are a ladder, and the numbers are chosen so they compose. At the
    # ~$0.00026 per document the M8 spike measured, the $5 deployment ceiling is roughly
    # 19,000 calls; 500 is about 2.6% of it, so one account cannot deny the service to
    # everyone else, and a person with three active cases is still far from touching it.
    ai_user_daily_call_limit: int = 500

    # Cases one user may hold at once. The last rung of the ladder above: those two bound
    # how much analysis a case and a user may buy, and this bounds how many workspaces a
    # user can open to buy it from — along with the storage, the processing, and the rows
    # in every case-scoped table that come with each one.
    #
    # Ten is deliberately far above what the product is for. A case is one intended
    # application, and someone weighing two application dates uses the simulator rather
    # than a second case, so nobody reaches this by working normally. A limit people meet
    # in ordinary use is a workflow constraint wearing a safety label.
    max_cases_per_user: int = 10

    # Shared secret for `POST /health/ai-probe`, which makes a real (tiny) model call
    # so the deployed smoke can tell a working key from a well-formed one. Unset
    # disables the endpoint entirely — an unauthenticated route that spends money is
    # not something to leave on by default.
    ai_probe_secret: str = ""

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, value: str) -> str:
        # Managed Postgres (Railway/Fly) hands out a bare postgres:// or
        # postgresql:// URL; SQLAlchemy needs the psycopg driver named explicitly
        # (and rejects the bare postgres:// scheme outright).
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @property
    def resolved_jwks_url(self) -> str:
        if self.clerk_jwks_url:
            return self.clerk_jwks_url
        if self.clerk_issuer:
            return f"{self.clerk_issuer.rstrip('/')}/.well-known/jwks.json"
        return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _loopback_host(url: str) -> bool:
    """Whether `url` points at this container, without ever re-raising the URL.

    `urlsplit` is not total. CPython validates the netloc under NFKC and raises
    `ValueError` **with the netloc inlined in the message** — password included — for any
    host or credential containing a character that changes under that normalisation. An
    uncaught parse here would therefore print a connection string into a crash trace on a
    platform log, which is precisely what the guard below refuses to do deliberately. A
    URL that cannot be parsed is a misconfiguration to name by variable like any other,
    not one to quote.
    """
    try:
        return (urlsplit(url).hostname or "") in _LOOPBACK_HOSTS
    except ValueError:
        # Unparseable, so its host is unknowable — treat it as configured and let the
        # driver fail on it. Reporting it as loopback would name the wrong fault.
        return False


def check_backing_services() -> None:
    """Refuse to boot pointed at a Postgres or Redis that is this container.

    The defaults above are deliberate conveniences: a developer clones the repo, runs
    `just up`, and nothing needs configuring. Deployed, the same defaults are the worst
    possible failure, because they are *plausible*. A Celery worker whose broker never
    arrives does not crash — it retries, politely, forever, reporting itself healthy the
    whole time. That is not hypothetical: the worker ran for fifteen minutes against
    `redis://localhost:6379/0` while the API accepted uploads that could never be
    processed, and nothing in the system could say so. Documents sat at UPLOADED and the
    only place the truth existed was a log nobody had reason to open.

    So a loopback host outside local development is treated as a missing variable rather
    than a deliberate choice, which it always is: nothing deploys its own database inside
    the application container.

    **This guard is the second line, not the first.** It can only fire when `ENVIRONMENT`
    is itself set, and an environment that forgot `REDIS_URL` can equally have forgotten
    `ENVIRONMENT` — in which case this reads `local` and stays quiet, which is exactly the
    silence it exists to break. The guard that does not depend on getting any variable
    right is `broker_connection_retry_on_startup = False` in `worker/celery_app.py`: an
    unreachable broker kills the process whatever the environment claims to be. This one
    adds the *named* failure when the platform is configured enough to say so.
    """
    settings = get_settings()
    if settings.environment in LOCAL_ENVIRONMENTS:
        return

    misconfigured = [
        name
        for name, url in (
            ("DATABASE_URL", settings.database_url),
            ("REDIS_URL", settings.redis_url),
        )
        if _loopback_host(url)
    ]
    if not misconfigured:
        return

    # Name the variables and the environment, never the URLs: a connection string carries
    # a password, and a boot failure is one of the most widely-read log lines there is.
    raise RuntimeError(
        f"{', '.join(misconfigured)} still resolve(s) to this container outside local "
        f"development, which means the variable never reached the process. Observed "
        f"ENVIRONMENT={settings.environment!r}. On a platform this is usually a "
        f"reference that did not resolve, a variable set on the wrong service, or a "
        f"deployment that predates it — check that the running deployment has it, not "
        f"just the dashboard."
    )
