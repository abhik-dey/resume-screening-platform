"""Rate limiting and security-header middleware."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.observability.logging_config import get_logger
from app.infrastructure.security.rate_limiter import RateLimiter

logger = get_logger(__name__)

# Endpoints that trigger LLM calls get a much stricter limit: they're slow,
# they cost money per request, and they're the realistic abuse target. A
# generic global limit would be either too loose for these or too tight for
# ordinary reads.
_EXPENSIVE_PATH_MARKERS = (
    "/pipeline", "/parse", "/match", "/feedback", "/interview-questions",
    "/analyze", "/report", "/rag/", "/extract-skills",
)


def _is_expensive(path: str) -> bool:
    return any(marker in path for marker in _EXPENSIVE_PATH_MARKERS)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        limiter: RateLimiter,
        default_limit: int,
        expensive_limit: int,
        window_seconds: int,
        enabled: bool = True,
    ) -> None:
        super().__init__(app)
        self._limiter = limiter
        self._default_limit = default_limit
        self._expensive_limit = expensive_limit
        self._window = window_seconds
        self._enabled = enabled

    def _identity(self, request: Request) -> str:
        """Prefer the authenticated user; fall back to client IP.

        Keying on the raw Authorization header rather than decoding the JWT
        here: middleware runs before dependency resolution, and decoding a
        token twice per request to save a hash is a poor trade. The header
        is stable per session, which is what the limiter needs.
        """
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            return f"token:{hash(auth[7:]) & 0xFFFFFFFF:08x}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"

    async def dispatch(self, request: Request, call_next):
        if not self._enabled or request.url.path in ("/metrics", "/api/health"):
            # Health and metrics are polled continuously by infrastructure;
            # limiting them would break monitoring rather than stop abuse.
            return await call_next(request)

        expensive = _is_expensive(request.url.path)
        limit = self._expensive_limit if expensive else self._default_limit
        key = f"{self._identity(request)}:{'expensive' if expensive else 'default'}"

        result = await self._limiter.check(key, limit, self._window)

        if not result.allowed:
            logger.warning(
                "rate limit exceeded",
                extra={"path": request.url.path, "limit": limit, "expensive": expensive},
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"Rate limit exceeded: {limit} requests per {self._window}s for this "
                        f"endpoint category. Retry after {result.retry_after_seconds}s."
                    )
                },
                headers={
                    "Retry-After": str(result.retry_after_seconds),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Standard defensive response headers.

    This is an API rather than a browser-rendered app, so several of these
    are defense in depth rather than primary controls — but the API docs
    (/docs) ARE browser-rendered, and cheap headers are worth having.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
        # Permissive enough for Swagger UI's CDN assets, restrictive
        # elsewhere. A stricter policy would break /docs.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net; img-src 'self' data: fastapi.tiangolo.com",
        )
        return response
