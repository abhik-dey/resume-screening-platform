"""
Application entrypoint.

Kept deliberately thin: this file wires together config, middleware, and
routers. It should never contain business logic — that belongs in
services/ and agents/ (introduced in later phases).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.jobs import router as jobs_router
from app.api.v1.endpoints.rag import router as rag_router
from app.api.v1.endpoints.reports import router as reports_router
from app.api.v1.endpoints.resumes import router as resumes_router
from app.api.v1.endpoints.search import router as search_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Multi-agent AI resume screening platform.",
)

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


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} API is running"}
