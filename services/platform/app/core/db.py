"""Database engine (sync SQLAlchemy 2) and a readiness probe.

The engine is a lazily-created module singleton so importing the app never opens
a connection — only the first real use does.
"""

import structlog
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings

_log = structlog.get_logger()

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)

        @event.listens_for(_engine, "checkin")
        def _reset_tenant(dbapi_connection: object, _record: object) -> None:
            # Clear the RLS tenant when a connection returns to the pool, so a reused
            # connection never carries a previous request's tenant into a query that
            # forgot to set one — that surfaces as "no rows" (fail closed), not a leak.
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            try:
                cursor.execute("RESET ROLE")  # drop back from app_rls to the owner
                cursor.execute("RESET app.user_id")
                # Commit so the connection returns to the pool idle, not mid-transaction
                # (psycopg is not autocommit; a dangling txn breaks the next checkout).
                dbapi_connection.commit()  # type: ignore[attr-defined]
            finally:
                cursor.close()

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


def connection_is_superuser() -> bool | None:
    """Whether the DB login role is a superuser (which bypasses RLS even under FORCE).
    None if it can't be determined. Used by the boot check to refuse to run a deployed
    environment without the RLS defence-in-depth backstop (ADR-0006, R1)."""
    try:
        with get_engine().connect() as conn:
            return conn.execute(text("SHOW is_superuser")).scalar() == "on"
    except SQLAlchemyError as exc:
        _log.warning("rls.superuser_check_failed", error=str(exc)[:200])
        return None
