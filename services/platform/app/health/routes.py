"""Liveness, readiness, and the one endpoint that spends money on purpose.

- ``/health/live``      — the process is up. No dependencies touched.
- ``/health/ready``     — dependencies (Postgres, Redis) are reachable, and the AI
  provider is *configured*. Returns 503 when any check fails.
- ``/health/ai-probe``  — makes one real model call. Secret-gated, off by default,
  and excluded from the OpenAPI schema: the 404 hides whether it is *enabled*, which
  a published route listing would give away for free.

**Readiness reports AI configuration, not AI reachability**, and the distinction is
deliberate. A live model call on every readiness probe would bill the account for
uptime — an orchestrator polls this every few seconds — so `ready` answers "could we
reach a provider" and the probe answers "can we". Only the second distinguishes a
valid key from a well-formed one, which is why it exists at all and why the deployed
smoke calls it once a day rather than continuously.
"""

import secrets
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel

from app.ai.boot import ai_configured
from app.ai.factory import get_provider
from app.ai.probe import run_probe
from app.ai.spend import SpendCeilingReached
from app.core.config import Settings, get_settings
from app.core.db import check_database
from app.core.redis import check_redis

router = APIRouter(tags=["health"])
_log = structlog.get_logger()


class LiveResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, bool]


class ProbeResponse(BaseModel):
    """Deliberately says nothing about the model's *answer* — only that a call
    completed. The probe checks the wiring; reporting what the model said would
    invite reading it as a quality signal."""

    status: str
    provider: str
    model: str
    latency_ms: int
    attempts: int


@router.get("/health/live", response_model=LiveResponse)
def live() -> LiveResponse:
    return LiveResponse(status="alive")


@router.get("/health/ready", response_model=ReadyResponse)
def ready(response: Response) -> ReadyResponse:
    checks = {
        "database": check_database(),
        "redis": check_redis(),
        # Configuration presence only — see the module docstring.
        "ai_provider": ai_configured(),
    }
    ok = all(checks.values())
    if not ok:
        response.status_code = 503
    return ReadyResponse(status="ready" if ok else "not_ready", checks=checks)


@router.post("/health/ai-probe", response_model=ProbeResponse, include_in_schema=False)
def ai_probe(
    settings: Annotated[Settings, Depends(get_settings)],
    x_probe_secret: Annotated[str, Header()] = "",
) -> ProbeResponse:
    """Make one real capability call. Costs a fraction of a penny; gated accordingly.

    Takes no session. The ledger opens its own (see `ai/service.py`), so this handler
    never holds one — which keeps `test_no_handler_takes_a_session_that_skipped_the
    _tenant` absolute rather than needing an exemption for the one route that would
    have been a legitimate exception. An absolute guard is worth more than a correct
    exception to it.
    """
    if not settings.ai_probe_secret:
        # Absent secret disables the endpoint rather than defaulting it open. A
        # money-spending route that is on unless configured off is the wrong way
        # round, and 404 rather than 403 avoids advertising that it exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    # Compared as *bytes*, constant-time. `==` on strings leaks length and prefix
    # through timing, and `compare_digest` on `str` raises TypeError for non-ASCII —
    # which Starlette will hand it, because it decodes headers as latin-1. One 0xFF
    # byte in the header was therefore an unauthenticated 500, and worse than noise:
    # a disabled probe 404s *before* this line, so the 500 told an anonymous caller
    # that AI_PROBE_SECRET is set, which is exactly what the 404-not-403 above hides.
    if not secrets.compare_digest(
        x_probe_secret.encode("latin-1", "ignore"), settings.ai_probe_secret.encode()
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="probe_secret_invalid")

    try:
        result = run_probe(get_provider(), settings=settings)
    except SpendCeilingReached as exc:
        # 429, not 500: the deployment is working exactly as designed and the caller
        # should back off rather than page someone.
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from None

    if not result.succeeded:
        # The whole point of the endpoint. A failure here is the deployed-red signal
        # that no amount of configuration checking produces.
        _log.error("ai.probe_failed", status=result.status.value, attempts=result.attempts)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ai_provider_unreachable:{result.status.value}",
        )

    settings_provider = "fake" if settings.ai_provider == "fake" else "openai"
    from app.ai.config import config_for
    from app.ai.domain import Capability

    return ProbeResponse(
        status="ok",
        provider=settings_provider,
        model=config_for(Capability.PROVIDER_PROBE).model,
        latency_ms=result.latency_ms,
        attempts=result.attempts,
    )
