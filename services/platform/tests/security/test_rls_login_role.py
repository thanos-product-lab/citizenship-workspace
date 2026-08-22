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
from app.shared.tenant import APP_ROLE, clear_tenant, set_tenant
from tests.conftest import RLS_TEST_ROLE, Api

from .conftest import CASE_SCOPED_TABLES, SUPPORTED_ANSWERS, count_rows

pytestmark = pytest.mark.integration


def test_the_test_role_is_not_a_superuser(rls_sessionmaker: Callable[[], Session]) -> None:
    """The premise of every other test in this file. A superuser here would make them all
    pass while testing nothing — which is precisely the condition being fixed."""
    with rls_sessionmaker() as session:
        assert session.execute(text("SELECT current_user")).scalar_one() == RLS_TEST_ROLE
        assert session.execute(text("SHOW is_superuser")).scalar_one() == "off"
        # BYPASSRLS is a separate attribute and reports `is_superuser = off`. The role is
        # created `IF NOT EXISTS`, so a pre-existing `app_test_login` carrying BYPASSRLS
        # would be reused silently and every test below would pass while testing nothing —
        # the exact failure class this file exists to close.
        assert (
            session.execute(
                text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
            ).scalar_one()
            is False
        )


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
        # First line only: SQLAlchemy renders `[parameters: ...]` into `str(exc)`, and a
        # failure message that carries a row's column values puts them in the CI log.
        # Synthetic today, but this is the habit, not the fixture, that has to be right.
        assert "row-level security policy" in str(raised.value).splitlines()[0]
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


def test_a_command_keeps_its_tenant_across_a_mid_request_commit(rls_api: Api) -> None:
    """The regression test for the defect this harness was built to find.

    `set_tenant` used to bind role and tenant to the *connection* and call that
    session-scoped. It is not: `Session.commit()` releases the connection back to the pool,
    where the checkin hook resets both, so the next statement ran with neither.
    `create_case` commits and then `session.refresh(case)`es for the server-defaulted
    timestamps, so on a connection with no superuser bypass the first command in the
    product raised `InvalidRequestError`.

    The tenant now lives on `Session.info` and an `after_begin` listener re-applies it per
    transaction (`app/shared/tenant.py`). Reverting that listener turns this red — and only
    on this connection, because on the owner the tenantless read bypasses RLS and succeeds.
    """
    created = rls_api("user_a").post("/api/v1/cases", json={"title": "A's case"})
    assert created.status_code == 201
    case_id = created.json()["id"]

    # Two more commands, each of which commits and then reads the row back.
    profile = rls_api("user_a").put(
        f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS
    )
    assert profile.status_code == 200
    confirmed = rls_api("user_a").post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    assert confirmed.status_code == 200


def test_a_recalculation_reports_the_conclusions_it_just_wrote(
    seeded_case: str, rls_api: Api
) -> None:
    """The same defect in the shape that did not raise — and the more dangerous shape.

    `_run_trusted_assessment` commits, and the route then builds its response from
    `list_requirements`, which queries afterwards. Tenantless, that query matched nothing
    and every requirement fell back to its unassessed default, so the endpoint answered
    **200** with `result_count: 9` and every conclusion reading `NOT_YET_ASSESSED` while
    the rows it had just written said `SUPPORTED` / `CURRENT`.

    A silent wrong answer on the assessment path, on the one endpoint whose job is to
    report what the deterministic rules concluded — the failure mode the product exists to
    prevent. Asserted separately from the raising half above, because a fix that only
    restored the refreshes would leave this one green and wrong.
    """
    body = rls_api("user_a").post(f"/api/v1/cases/{seeded_case}/assessments/recalculate").json()

    assert body["result_count"] > 0
    conclusions = {row["conclusion"] for row in body["requirements"]}
    assert conclusions != {"NOT_YET_ASSESSED"}, (
        f"recalculate reported {body['result_count']} results, all NOT_YET_ASSESSED"
    )
    # The response must agree with a fresh read of the same rows.
    follow_up = rls_api("user_a").get(f"/api/v1/cases/{seeded_case}/requirements").json()
    assert {row["requirement_key"]: row["conclusion"] for row in body["requirements"]} == {
        row["requirement_key"]: row["conclusion"] for row in follow_up
    }


def test_the_tenant_survives_a_commit_and_a_rollback(
    rls_sessionmaker: Callable[[], Session],
) -> None:
    """The mechanism itself, without HTTP in the way.

    Two ways the connection's own settings used to be lost, one root cause. The commit path
    is the defect above. The rollback path is ADR-0006 R5, recorded there as a separate
    latent risk — a pre-first-commit `ROLLBACK` reverted the non-LOCAL role and GUC, and it
    stayed latent only because no handler happened to re-query afterwards. Re-applying per
    transaction closes both, which is why they are asserted together.
    """
    with rls_sessionmaker() as session:
        set_tenant(session, "user_a")

        def context() -> tuple[str, str]:
            role, tenant = session.execute(
                text("SELECT current_user, current_setting('app.user_id', true)")
            ).one()
            return str(role), str(tenant)

        assert context() == (APP_ROLE, "user_a")
        session.commit()
        assert context() == (APP_ROLE, "user_a"), "lost across a commit"
        session.rollback()
        assert context() == (APP_ROLE, "user_a"), "lost across a rollback (ADR-0006 R5)"

        clear_tenant(session)
        current_user, tenant = context()
        assert current_user == RLS_TEST_ROLE and not tenant, "clear_tenant left the context set"
