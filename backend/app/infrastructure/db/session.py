"""
Async database engine and session management.

`get_db` is a FastAPI dependency — routes never touch the engine directly.
This is also the seam tests use: `app.dependency_overrides[get_db]` swaps
in a SQLite session for the API test suite without changing any route code.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, pool_pre_ping=True, echo=settings.debug)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped async DB session, committing/closing per request lifecycle."""
    async with AsyncSessionLocal() as session:
        yield session
