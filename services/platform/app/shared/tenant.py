"""Per-request tenant identity for Postgres Row-Level Security (defence in depth).

RLS policies on the case-scoped tables filter rows by `current_setting('app.user_id')`.
`get_tenant_session` sets that GUC from the authenticated user for every case-scoped
request, so a query can only ever see the caller's own rows — even if an app-level
ownership check were forgotten (CLAUDE.md §11; ADR-0006).

Fail-closed: the policies read the GUC with `missing_ok=true`, so an unset value is
NULL and matches no row (and `WITH CHECK` rejects writes). A query that forgot to
establish a tenant surfaces as "no rows", never as a leak.

**The tenant is transaction-scoped, and re-applied automatically.** The authoritative
record is `session.info`, not the connection; the `after_begin` listener at the bottom of
this module re-applies role and GUC at the start of every transaction the session opens.
See `set_tenant` for why that indirection exists — the short version is that binding them
to the connection did not survive the unit of work's own commit, and on a superuser login
role nobody could tell.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy import Connection, event, func, select
from sqlalchemy.orm import Session, SessionTransaction

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.shared.db import get_db

TENANT_GUC = "app.user_id"
APP_ROLE = "app_rls"

#: Where the tenant actually lives. `Session.info` survives commit and rollback, which is
#: the whole point — the connection's own settings do not.
TENANT_SESSION_KEY = "rls_tenant_user_id"


def _apply(connection: Connection, user_id: str) -> None:
    """Bind role and tenant for the *current transaction*.

    One round trip, and `is_local=True` on both. Transaction-scoped rather than
    session-scoped because the listener re-applies them per transaction anyway, so local
    settings unwind on their own and a connection cannot carry a tenant anywhere. The user
    id travels as a bound parameter; it is a Clerk subject and never interpolated.
    """
    connection.execute(
        select(
            func.set_config("role", APP_ROLE, True),
            func.set_config(TENANT_GUC, user_id, True),
        )
    )


@event.listens_for(Session, "after_begin")
def _reapply_tenant(
    session: Session, _transaction: SessionTransaction, connection: Connection
) -> None:
    """Re-establish the tenant whenever the session opens a transaction.

    This is the fix for the defect the M5 RLS harness found. Without it, tenant state was
    bound to the connection and silently lost the moment the unit of work committed
    mid-request, because `Session.commit()` releases the connection and the pool checkin
    hook resets it. Every subsequent statement ran with no role and no tenant.

    On a superuser login role that is invisible — the tenantless query bypasses RLS and
    succeeds — which is why it survived from M2 to M5 with tests green. On a non-superuser
    one, eleven call sites across six modules broke, and `POST /assessments/recalculate`
    answered 200 with every requirement reading `NOT_YET_ASSESSED` while the rows it had
    just written said `SUPPORTED`. A silent wrong answer on the assessment path.

    Registered on the `Session` class rather than one sessionmaker, so it covers the
    request session, the recalculation-failure recovery's own session, the CLI scripts and
    the seed — anything that calls `set_tenant` is covered by construction rather than by
    remembering. A session with no tenant recorded is left alone: no role, no GUC, and a
    non-superuser connection then fails closed.
    """
    user_id = session.info.get(TENANT_SESSION_KEY)
    if user_id is not None:
        _apply(connection, user_id)


def set_tenant(session: Session, user_id: str) -> None:
    """Enter the RLS context for `user_id` and keep it for the life of the session.

    Records the tenant on `session.info` — the durable half — then applies it to the
    current transaction. The explicit apply is not redundant with the listener: if a
    transaction is already open, `after_begin` has already fired and would not fire again,
    so this call is what covers that case. If none is open, `session.connection()`
    autobegins, the listener applies it, and this repeats a no-op.

    Switching into the non-superuser `app_rls` role is what makes the policies apply at
    all; the owner would otherwise bypass them, even under FORCE.
    """
    session.info[TENANT_SESSION_KEY] = user_id
    _apply(session.connection(), user_id)


def clear_tenant(session: Session) -> None:
    """Leave the RLS context: forget the tenant and drop back to the connection's own role.

    Needed by anything that must act as the owner on a session that has been in a tenant
    context — the test harness truncating tables, principally. Popping `session.info` alone
    would not be enough, because the current transaction still carries the settings the
    listener applied to it.
    """
    session.info.pop(TENANT_SESSION_KEY, None)
    connection = session.connection()
    connection.exec_driver_sql("RESET ROLE")
    connection.exec_driver_sql(f'RESET "{TENANT_GUC}"')


def get_tenant_session(
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Session:
    """The session dependency for every case-scoped route: the same `get_db` session,
    with the RLS tenant set to the caller before any query runs."""
    set_tenant(session, user.user_id)
    return session
