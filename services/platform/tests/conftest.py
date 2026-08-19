"""Shared test fixtures.

DB-backed tests are marked `integration` (they need the Postgres that `just up` or
CI provides). The schema is built once per session by running the real Alembic
migrations — tests exercise the same DDL that ships, not a `create_all` shortcut
that could silently drift from the migrations.
"""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.main import app
from app.requirements.models import CATALOG_TABLES
from app.shared.db import Base, get_db, get_sessionmaker
from app.shared.tenant import set_tenant

# Global reference data seeded by migrations, not per-test state: excluded from the per-test
# TRUNCATE so the catalog persists across the session (like the schema itself).
#
# Taken from the catalog module rather than listed again here. A second hand-written list
# silently wipes any catalog table added later — the seed vanishes after the first test and
# every read returns empty, which reads as a logic bug in whatever depends on it. That is
# exactly how `rule_composition_edges` first appeared to be broken.
_REFERENCE_TABLES = frozenset(CATALOG_TABLES)


@pytest.fixture(scope="session")
def _schema() -> Iterator[None]:
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")
    yield


@pytest.fixture
def db_session(_schema: None) -> Iterator[Session]:
    session = get_sessionmaker()()
    # RLS is on (migration 0004): direct-DB tests need a tenant to read/write case
    # rows. Default to user_a; API requests set their own tenant per request, and
    # cross-tenant tests set it explicitly. TRUNCATE (owner privilege) ignores RLS.
    set_tenant(session, "user_a")
    try:
        yield session
    finally:
        session.rollback()
        # TRUNCATE needs owner privilege; drop out of the app_rls role set by set_tenant.
        session.execute(text("RESET ROLE"))
        for table in reversed(Base.metadata.sorted_tables):
            # The requirement catalog is global reference data seeded once by migration
            # 0007, not per-test state — truncating it would wipe the seed after the first
            # test. Assessment rows still clear via CASCADE off the cases truncate.
            if table.name in _REFERENCE_TABLES:
                continue
            session.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))
        session.commit()
        session.close()


def as_user(user_id: str) -> CurrentUser:
    return CurrentUser(user_id=user_id, session_id="sess", email=None)


@pytest.fixture
def api(db_session: Session) -> Iterator[Callable[[str], TestClient]]:
    """Return `as(user_id) -> TestClient`, sharing the test's session and faking auth.

    Calling `as("user_b")` re-points the current user before returning the client,
    so a single test can act as two different users against the same data."""
    current = {"user_id": "user_a"}
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: as_user(current["user_id"])
    client = TestClient(app)

    def act_as(user_id: str) -> TestClient:
        current["user_id"] = user_id
        return client

    try:
        yield act_as
    finally:
        app.dependency_overrides.clear()
