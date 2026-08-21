"""The gap CI structurally could not see, closed — ADR-0006 R1.

Every other RLS test in this repo, including the ones in `test_rls_matrix.py`, reaches
enforcement the same way the application does: `set_tenant` issues `SET ROLE app_rls`,
and switching into a non-superuser role drops the owner's bypass. That proves the
policies are correct. It cannot prove the *call* happens, because the connection
underneath is a superuser — so a code path that never sets a tenant reads and writes
everything, and nothing goes red.

That is not hypothetical. It is what happened at M6: `_record_failed_run` opens its own
session, and deleting its `set_tenant` line left the entire suite green while every
failure record in a deployed environment would have been refused by policy — silently,
because the recovery swallows and logs.

These tests connect as `app_test_login` (see `tests/conftest.py`): LOGIN, NOSUPERUSER,
same grants as `app_rls`. On that connection RLS applies to the login role itself, so
forgetting the tenant fails closed here exactly as it would in production.
"""

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.cases.domain import ApplicationCase
from app.shared.tenant import set_tenant
from tests.conftest import RLS_TEST_ROLE, Api

from .conftest import CASE_SCOPED_TABLES, count_rows

pytestmark = pytest.mark.integration


def test_the_test_role_is_not_a_superuser(rls_sessionmaker: Callable[[], Session]) -> None:
    """The premise of every other test in this file. A superuser here would make them all
    pass while testing nothing — which is precisely the condition being fixed."""
    with rls_sessionmaker() as session:
        assert session.execute(text("SELECT current_user")).scalar_one() == RLS_TEST_ROLE
        assert session.execute(text("SHOW is_superuser")).scalar_one() == "off"


def test_a_session_that_never_sets_a_tenant_sees_nothing(
    seeded_case: str, rls_sessionmaker: Callable[[], Session]
) -> None:
    """The regression the owner connection cannot detect: no `set_tenant`, no rows.

    On the owner connection every one of these counts is non-zero, which is why this test
    has to live on its own engine."""
    with rls_sessionmaker() as session:
        leaked = [t for t in CASE_SCOPED_TABLES if count_rows(session, t) > 0]
        assert leaked == [], f"readable without a tenant on a non-superuser connection: {leaked}"


def test_a_session_that_never_sets_a_tenant_cannot_write(
    seeded_case: str, rls_sessionmaker: Callable[[], Session]
) -> None:
    """And the write half. `WITH CHECK` sees a NULL `app.user_id` and refuses — the
    mechanism that would have rejected M6's failure record."""
    with rls_sessionmaker() as session:
        session.add(ApplicationCase.create(owner_user_id="user_a", title="no tenant"))
        with pytest.raises(ProgrammingError) as raised:
            session.flush()
        assert "row-level security policy" in str(raised.value)
        session.rollback()


def test_setting_the_tenant_restores_access_on_the_same_connection(
    seeded_case: str, rls_sessionmaker: Callable[[], Session]
) -> None:
    """The other half of the pin: the rows are invisible because of the missing tenant,
    not because the role cannot reach the table at all. A `permission denied` would also
    make the test above pass, and would be testing the wrong mechanism."""
    with rls_sessionmaker() as session:
        assert count_rows(session, "cases") == 0
        set_tenant(session, "user_a")
        assert count_rows(session, "cases") == 1
        set_tenant(session, "user_b")
        assert count_rows(session, "cases") == 0


def test_a_read_only_request_works_end_to_end_on_the_non_superuser_connection(
    seeded_case: str, rls_api: Api
) -> None:
    """The request path — auth, `get_tenant_session`, the ownership check, the query —
    over a connection with no bypass. A request that only reads never commits, so it
    holds one connection for its whole life and keeps the tenant it established."""
    assert rls_api("user_a").get(f"/api/v1/cases/{seeded_case}").status_code == 200
    assert len(rls_api("user_a").get("/api/v1/cases").json()) == 1

    # Unowned and absent are one state, and on this connection RLS is what makes that
    # true, not only the application check.
    assert rls_api("user_b").get(f"/api/v1/cases/{seeded_case}").status_code == 404
    assert rls_api("user_b").get("/api/v1/cases").json() == []


@pytest.mark.xfail(
    strict=True,
    reason="A command that commits mid-request loses its tenant; see the docstring. "
    "Remove this marker in the same change that fixes it.",
)
def test_a_command_keeps_its_tenant_across_a_mid_request_commit(rls_api: Api) -> None:
    """**A defect in application code, found by this harness rather than assumed away.**

    `set_tenant` binds the role and the tenant at *session* scope — `SET ROLE` and
    `set_config(..., is_local=False)` — deliberately, because the unit of work commits in
    the middle of a request and `SET LOCAL` would not survive that (ADR-0006, deviating
    from ADR-0005). But SQLAlchemy releases the connection back to the pool when a
    session's transaction ends, and `app.core.db` resets role and tenant on checkin. So
    the next statement checks out a connection with neither:

        set_tenant(session, "user_a")   -> (app_rls, 'user_a')
        session.commit()                -> connection returns to the pool, reset fires
        session.execute(...)            -> (app_test_login, '')   tenant gone

    `create_case` does exactly this: `uow.commit()`, then `session.refresh(case)` to load
    the server-defaulted timestamps. The refresh finds no row and raises
    `InvalidRequestError`, so the very first command in the product fails.

    On the owner connection this is invisible — a superuser bypasses RLS, so the
    tenantless read succeeds and nobody notices. It is the same shape as the M6 bug and
    it is why this file exists. It also means the non-superuser runtime role of ADR-0006
    R1 Option A cannot be adopted until it is fixed: every write command would 500.

    The fix is to re-establish the tenant per transaction rather than per session —
    remember the user id on `Session.info` and re-apply it from an `after_begin`
    listener — which is application code, touches every request, and belongs in its own
    reviewed change rather than in a test slice.
    """
    created = rls_api("user_a").post("/api/v1/cases", json={"title": "A's case"})
    assert created.status_code == 201
