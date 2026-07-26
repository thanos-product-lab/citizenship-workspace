"""Application settings, loaded from the environment (12-factor)."""

from functools import lru_cache

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
