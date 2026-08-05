"""
Redis-backed sliding-window rate limiting.

WHY REDIS AND NOT IN-MEMORY
---------------------------
An in-memory limiter works until you run a second worker, then silently
allows N times the intended rate. Phase 21 adds Gunicorn with multiple
workers, so an in-memory limiter would stop working precisely when it
starts mattering — the worst kind of failure, because nothing breaks
visibly.

Redis has been running since Phase 2 doing nothing. This is what it's for.

FAILS OPEN
----------
If Redis is unreachable, requests are allowed. That's a deliberate
availability-over-enforcement trade for this system: rate limiting protects
against cost overruns and abuse, and taking the entire API down because the
rate limiter is unavailable trades a moderate problem for a total one. A
payment or auth system might reasonably choose the opposite.

The failure is logged loudly so it doesn't pass unnoticed.
"""
import time
from dataclasses import dataclass

import redis.asyncio as redis

from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int = 0


class RateLimiter:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: redis.Redis | None = None
        self._unavailable_logged = False

    async def _get_client(self) -> redis.Redis | None:
        if self._client is None:
            try:
                self._client = redis.from_url(self._redis_url, decode_responses=True)
                await self._client.ping()
                self._unavailable_logged = False
            except Exception as exc:  # noqa: BLE001 -- any Redis failure means fail-open
                if not self._unavailable_logged:
                    logger.error(
                        "Rate limiter unavailable — FAILING OPEN, requests are not being limited",
                        extra={"error_type": type(exc).__name__},
                    )
                    self._unavailable_logged = True
                self._client = None
        return self._client

    async def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        """Sliding-window check via a Redis sorted set.

        A sorted set keyed by timestamp gives a true sliding window rather
        than a fixed bucket. Fixed windows allow a burst of 2x the limit
        across a boundary — send `limit` requests at 0:59 and `limit` more
        at 1:01 and a fixed-window limiter permits both.
        """
        client = await self._get_client()
        if client is None:
            return RateLimitResult(allowed=True, limit=limit, remaining=limit)

        now = time.time()
        window_start = now - window_seconds
        redis_key = f"ratelimit:{key}"

        try:
            pipe = client.pipeline()
            pipe.zremrangebyscore(redis_key, 0, window_start)  # drop expired entries
            pipe.zcard(redis_key)
            pipe.zadd(redis_key, {f"{now}:{id(now)}": now})
            # TTL so abandoned keys don't accumulate forever.
            pipe.expire(redis_key, window_seconds + 1)
            results = await pipe.execute()
            count_before = results[1]
        except Exception as exc:  # noqa: BLE001
            if not self._unavailable_logged:
                logger.error(
                    "Rate limiter check failed — FAILING OPEN",
                    extra={"error_type": type(exc).__name__},
                )
                self._unavailable_logged = True
            return RateLimitResult(allowed=True, limit=limit, remaining=limit)

        if count_before >= limit:
            # Remove the entry just added: a rejected request shouldn't
            # extend the window and push recovery further out.
            try:
                await client.zremrangebyscore(redis_key, now, now)
            except Exception:  # noqa: BLE001 -- best-effort cleanup
                pass
            return RateLimitResult(
                allowed=False, limit=limit, remaining=0, retry_after_seconds=window_seconds
            )

        return RateLimitResult(
            allowed=True, limit=limit, remaining=max(0, limit - count_before - 1)
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
