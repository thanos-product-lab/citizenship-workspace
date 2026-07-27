"""Per-request tenant identity for Postgres Row-Level Security (defence in depth).

RLS policies on the case-scoped tables filter rows by `current_setting('app.user_id')`.
`get_tenant_session` sets that GUC from the authenticated user for every case-scoped
request, so a query can only ever see the caller's own rows — even if an app-level
ownership check were forgotten (CLAUDE.md §11; ADR-0006).

Fail-closed: the policies read the GUC with `missing_ok=true`, so an unset value is
NULL and matches no row (and `WITH CHECK` rejects writes). Combined with the pool
checkin reset in `app.core.db`, a reused connection never carries a previous tenant's
id into a query that forgot to set one — a bug surfaces as "no rows", never a leak.
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
    and bind the tenant GUC. `is_local=False` keeps both set across the request's
    transaction boundaries (the unit of work commits mid-request)."""
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
