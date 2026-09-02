"""Refuse to boot into a configuration that can only fail per-request.

M7 hit the local-green/deployed-red pattern five times, and a model provider is its
purest form: credentials plus network plus quota, trivially faked on a laptop. It is
also worse than the Redis case in one specific way. An unreachable broker kills the
worker at startup because `broker_connection_retry_on_startup = False`; a missing or
rejected API key does nothing at all until a user uploads a document, at which point
one document fails and the deployment still reports itself healthy.

So the checks here are the same shape as `check_upload_secret` and
`check_backing_services`, run at import in `main.py` for the reason recorded there:
raising from a lifespan produces ~100 frames per crash and pushes the line naming
the cause out of the retained log window.

**Presence is not reachability**, and this file only proves presence. A well-formed
key that has been revoked, or an account with no credit — which is exactly what the
M8 spike hit on its first live run — passes every check here. Only a real call
distinguishes them, which is what `/health/ai-probe` and the deployed smoke are for.
"""

import structlog

from app.core.config import LOCAL_ENVIRONMENTS, get_settings

_log = structlog.get_logger()


def check_ai_configuration() -> None:
    settings = get_settings()
    local = settings.environment in LOCAL_ENVIRONMENTS

    if settings.ai_provider == "fake":
        if not local:
            # The dangerous misconfiguration, and the reason it is a boot failure
            # rather than a warning: the fake returns schema-valid synthetic output,
            # so a deployment running on it would present fabricated values as model
            # proposals and nothing downstream could tell. Same line the storage
            # `memory` backend draws (threat model §12).
            raise RuntimeError(
                "AI_PROVIDER=fake outside local development. The fake provider returns "
                "synthetic structured output and would present fabricated values as "
                f"model proposals. Observed ENVIRONMENT={settings.environment!r}. Set "
                "AI_PROVIDER=openai and supply OPENAI_API_KEY."
            )
        _log.warning("ai.fake_provider_selected", environment=settings.environment)
        return

    if not settings.openai_api_key and not local:
        # Name the variable and what was observed, never the value. A bare "must be
        # set" cannot distinguish the four ways this actually goes wrong on a
        # platform, and those four are the whole diagnostic value of the message.
        raise RuntimeError(
            "OPENAI_API_KEY must be set outside local development: without it every "
            "document upload reaches the extraction stage and fails there, while the "
            "API's health check keeps reporting ready. Observed "
            f"ENVIRONMENT={settings.environment!r}; OPENAI_API_KEY was absent or empty "
            "in this process's environment. Check the running deployment has it — not "
            "just the dashboard — and that it is set on the API *and* worker services."
        )

    if settings.ai_daily_spend_ceiling_usd <= 0:
        raise RuntimeError(
            "AI_DAILY_SPEND_CEILING_USD must be greater than zero. A ceiling of zero "
            "refuses every call, and a negative one is a configuration error being read "
            f"as a budget. Observed {settings.ai_daily_spend_ceiling_usd!r}."
        )

    # The bound that a per-request timeout does not give you. Asserted at boot
    # because the arithmetic is easy to break from either side — raising the request
    # timeout or lowering the deadline — and the symptom is a worker killed
    # mid-write by Celery's soft limit, which reports nothing about either setting.
    if settings.ai_request_timeout_seconds > settings.ai_task_deadline_seconds:
        raise RuntimeError(
            f"AI_REQUEST_TIMEOUT_SECONDS ({settings.ai_request_timeout_seconds}) exceeds "
            f"AI_TASK_DEADLINE_SECONDS ({settings.ai_task_deadline_seconds}), so the task "
            "budget could never permit even one call."
        )


def ai_configured() -> bool:
    """Whether a provider *could* be reached. Configuration presence only — this makes
    no call, deliberately: an orchestrator polls readiness every few seconds and a live
    model call there would bill the account for uptime.

    **Local environments always pass**, which is the same line `check_ai_configuration`
    above draws and for the same reason. Nothing in local development or CI requires a
    key — the app must import and serve without secrets — so reporting a developer's
    machine unready for the absence of one would be a false red on every `just up`, and
    a health check that is routinely red is a health check nobody reads.

    Deployed, the absence of a key is exactly the condition worth reporting, because it
    is invisible otherwise: every document fails at the extraction stage while the API
    keeps answering. That is the state M7's unreachable Redis spent fifteen minutes in.
    """
    settings = get_settings()
    if settings.environment in LOCAL_ENVIRONMENTS:
        return True
    return settings.ai_provider != "fake" and bool(settings.openai_api_key)
