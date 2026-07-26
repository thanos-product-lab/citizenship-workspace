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
