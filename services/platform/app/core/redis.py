"""Redis client (sync) and a readiness probe."""

import structlog
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

_log = structlog.get_logger()

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(get_settings().redis_url)
    return _client


def check_redis() -> bool:
    """True if Redis answers PING."""
    try:
        return bool(get_redis().ping())
    except RedisError as exc:
        _log.warning("healthcheck.redis_failed", error=str(exc)[:300])
        return False
