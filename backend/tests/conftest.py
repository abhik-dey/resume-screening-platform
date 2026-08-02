"""
Shared test fixtures.

Uses an in-memory SQLite database instead of the real PostgreSQL — this
keeps the test suite fast and fully isolated (no shared state between
runs, no need for Docker/Postgres just to run `pytest`). This works
because the `GUID` type decorator (see app/infrastructure/db/types.py)
makes our ORM models portable across both dialects.
"""
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.infrastructure.db.models  # noqa: F401 -- registers every table with Base
from app.api.deps import get_file_storage, get_llm_provider_dependency
from app.infrastructure.db.base import Base
from app.infrastructure.db.session import get_db
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import app
from tests.fakes import VALID_PARSED_RESUME_JSON, ScriptedLLMProvider

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def test_engine():
    # StaticPool + a single shared connection is required for SQLite's
    # in-memory mode, which otherwise creates a fresh (empty) database
    # per connection.
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session, tmp_path) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db():
        yield db_session

    def _override_get_file_storage():
        return LocalFileStorage(base_dir=str(tmp_path / "resumes"))

    def _override_get_llm_provider():
        # Default fake for API tests that don't specifically test parsing
        # retry/failure behavior. Tests that do (see test_resumes_api.py)
        # can reassign app.dependency_overrides[get_llm_provider_dependency]
        # themselves before making their request.
        return ScriptedLLMProvider([VALID_PARSED_RESUME_JSON])

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_file_storage] = _override_get_file_storage
    app.dependency_overrides[get_llm_provider_dependency] = _override_get_llm_provider
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
