"""Domain-level exceptions shared across modules, with their HTTP mapping.

`register_exception_handlers` wires these onto the FastAPI app so services and
domain objects can raise intent (`ConcurrencyConflict`, `IllegalTransition`)
without importing HTTP concerns.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Base for domain-rule violations surfaced to the API layer."""


class ConcurrencyConflict(DomainError):
    """A command supplied a stale revision; the aggregate changed underneath it."""


class IllegalTransition(DomainError):
    """A lifecycle transition was attempted that the state machine forbids."""


class ProfileIncomplete(DomainError):
    """A profile was confirmed before its required answers were all provided."""

    def __init__(self, missing_fields: list[str]) -> None:
        self.missing_fields = missing_fields
        super().__init__(f"missing required answers: {', '.join(missing_fields)}")


class CaseNotActive(DomainError):
    """A case-scoped command that needs an assessable case was issued against one
    that is not ACTIVE (still DRAFT/onboarding, archived, or pending deletion).

    Distinct from the ownership 404 on purpose: the case exists and is the caller's,
    it is simply not yet ready for this input. That is a state the user must be able
    to understand and act on (finish onboarding), not one to hide behind "not found".
    Carries a stable `code` so the frontend can route the user back to onboarding."""

    code = "CASE_NOT_ACTIVE"

    def __init__(self, lifecycle_status: str) -> None:
        self.lifecycle_status = lifecycle_status
        super().__init__(f"this action needs an active case; the case is {lifecycle_status}")


class TravelRecordNotFound(DomainError):
    """A travel record referenced by id does not exist in this case. Raised (→ 404)
    rather than leaking existence when the id is unknown *or* belongs to another of
    the user's own cases — RLS hides other tenants, but not the caller's other cases,
    so the case-ownership of a nested object is checked explicitly (Domain §3.1)."""


class StateWithoutEventError(RuntimeError):
    """A unit of work tried to commit business state without emitting a domain event.

    This is a programming error, not a user error — it never reaches the API as a
    handled response; it fails loudly in tests and logs.
    """


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ConcurrencyConflict)
    async def _conflict(_request: Request, _exc: ConcurrencyConflict) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "The record changed since you loaded it; reload and retry."},
        )

    @app.exception_handler(IllegalTransition)
    async def _illegal_transition(_request: Request, exc: IllegalTransition) -> JSONResponse:
        # 409: the aggregate is in a state that conflicts with the requested command.
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})

    @app.exception_handler(CaseNotActive)
    async def _case_not_active(_request: Request, exc: CaseNotActive) -> JSONResponse:
        # 409: the case's lifecycle state conflicts with a command that needs an
        # active case. Not a 404 — the case is real and owned; it is just not ready.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": str(exc),
                "code": exc.code,
                "lifecycle_status": exc.lifecycle_status,
            },
        )

    @app.exception_handler(TravelRecordNotFound)
    async def _travel_record_not_found(
        _request: Request, _exc: TravelRecordNotFound
    ) -> JSONResponse:
        # 404: unknown id, or an id from another case — indistinguishable on purpose.
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Travel record not found"}
        )

    @app.exception_handler(ProfileIncomplete)
    async def _profile_incomplete(_request: Request, exc: ProfileIncomplete) -> JSONResponse:
        # 422: the request is well-formed but the profile cannot yet be confirmed.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(exc), "missing_fields": exc.missing_fields},
        )
