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

    `extraction_runs` is named alongside them rather than relying on `CASCADE`, because
    it references `model_runs` (ADR-0025) and Postgres refuses to truncate a table
    something points at. Listing it is a sentence about what this fixture wipes;
    `CASCADE` would be a standing instruction to wipe whatever happens to point at the
    ledger next, which in a later slice could be a table a test meant to keep.
    """
    yield
    with get_sessionmaker()() as session:
        session.execute(text("TRUNCATE TABLE extraction_runs, model_runs, ai_daily_spend"))
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
