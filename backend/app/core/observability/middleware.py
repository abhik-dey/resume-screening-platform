"""
Request context and metrics middleware.

Assigns every request an ID (honoring an inbound X-Request-ID so the trail
survives across services), records HTTP metrics, and logs the request in
structured form.
"""
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.observability.context import new_request_id, set_request_id, set_user_id
from app.core.observability.logging_config import get_logger
from app.core.observability.metrics import http_request_duration_seconds, http_requests_total

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


def _endpoint_label(request: Request) -> str:
    """Use the route TEMPLATE, not the raw path.

    /api/v1/resumes/{resume_id} rather than the concrete UUID — otherwise
    every distinct ID becomes its own metric label value, which is the
    classic way to blow up Prometheus cardinality.
    """
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return "unmatched"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        set_request_id(request_id)
        set_user_id(None)  # populated by auth once the user is resolved

        started = time.perf_counter()
        status_code = 500  # assume failure until proven otherwise
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration = time.perf_counter() - started
            endpoint = _endpoint_label(request)

            http_requests_total.labels(
                method=request.method, endpoint=endpoint, status=str(status_code)
            ).inc()
            http_request_duration_seconds.labels(
                method=request.method, endpoint=endpoint
            ).observe(duration)

            logger.info(
                "request completed",
                extra={
                    "method": request.method,
                    "endpoint": endpoint,
                    "status_code": status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )
