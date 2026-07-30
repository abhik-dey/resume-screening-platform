"""
Health check endpoint.

This is the smoke test for the whole environment: if this endpoint reports
both dependencies as "ok", we know FastAPI, Postgres, and Redis are all
reachable from each other over the Docker network.
"""
from typing import Literal

import redis.asyncio as redis
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()


class DependencyStatus(BaseModel):
    status: Literal["ok", "error"]
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    postgres: DependencyStatus
    redis: DependencyStatus


async def _check_postgres() -> DependencyStatus:
    try:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        return DependencyStatus(status="ok")
    except Exception as exc:  # noqa: BLE001 — deliberately broad for a health probe
        return DependencyStatus(status="error", detail=str(exc))


async def _check_redis() -> DependencyStatus:
    try:
        client = redis.from_url(settings.redis_url)
        await client.ping()
        await client.aclose()
        return DependencyStatus(status="ok")
    except Exception as exc:  # noqa: BLE001
        return DependencyStatus(status="error", detail=str(exc))


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Report liveness of the API plus its two core infra dependencies."""
    postgres_status = await _check_postgres()
    redis_status = await _check_redis()

    overall = "ok" if postgres_status.status == "ok" and redis_status.status == "ok" else "degraded"

    return HealthResponse(status=overall, postgres=postgres_status, redis=redis_status)
