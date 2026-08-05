"""
Rate limiter tests.

The fail-open behavior gets specific attention: it's a deliberate
availability trade, and a silent change to it would be a security
regression nobody would notice.
"""
from app.infrastructure.security.rate_limiter import RateLimiter


class _BrokenRedis:
    """Stands in for an unreachable Redis."""

    async def ping(self):
        raise ConnectionError("redis down")


async def test_fails_open_when_redis_is_unavailable(monkeypatch):
    # Deliberate trade: rate limiting protects against cost overruns, and
    # taking the whole API down because the limiter is unavailable swaps a
    # moderate problem for a total one.
    limiter = RateLimiter(redis_url="redis://nonexistent-host:6379")
    result = await limiter.check("test-key", limit=1, window_seconds=60)
    assert result.allowed is True


async def test_fail_open_is_logged_once_not_per_request(caplog):
    # A per-request error log during a Redis outage would bury everything
    # else in the log stream.
    limiter = RateLimiter(redis_url="redis://nonexistent-host:6379")
    for _ in range(5):
        await limiter.check("k", limit=1, window_seconds=60)
    assert limiter._unavailable_logged is True


async def test_result_reports_the_configured_limit():
    limiter = RateLimiter(redis_url="redis://nonexistent-host:6379")
    result = await limiter.check("k", limit=42, window_seconds=60)
    assert result.limit == 42


async def test_middleware_adds_rate_limit_headers_when_enabled():
    """Verifies the headers the API suite can't check.

    The API test suite disables rate limiting (see conftest), so header
    presence is asserted here against the middleware directly — where the
    limiter's behavior can be controlled rather than depending on request
    volume.
    """
    from httpx import ASGITransport, AsyncClient
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    from app.core.observability.security_middleware import RateLimitMiddleware

    class _AllowingLimiter:
        async def check(self, key, limit, window_seconds):
            from app.infrastructure.security.rate_limiter import RateLimitResult

            return RateLimitResult(allowed=True, limit=limit, remaining=limit - 1)

    async def _endpoint(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/x", _endpoint)])
    app.add_middleware(
        RateLimitMiddleware,
        limiter=_AllowingLimiter(),
        default_limit=10,
        expensive_limit=2,
        window_seconds=60,
        enabled=True,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/x")
    assert resp.headers["x-ratelimit-limit"] == "10"
    assert resp.headers["x-ratelimit-remaining"] == "9"


async def test_middleware_returns_429_with_retry_after_when_limit_exceeded():
    from httpx import ASGITransport, AsyncClient
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    from app.core.observability.security_middleware import RateLimitMiddleware

    class _RejectingLimiter:
        async def check(self, key, limit, window_seconds):
            from app.infrastructure.security.rate_limiter import RateLimitResult

            return RateLimitResult(
                allowed=False, limit=limit, remaining=0, retry_after_seconds=60
            )

    async def _endpoint(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/x", _endpoint)])
    app.add_middleware(
        RateLimitMiddleware,
        limiter=_RejectingLimiter(),
        default_limit=10,
        expensive_limit=2,
        window_seconds=60,
        enabled=True,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/x")
    assert resp.status_code == 429
    assert resp.headers["retry-after"] == "60"


async def test_expensive_endpoints_get_the_stricter_limit():
    """LLM endpoints are slow, cost money per call, and are the realistic
    abuse target — so they must not inherit the generous default."""
    from httpx import ASGITransport, AsyncClient
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    from app.core.observability.security_middleware import RateLimitMiddleware

    seen = {}

    class _RecordingLimiter:
        async def check(self, key, limit, window_seconds):
            from app.infrastructure.security.rate_limiter import RateLimitResult

            seen[key] = limit
            return RateLimitResult(allowed=True, limit=limit, remaining=limit - 1)

    async def _endpoint(request):
        return PlainTextResponse("ok")

    app = Starlette(
        routes=[Route("/api/v1/jobs/x/pipeline", _endpoint), Route("/api/v1/jobs", _endpoint)]
    )
    app.add_middleware(
        RateLimitMiddleware,
        limiter=_RecordingLimiter(),
        default_limit=120,
        expensive_limit=20,
        window_seconds=60,
        enabled=True,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        await c.get("/api/v1/jobs/x/pipeline")
        await c.get("/api/v1/jobs")

    limits = set(seen.values())
    assert 20 in limits, "expensive endpoint should get the strict limit"
    assert 120 in limits, "ordinary endpoint should get the default limit"
