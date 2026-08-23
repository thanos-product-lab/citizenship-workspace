"""Application settings, loaded from the environment (12-factor)."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    storage_bucket: str = "citizenship-evidence"
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_region: str = "us-east-1"

    # Short, per threat model §12. Long enough for a browser to follow a redirect,
    # too short to be worth passing on. Presigned URLs cannot be revoked, so this
    # is the whole of the bound on an issued URL's life (ADR-0018).
    storage_presign_ttl_seconds: int = 60

    # Hard ceiling on an uploaded file. Enforced twice: declared size at presign
    # (cheap, pre-upload) and actual size at completion (authoritative — a client
    # controls what it declares, not what the store reports).
    max_upload_bytes: int = 20 * 1024 * 1024

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
