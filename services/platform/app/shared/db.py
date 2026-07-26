"""ORM declarative base, session factory, and the `get_db` request dependency.

The sessionmaker is a lazily-created module singleton bound to the shared engine
(`app.core.db`), so importing the app never opens a connection. `expire_on_commit`
is False so a committed aggregate stays readable without a reload; server-defaulted
columns are populated via RETURNING on flush.
"""

from collections.abc import Iterator

from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.db import get_engine


class Base(DeclarativeBase):
    """Declarative base for every ORM model in the monolith."""


_sessionmaker: sessionmaker[Session] | None = None


def get_sessionmaker() -> sessionmaker[Session]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False
        )
    return _sessionmaker


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session. Commit is owned by the unit of work,
    never by this dependency — a read path that never commits leaves no trace."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
