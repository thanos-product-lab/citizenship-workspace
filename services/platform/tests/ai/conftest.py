"""Shared arrangement for the AI boundary tests."""

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.shared.db import get_sessionmaker


@pytest.fixture
def ledger(db_session: Session) -> Callable[[], Session]:
    """Bind the ledger to the test's own session.

    `invoke` opens its own session in production precisely so the spend survives the
    caller's rollback (see `ai/service.py`). That is the behaviour under test almost
    everywhere else, but it makes assertions awkward: a separate connection cannot see
    the test transaction's rows. Injecting the test's session keeps the assertions
    honest about *what* was written; `test_ledger_isolation.py` covers the separation
    itself against real connections.
    """

    def _make() -> Session:
        return db_session

    return _make


@pytest.fixture(autouse=True)
def clear_ledger() -> Iterator[None]:
    """Empty both ledger tables after every test in this package.

    The root `db_session` fixture already truncates them — but only for tests that ask
    for `db_session`. The route tests do not: they drive the app, which opens its own
    connection and *commits*, so their rows outlive the test and the next assertion
    that expects to find exactly one `ModelRun` finds three. That is how this fixture
    came to exist.

    `TRUNCATE` as the table owner, not `DELETE`: migration 0025 revokes DELETE on both
    tables from `app_rls`, because a ledger the request role can erase is not a ledger.

    **`CASCADE`, after arguing against it and being wrong twice.** An earlier version
    named the referencing tables explicitly, reasoning that a list is "a sentence about
    what this fixture wipes" while `CASCADE` would be "a standing instruction to wipe
    whatever happens to point at the ledger next". That sounded careful and broke on the
    next two slices in a row: `extraction_runs` in slice 2, then `extracted_claims` in
    3a, each time producing an `E` on every test in this package and a stale list nobody
    would think to update.

    The principle was wrong on its merits, not just inconvenient. A row that references a
    ledger row is meaningless once that row is gone — a claim whose extraction run does
    not exist is an orphan, not data a test meant to keep. `CASCADE` says exactly that,
    and says it once rather than needing a maintainer to notice each new foreign key.
    """
    yield
    with get_sessionmaker()() as session:
        session.execute(text("TRUNCATE TABLE model_runs, ai_daily_spend CASCADE"))
        session.commit()


@pytest.fixture
def ai_settings() -> Settings:
    """Settings with a fake provider and a small ceiling, so a test can reach it."""
    return Settings(
        environment="test",
        ai_provider="fake",
        ai_request_timeout_seconds=5.0,
        ai_task_deadline_seconds=30.0,
        ai_max_attempts=3,
        ai_daily_spend_ceiling_usd=1.0,
    )
