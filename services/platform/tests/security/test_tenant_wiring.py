"""Every case-scoped route establishes a tenant before it queries.

RLS is only a backstop if the request actually enters the tenant context, and that
happens in exactly one place: the `get_tenant_session` dependency, which issues
`SET ROLE app_rls` and binds `app.user_id`. A route wired to `get_db` instead would run
as the connection role and, on a deployment whose login role is a superuser, see every
tenant's rows. `require_case_access` depends on `get_tenant_session`, so the ordinary way
to write a route already satisfies this — the failure mode is a route that reads the case
some other way.

This is a static check over the dependency graph, so it costs nothing and covers routes
no functional test has been written for yet. It does not cover code that opens its own
session outside a request; `test_rls_login_role.py` is what reaches those.
"""

from collections.abc import Iterator

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

from app.main import app
from app.shared.tenant import get_tenant_session

# The one marker of a case-scoped route. Everything under it reads or writes rows that
# belong to exactly one user.
CASE_PATH_PARAMETER = "{case_id}"


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


def test_every_case_scoped_route_depends_on_the_tenant_session() -> None:
    offenders = [
        f"{sorted(route.methods or [])} {route.path}"
        for route in _case_scoped_routes()
        if get_tenant_session not in _dependency_calls(route.dependant)
    ]
    assert offenders == [], (
        f"case-scoped routes that never enter the RLS tenant context: {offenders}. "
        "Depend on require_case_access or get_tenant_session, not get_db"
    )


def test_the_check_has_routes_to_check() -> None:
    """Guard against the assertion above passing because the path marker changed and it
    now matches nothing."""
    case_scoped = _case_scoped_routes()
    assert len(case_scoped) > 10, f"only {len(case_scoped)} case-scoped routes found"


@pytest.mark.parametrize("path_fragment", ["/overview", "/requirements", "/issues"])
def test_a_known_case_scoped_route_is_seen_by_the_check(path_fragment: str) -> None:
    """Three named routes, so a refactor that moves them out from under `{case_id}`
    without moving the ownership check with them is visible here."""
    matches = [route for route in _case_scoped_routes() if route.path.endswith(path_fragment)]
    assert matches, f"no case-scoped route ends with {path_fragment}"
    for route in matches:
        assert get_tenant_session in _dependency_calls(route.dependant)
