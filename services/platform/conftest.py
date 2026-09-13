"""Root conftest — it decides which database the suite runs against.

This file exists for its import-time side effect and for nothing else. pytest loads
conftest files from the rootdir down, so this one runs before `tests/conftest.py` is
imported and long before anything calls `get_settings()`. That ordering is the whole
reason it is a separate file rather than a few more lines at the top of the suite's own
conftest.
"""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings


def isolate_the_test_database() -> None:
    """Point the suite at its own database, creating it if it is not there.

    Every DB-backed test truncates. Until this existed the suite truncated the same
    Postgres `docker compose` serves the running app, so `just test-be` wiped the
    development database — three times in one M8 session, once destroying a case that was
    mid-walkthrough. The control in place was a habit ("reseed afterwards", "do not run
    the suite while driving the browser"), and a habit is the wrong control for an
    irreversible action: it holds until the one time it does not.

    Derived from the configured URL rather than hard-coded, so CI, compose and a
    developer's machine each get a test database beside whatever they already use.
    `TEST_DATABASE_NAME` overrides the derived name; setting it to the configured name is
    how you deliberately opt out.

    **Read through `Settings`, not `os.environ`.** `DATABASE_URL` usually lives in
    `services/platform/.env`, which is invisible to the environment — deriving from
    `os.environ` alone would leave exactly the developers this protects still pointed at
    their own database. Writing the result back to `os.environ` is what makes it stick: an
    environment variable outranks the env file, so every later `Settings()` — the app's,
    Alembic's, the worker context's — resolves to the same test database.

    A second consequence, and not a small one: a running worker is pointed at the
    development database, so it can no longer relay rows this suite writes. The suite no
    longer has to be run with the worker stopped, which is what produced the M8 gate's
    silent-upload finding — a worker stopped for a test run and left stopped.
    """
    configured = make_url(Settings().database_url)
    if configured.database is None:
        return

    target = os.environ.get("TEST_DATABASE_NAME") or f"{configured.database}_test"
    if target == configured.database:
        return

    os.environ["DATABASE_URL"] = configured.set(database=target).render_as_string(
        hide_password=False
    )

    # `CREATE DATABASE` cannot run inside a transaction, hence AUTOCOMMIT, and it is
    # issued against the maintenance database because you cannot create a database from a
    # connection to the one being created. The name is an identifier, so it cannot be a
    # bound parameter; it comes from configuration rather than from a request, and is
    # quoted anyway because "it is not user input today" is not a property that stays true
    # by itself.
    quoted = '"' + target.replace('"', '""') + '"'
    admin = create_engine(
        configured.set(database="postgres"), isolation_level="AUTOCOMMIT", pool_pre_ping=True
    )
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target}
            ).scalar()
            if exists is None:
                connection.execute(text(f"CREATE DATABASE {quoted}"))
    except SQLAlchemyError:
        # Postgres is unreachable. Deliberately not fatal: the tests that do not need a
        # database should still run, and the ones that do already fail loudly at `_schema`
        # when the migrations cannot connect. Failing here would turn "Postgres is down"
        # into "the suite cannot be collected", which says strictly less.
        pass
    finally:
        admin.dispose()


isolate_the_test_database()
