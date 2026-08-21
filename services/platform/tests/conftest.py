"""Shared test fixtures.

DB-backed tests are marked `integration` (they need the Postgres that `just up` or
CI provides). The schema is built once per session by running the real Alembic
migrations — tests exercise the same DDL that ships, not a `create_all` shortcut
that could silently drift from the migrations.
"""

import secrets
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.core.config import get_settings
from app.main import app
from app.requirements.models import CATALOG_TABLES
from app.shared.db import Base, get_db, get_sessionmaker
from app.shared.tenant import APP_ROLE, set_tenant

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


Api = Callable[[str], TestClient]


def as_user(user_id: str) -> CurrentUser:
    return CurrentUser(user_id=user_id, session_id="sess", email=None)


@pytest.fixture
def api(db_session: Session) -> Iterator[Api]:
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


# --- The non-superuser connection (ADR-0006 R1) ------------------------------
#
# The suite's ordinary connection is the database owner, `citizenship`, and a superuser
# bypasses RLS even under FORCE. That is why `set_tenant` can be deleted from a code path
# and leave every test green while, in a deployment, the policies reject its every write.
# It is not fixable by demoting `citizenship`: it is the initdb bootstrap superuser, and
# Postgres refuses to remove SUPERUSER from that role.
#
# So the fix is a second role. `app_test_login` is what the runtime role in ADR-0006's
# Option A would be — LOGIN, NOSUPERUSER, and holding the same table grants `app_rls`
# holds. The grants matter: with them, a query that forgets the tenant is filtered by the
# *policy* and returns nothing, which is the production behaviour worth pinning. Without
# them it would be refused for lack of privilege — also fail-closed, but a different
# mechanism, and a test that green-lights the wrong one is not evidence.
#
# Deliberately test-only. Nothing in `docker-compose.yml`, `ci.yml`, `railway.json` or
# `app/core/config.py` changes; the application still connects as the owner and still logs
# `rls.login_role_superuser` at boot. Closing R1 in production is a separate decision.
RLS_TEST_ROLE = "app_test_login"
# Generated per session and never written down. A constant would be a durable credential on
# whatever database the suite happened to run against, and `CREATE ROLE ... PASSWORD` is not
# redacted by `log_statement`, so a fixed one would sit in the server log verbatim.
RLS_TEST_PASSWORD = secrets.token_urlsafe(24)

# Creating a LOGIN role is the one thing this suite does that outlives the run, so it refuses
# to do it anywhere but a local database. The TRUNCATE teardown and the Alembic upgrade would
# already be catastrophic against a shared one, but both are loud and immediate; a login role
# with schema-wide DML is silent and permanent. `just test-be` inherits whatever DATABASE_URL
# the shell exports, which is exactly how a debugging session ends up pointed at a deployment.
LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres", "db"})


@pytest.fixture(scope="session")
def _rls_login_role(_schema: None) -> Iterator[str]:
    """Provision `app_test_login` for the session, as the owner, and drop it afterwards.
    Depends on `_schema` because the grants need the tables to exist."""
    host = make_url(get_settings().database_url).host
    if host not in LOCAL_DB_HOSTS:
        pytest.fail(
            f"refusing to create a login role on a non-local database ({host}). "
            "Point DATABASE_URL at a local Postgres before running the suite"
        )
    with get_sessionmaker()() as session:
        session.execute(
            text(
                f"DO $$ BEGIN "
                f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{RLS_TEST_ROLE}') THEN "
                f"CREATE ROLE {RLS_TEST_ROLE} LOGIN NOSUPERUSER "
                f"PASSWORD '{RLS_TEST_PASSWORD}'; END IF; END $$;"
            )
        )
        session.execute(text(f"GRANT USAGE ON SCHEMA public TO {RLS_TEST_ROLE}"))
        session.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                f"IN SCHEMA public TO {RLS_TEST_ROLE}"
            )
        )
        # The catalog is read-only for the request role (migration 0012), so it is read-only
        # here too — a test role holding privileges the runtime role lacks can only ever let
        # a test pass where production would be refused. This revoke covers the *direct*
        # grant made above; `app_rls` membership is what keeps the property true, because
        # migration 0012 revoked the same writes there. Neither mechanism is trusted:
        # `test_catalog_grants.py` asserts the outcome for both roles.
        for table in CATALOG_TABLES:
            session.execute(text(f"REVOKE INSERT, UPDATE, DELETE ON {table} FROM {RLS_TEST_ROLE}"))
        # Membership in app_rls, so `set_tenant`'s own `SET ROLE` still works from here.
        session.execute(text(f"GRANT {APP_ROLE} TO {RLS_TEST_ROLE}"))
        session.commit()

    yield RLS_TEST_ROLE

    with get_sessionmaker()() as session:
        # `DROP OWNED BY` clears the grants first; without it the DROP fails on dependent
        # privileges and the role outlives the run that created it.
        session.execute(text(f"REVOKE {APP_ROLE} FROM {RLS_TEST_ROLE}"))
        session.execute(text(f"DROP OWNED BY {RLS_TEST_ROLE}"))
        session.execute(text(f"DROP ROLE IF EXISTS {RLS_TEST_ROLE}"))
        session.commit()


@pytest.fixture(scope="session")
def rls_engine(_rls_login_role: str) -> Iterator[Engine]:
    """An engine on the same database as the app, connected as the non-superuser role.

    Mirrors the pool-checkin reset in `app.core.db` rather than sharing it: a connection
    that returns to the pool still carrying a role and a tenant is the bug that reset
    exists to prevent, and a test harness that skipped it would be less strict than the
    thing it is testing."""
    url = make_url(get_settings().database_url).set(
        username=RLS_TEST_ROLE, password=RLS_TEST_PASSWORD
    )
    engine = create_engine(url, pool_pre_ping=True)

    @event.listens_for(engine, "checkin")
    def _reset_tenant(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET app.user_id")
            dbapi_connection.commit()  # type: ignore[attr-defined]
        finally:
            cursor.close()

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def rls_sessionmaker(rls_engine: Engine) -> Callable[[], Session]:
    """`get_sessionmaker()`'s shape, on the non-superuser connection. Matches the app's
    settings — no autoflush, no expire-on-commit — so code under test behaves the same."""
    return sessionmaker(bind=rls_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def rls_api(db_session: Session, rls_sessionmaker: Callable[[], Session]) -> Iterator[Api]:
    """`api`, but every request runs on the non-superuser connection.

    `db_session` is still requested, and not incidentally: it owns the TRUNCATE teardown,
    which needs owner privilege the RLS role does not have. Requests here commit, so a
    test that arranges through `rls_api` and asserts through `db_session` sees the data —
    but the reverse is not true, because uncommitted work on the owner session belongs to
    a different transaction."""
    current = {"user_id": "user_a"}
    sessions: list[Session] = []

    def open_session() -> Iterator[Session]:
        session = rls_sessionmaker()
        sessions.append(session)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = open_session
    app.dependency_overrides[get_current_user] = lambda: as_user(current["user_id"])
    client = TestClient(app)

    def act_as(user_id: str) -> TestClient:
        current["user_id"] = user_id
        return client

    try:
        yield act_as
    finally:
        app.dependency_overrides.clear()
        for session in sessions:
            session.close()
