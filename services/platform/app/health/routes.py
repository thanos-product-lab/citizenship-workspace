"""Liveness and readiness endpoints.

- ``/health/live``  — the process is up. No dependencies touched.
- ``/health/ready`` — dependencies (Postgres, Redis) are reachable. Returns 503
  when any check fails, so an orchestrator can hold traffic until it is ready.
"""

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.core.db import check_database
from app.core.redis import check_redis

router = APIRouter(tags=["health"])


class LiveResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, bool]


@router.get("/health/live", response_model=LiveResponse)
def live() -> LiveResponse:
    return LiveResponse(status="alive")


@router.get("/health/ready", response_model=ReadyResponse)
def ready(response: Response) -> ReadyResponse:
    checks = {"database": check_database(), "redis": check_redis()}
    ok = all(checks.values())
    if not ok:
        response.status_code = 503
    return ReadyResponse(status="ready" if ok else "not_ready", checks=checks)
