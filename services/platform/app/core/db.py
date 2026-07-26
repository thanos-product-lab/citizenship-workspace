"""Database engine (sync SQLAlchemy 2) and a readiness probe.

The engine is a lazily-created module singleton so importing the app never opens
a connection — only the first real use does.
"""

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings

_log = structlog.get_logger()

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def check_database() -> bool:
    """True if a trivial query succeeds against Postgres."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        _log.warning("healthcheck.database_failed", error=str(exc)[:300])
        return False
    return True
