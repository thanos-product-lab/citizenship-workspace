"""Application settings, loaded from the environment (12-factor)."""

from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
