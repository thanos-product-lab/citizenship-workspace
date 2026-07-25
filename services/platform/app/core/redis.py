"""Redis client (sync) and a readiness probe."""

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

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
    except RedisError:
        return False
