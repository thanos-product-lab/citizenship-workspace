"""Row-level security: a tenant can only ever reach its own rows at the DB layer.

This is the defence-in-depth backstop behind the application ownership check — the
"row-level isolation" test ADR-0005/0006 require. A separate session is used for the
cross-tenant read so it starts with an empty identity map (RLS filters the DB, not
the in-memory cache).
"""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.applicants.domain import RouteProfile, RouteProfileVersion
from app.cases.domain import ApplicationCase, CaseMembership
from app.shared.db import get_sessionmaker
from app.shared.tenant import APP_ROLE, set_tenant

pytestmark = pytest.mark.integration


def _seed_case_for_user_a(session: Session) -> ApplicationCase:
    set_tenant(session, "user_a")
    case = ApplicationCase.create(owner_user_id="user_a", title="A's case")
    session.add(case)
    session.add(CaseMembership.owner(case_id=case.id, user_id="user_a"))
    session.flush()  # parent before children: no ORM relationship() drives ordering
    profile = RouteProfile.start(case_id=case.id)
    session.add(profile)
    session.flush()
    session.add(RouteProfileVersion.new_draft(route_profile_id=profile.id, created_by="user_a"))
    session.commit()
    return case


def test_rls_hides_a_case_from_another_tenant(db_session: Session) -> None:
    case = _seed_case_for_user_a(db_session)

    other = get_sessionmaker()()
    try:
        set_tenant(other, "user_b")
        assert other.get(ApplicationCase, case.id) is None  # invisible to user_b
        assert other.scalar(select(func.count()).select_from(ApplicationCase)) == 0

        set_tenant(other, "user_a")
        assert other.get(ApplicationCase, case.id) is not None  # visible to its owner
    finally:
        other.close()


def test_rls_hides_child_rows_from_another_tenant(db_session: Session) -> None:
    _seed_case_for_user_a(db_session)

    other = get_sessionmaker()()
    try:
        set_tenant(other, "user_b")
        assert other.scalar(select(func.count()).select_from(RouteProfile)) == 0
        assert other.scalar(select(func.count()).select_from(RouteProfileVersion)) == 0

        set_tenant(other, "user_a")
        assert other.scalar(select(func.count()).select_from(RouteProfile)) == 1
        assert other.scalar(select(func.count()).select_from(RouteProfileVersion)) == 1
    finally:
        other.close()


def test_rls_forbids_writing_a_row_for_another_tenant(db_session: Session) -> None:
    # As user_b, inserting a case owned by user_a violates the WITH CHECK policy.
    set_tenant(db_session, "user_b")
    db_session.add(ApplicationCase.create(owner_user_id="user_a", title="spoofed"))
    with pytest.raises(ProgrammingError):
        db_session.flush()
    db_session.rollback()


def test_rls_fails_closed_when_no_tenant_is_set(db_session: Session) -> None:
    """The fail-closed guarantee for the role the app actually runs as: under
    `app_rls` with no `app.user_id` set, every case row is invisible — a query that
    forgets to establish a tenant returns nothing rather than leaking."""
    _seed_case_for_user_a(db_session)

    other = get_sessionmaker()()
    try:
        other.execute(text(f"SET ROLE {APP_ROLE}"))  # role set, but NO tenant GUC
        assert other.scalar(select(func.count()).select_from(ApplicationCase)) == 0
        assert other.scalar(select(func.count()).select_from(RouteProfile)) == 0
    finally:
        other.close()
