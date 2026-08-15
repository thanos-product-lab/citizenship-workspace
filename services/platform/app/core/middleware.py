"""Request-scoped trace id.

Reuses an inbound ``x-request-id`` when present (so a trace can span the browser,
the API, and the worker) or mints one. Bound into structlog contextvars for the
duration of the request and echoed back on the response.
"""

from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

TRACE_HEADER = "x-request-id"


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get(TRACE_HEADER) or uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers[TRACE_HEADER] = trace_id
        return response
