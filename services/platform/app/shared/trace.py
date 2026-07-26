"""Access to the request-scoped trace id bound by `TraceIdMiddleware`.

Events and audit entries carry the trace id so a domain change can be correlated
with the request that caused it, without threading the id through every call.
"""

import structlog


def current_trace_id() -> str | None:
    value = structlog.contextvars.get_contextvars().get("trace_id")
    return value if isinstance(value, str) else None
