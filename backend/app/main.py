"""
Application entrypoint.

Kept deliberately thin: this file wires together config, middleware, and
routers. It should never contain business logic — that belongs in
services/ and agents/ (introduced in later phases).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api.health import router as health_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.jobs import router as jobs_router
from app.api.v1.endpoints.pipeline import router as pipeline_router
from app.api.v1.endpoints.rag import router as rag_router
from app.api.v1.endpoints.reports import router as reports_router
from app.api.v1.endpoints.resumes import router as resumes_router
from app.api.v1.endpoints.search import router as search_router
from app.api.v1.endpoints.tools import router as tools_router
from app.core.config import get_settings
from app.core.observability.logging_config import configure_logging, get_logger
from app.core.observability.metrics import render_metrics
from app.core.observability.middleware import RequestContextMiddleware
from app.core.observability.tracing import configure_tracing

settings = get_settings()

# Configured before the app is created so startup itself is logged in the
# chosen format rather than uvicorn's default.
configure_logging(level=settings.log_level, json_format=settings.log_json)
configure_tracing(
    enabled=settings.tracing_enabled, otlp_endpoint=settings.otlp_endpoint
)
logger = get_logger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Multi-agent AI resume screening platform.",
)

# Added before CORS so it wraps outermost: a request rejected by CORS
# should still get an ID and appear in metrics.
app.add_middleware(RequestContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(resumes_router)
app.include_router(reports_router)
app.include_router(search_router)
app.include_router(rag_router)
app.include_router(pipeline_router)
app.include_router(tools_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} API is running"}


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus scrape endpoint.

    Deliberately unauthenticated and excluded from the OpenAPI schema:
    Prometheus scrapers don't carry bearer tokens, and this is expected to
    be reachable only from inside the cluster network. Exposing it publicly
    would leak operational detail — that's a network-policy concern,
    addressed in the Kubernetes phase.
    """
    if not settings.metrics_enabled:
        return Response(content="metrics disabled\n", media_type="text/plain", status_code=404)
    return Response(content=render_metrics(), media_type="text/plain; version=0.0.4")
