"""Per-request tenant identity for Postgres Row-Level Security (defence in depth).

RLS policies on the case-scoped tables filter rows by `current_setting('app.user_id')`.
`get_tenant_session` sets that GUC from the authenticated user for every case-scoped
request, so a query can only ever see the caller's own rows — even if an app-level
ownership check were forgotten (CLAUDE.md §11; ADR-0006).

Fail-closed: the policies read the GUC with `missing_ok=true`, so an unset value is
NULL and matches no row (and `WITH CHECK` rejects writes). Combined with the pool
checkin reset in `app.core.db`, a reused connection never carries a previous tenant's
id into a query that forgot to set one — a bug surfaces as "no rows", never a leak.

That same checkin reset is why the tenant does not survive a mid-request commit. See
`set_tenant` below: the guarantee here is per-transaction, not per-request.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.shared.db import get_db

TENANT_GUC = "app.user_id"
APP_ROLE = "app_rls"


def set_tenant(session: Session, user_id: str) -> None:
    """Enter the RLS context for `user_id`: switch to the non-superuser `app_rls`
    role (so policies are enforced — the owner/superuser would otherwise bypass them)
    and bind the tenant GUC.

    **`is_local=False` does not do what this comment used to claim.** It said the
    non-LOCAL setting "keeps both set across the request's transaction boundaries (the
    unit of work commits mid-request)". It does not. Both settings live on the *connection*,
    and `Session.commit()` releases the connection back to the pool, where the checkin
    listener in `app.core.db` runs `RESET ROLE; RESET app.user_id`. Every statement after a
    mid-request commit therefore runs with no role and no tenant:

        set_tenant(session, "user_a")  ->  (app_rls, 'user_a')
        session.commit()               ->  connection released, reset fires
        session.execute(...)           ->  (login_role, '')

    On a superuser login role that is invisible, because the tenantless query bypasses RLS
    and succeeds. On a non-superuser one it is not: eleven call sites across six modules
    query after their own commit, and `assessments.service.list_requirements` is one of
    them — so `POST /assessments/recalculate` answers 200 with every requirement reading
    `NOT_YET_ASSESSED`. See the strict xfails in `tests/security/test_rls_login_role.py`.

    The fix is to make the tenant transaction-scoped rather than connection-scoped: record
    the user id on `Session.info` here and re-apply role and GUC from an `after_begin`
    listener. That also subsumes ADR-0006 R5, which is the same root cause reached through
    a rollback rather than a commit. Until then the backstop only holds within a single
    transaction, and ADR-0006 R1 Option A cannot be adopted.
    """
    session.execute(text(f"SET ROLE {APP_ROLE}"))
    session.execute(select(func.set_config(TENANT_GUC, user_id, False)))


def get_tenant_session(
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Session:
    """The session dependency for every case-scoped route: the same `get_db` session,
    with the RLS tenant set to the caller before any query runs."""
    set_tenant(session, user.user_id)
    return session
