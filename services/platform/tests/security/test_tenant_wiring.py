"""Every route establishes a tenant before it queries, or is named as one that need not.

RLS is only a backstop if the request actually enters the tenant context, and that
happens in exactly one place: the `get_tenant_session` dependency, which issues
`SET ROLE app_rls` and binds `app.user_id`. A route wired to `get_db` instead would run
as the connection role and, on a deployment whose login role is a superuser, see every
tenant's rows.

**This file used to select routes by the literal `{case_id}` in the path**, which is a
property of a URL convention rather than of a handler. The M5 notes recorded the shape
that would slip through — *"a `GET /api/v1/evidence/{evidence_id}/download` is
case-scoped and invisible to the check"* — and named M7 as where it would break. It is
now inverted: **every** route must enter the tenant context unless it is named in
`TENANT_FREE_ROUTES`, so a new route is covered by default and an exemption is a visible
diff rather than an omission nobody sees.

The prefix rule it used to assume is now asserted separately rather than relied on:
`test_no_case_scoped_aggregate_is_addressable_outside_a_case_prefix` derives the
case-scoped tables from Postgres and requires anything addressing one to live under
`/cases/{case_id}/…`. The two checks are blind to different things — the first misses a
correctly-wired route in the wrong place, the second misses a route with no table behind
it — which is why both are here.

Neither covers code that opens its own session outside a request. `test_rls_login_role.py`
reaches those, and `test_task_tenant_wiring.py` covers Celery tasks (M7 slice 2).
"""

from collections.abc import Iterator

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

from app.main import app
from app.shared.db import get_db
from app.shared.tenant import get_tenant_session

# The prefix every case-scoped aggregate is addressable under.
CASE_PATH_PARAMETER = "{case_id}"

# Routes that legitimately never enter a tenant context, each with the reason it does
# not need one. Adding a name here is the only way to exempt a route, which makes an
# exemption a decision someone has to write down rather than an accident.
TENANT_FREE_ROUTES: frozenset[str] = frozenset(
    {
        # Liveness and readiness: no user, no rows.
        "GET /health/live",
        "GET /health/ready",
        # The caller's own identity, straight from the verified token. Touches no
        # case-scoped table.
        "GET /api/v1/me",
        # FastAPI's own docs endpoints are Starlette routes, not `APIRoute`s, so they
        # are never in scope here — `test_the_allowlist_names_only_routes_that_exist`
        # refused them when they were listed, which is the guard doing its job.
    }
)


def _api_routes(routes: list[BaseRoute] | None = None) -> Iterator[APIRoute]:
    """Every `APIRoute` in the app, flattened.

    `include_router` does not splice handlers into `app.routes`. On FastAPI 0.139 it
    appends one `_IncludedRouter` wrapper per call, holding the original router behind
    `original_router`. A single-level scan therefore finds ten wrappers and zero
    endpoints — and every assertion in this file would pass while checking nothing.
    `test_the_check_has_routes_to_check` exists because that is exactly what happened
    when this file was first written, and it is the reason a coverage guard sits beside
    every "assert the bad set is empty" test here."""
    for route in app.routes if routes is None else routes:
        if isinstance(route, APIRoute):
            yield route
        nested = getattr(route, "routes", None)
        if nested:
            yield from _api_routes(nested)
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from _api_routes(included.routes)


def _label(route: APIRoute) -> str:
    method = sorted(route.methods or ["GET"])[0]
    return f"{method} {route.path}"


def _case_scoped_routes() -> list[APIRoute]:
    return [route for route in _api_routes() if CASE_PATH_PARAMETER in route.path]


def _dependency_calls(dependant: Dependant) -> set[object]:
    """Every callable in the dependency tree, flattened. FastAPI nests sub-dependencies
    arbitrarily deep — `require_case_access` reaches `get_tenant_session` through one
    level today, and that depth is not a contract."""
    found: set[object] = set()
    pending = list(dependant.dependencies)
    while pending:
        current = pending.pop()
        if current.call is not None:
            found.add(current.call)
        pending.extend(current.dependencies)
    return found


def test_every_route_enters_a_tenant_or_is_allowlisted() -> None:
    """The inverted check: covered by default, exempt only by name.

    A route added without a tenant dependency fails here whatever its URL looks like,
    which is the property the old `{case_id}`-in-the-path selection did not have."""
    offenders = [
        _label(route)
        for route in _api_routes()
        if _label(route) not in TENANT_FREE_ROUTES
        and get_tenant_session not in _dependency_calls(route.dependant)
    ]
    assert offenders == [], (
        f"routes that never enter the RLS tenant context: {offenders}. Depend on "
        "require_case_access or get_tenant_session, not get_db — or, if the route "
        "genuinely touches no case-scoped row, add it to TENANT_FREE_ROUTES with the "
        "reason."
    )


def test_no_handler_takes_a_session_that_skipped_the_tenant() -> None:
    """A handler's *own* session must be the tenant one.

    The check above is satisfied by any `get_tenant_session` anywhere in the dependency
    tree — and `require_case_access` puts one there for free. So a handler can declare
    `session: Annotated[Session, Depends(get_db)]`, run its ownership check on a tenant
    session and then do all its real work on a tenantless one, and the check above stays
    green. Found by mutation, not by reading: switching the evidence content route to
    `get_db` passed every assertion in this file.

    On a superuser login role that session sees every tenant's rows, so the RLS backstop
    is gone while the route looks correctly wired. `get_db` appears as a *direct* child
    of the route's dependant only when a handler asked for it by name — the copy nested
    inside `get_tenant_session` is one level further down — so that is what is checked.
    """
    offenders = [
        _label(route)
        for route in _api_routes()
        if any(dependency.call is get_db for dependency in route.dependant.dependencies)
    ]
    assert offenders == [], (
        f"handlers taking a session that never entered the tenant context: {offenders}. "
        "Depend on get_tenant_session, not get_db — the ownership check running on a "
        "tenant session does not help the queries that follow it."
    )


def test_the_allowlist_names_only_routes_that_exist() -> None:
    """A stale exemption is an exemption nobody is reading. If a route is renamed or
    removed, its allowlist entry has to go with it."""
    live = {_label(route) for route in _api_routes()}
    stale = sorted(TENANT_FREE_ROUTES - live)
    assert stale == [], f"TENANT_FREE_ROUTES names routes that no longer exist: {stale}"


def test_the_allowlist_names_only_routes_that_need_it() -> None:
    """An unnecessary exemption is worse than a stale one.

    A route that already enters the tenant context gains nothing from being listed, and
    loses the check: if it is later rewired to `get_db`, the allowlist absolves it in
    silence. The first draft of this file listed `GET` and `POST /api/v1/cases` on the
    reasoning that "there is no case to establish a tenant for until one exists" — which
    is not what the code does; both depend on `get_tenant_session` directly. Those are
    the two routes that read and write the ownership table itself, so the exemption was
    covering exactly the wrong thing.

    Existence and necessity are different questions, and the test above only asks the
    first, which is why this one is separate rather than folded into it.
    """
    unnecessary = sorted(
        _label(route)
        for route in _api_routes()
        if _label(route) in TENANT_FREE_ROUTES
        and get_tenant_session in _dependency_calls(route.dependant)
    )
    assert unnecessary == [], (
        f"routes exempted from the tenant check that already pass it: {unnecessary}. "
        "Remove them from TENANT_FREE_ROUTES — an exemption they do not need is an "
        "exemption that hides a future regression."
    )


def test_no_case_scoped_aggregate_is_addressable_outside_a_case_prefix() -> None:
    """A row that belongs to one case must be reachable only through that case.

    The tenant check above proves a handler enters the RLS context; it says nothing
    about *which* case's rows it may then touch. A flat `/api/v1/evidence/{id}` would
    pass it while resting the entire case boundary on the handler remembering to
    re-check ownership — and the M5 notes named exactly that URL as the one M7 would
    introduce. So the shape is constrained rather than trusted.

    The table names come from Postgres, via the same derivation `test_rls_coverage.py`
    uses, so a new case-scoped table joins this check on the migration that creates it.
    """
    from tests.security.conftest import CASE_SCOPED_TABLES

    # Map each case-scoped table to the URL segments it could plausibly be addressed
    # under. The first token matters most and is the one the first draft missed:
    # `evidence_items` yielded only "evidence-item", so a real `/api/v1/evidence/{id}`
    # route slipped straight through. Found by mutation.
    #
    # `cases` itself is addressed at `/api/v1/cases`, which is the prefix rather than a
    # violation of it, and membership is never addressed directly.
    candidates: set[str] = set()
    for table in CASE_SCOPED_TABLES:
        if table in {"cases", "case_memberships"}:
            continue
        for form in (table, table.removesuffix("s")):
            candidates.add(form)
            candidates.add(form.replace("_", "-"))
        candidates.add(table.split("_", 1)[0])

    offenders = [
        _label(route)
        for route in _api_routes()
        if CASE_PATH_PARAMETER not in route.path
        and any(f"/{name}" in route.path for name in candidates)
    ]
    assert offenders == [], (
        f"case-scoped aggregates addressable outside a /cases/{{case_id}} prefix: "
        f"{offenders}. A storage key, an evidence id, or any other nested id is not a "
        "permission (Domain §52) — route it through its case."
    )


def test_the_check_has_routes_to_check() -> None:
    """Guard against the assertion above passing because the path marker changed and it
    now matches nothing."""
    case_scoped = _case_scoped_routes()
    assert len(case_scoped) > 10, f"only {len(case_scoped)} case-scoped routes found"


@pytest.mark.parametrize("path_fragment", ["/overview", "/requirements", "/issues", "/evidence"])
def test_a_known_case_scoped_route_is_seen_by_the_check(path_fragment: str) -> None:
    """Named routes, so a refactor that moves them out from under `{case_id}`
    without moving the ownership check with them is visible here."""
    matches = [route for route in _case_scoped_routes() if route.path.endswith(path_fragment)]
    assert matches, f"no case-scoped route ends with {path_fragment}"
    for route in matches:
        assert get_tenant_session in _dependency_calls(route.dependant)
