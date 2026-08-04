"""
Centralized, environment-driven configuration.

All settings are read from environment variables (or a .env file in local
dev). Nothing in this module is hardcoded to a specific deployment target —
that's what makes the same image work in dev, staging, and prod by just
changing env vars.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings, validated at startup by Pydantic."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App metadata ---
    app_name: str = "AI Resume Screening Platform"
    environment: str = Field(default="development")
    debug: bool = Field(default=True)

    # --- PostgreSQL ---
    postgres_user: str = Field(default="resume_user")
    postgres_password: str = Field(default="resume_pass")
    postgres_db: str = Field(default="resume_screening")
    postgres_host: str = Field(default="postgres")
    postgres_port: int = Field(default=5432)

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy connection string (asyncpg driver)."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # --- Redis ---
    redis_host: str = Field(default="redis")
    redis_port: int = Field(default=6379)

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    # --- CORS ---
    cors_origins: list[str] = Field(default=["http://localhost:5173"])

    # --- Auth / JWT ---
    # NOTE: the default below is fine for local dev only. Production MUST
    # override this via the JWT_SECRET_KEY env var with a long random value
    # (e.g. `openssl rand -hex 32`) — this is enforced in Phase 19 (Security).
    jwt_secret_key: str = Field(default="dev-only-insecure-secret-change-me")
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=60)

    # --- File Storage (Phase 5) ---
    # Local disk today; the FileStorage interface lets this become an S3
    # adapter later without touching ResumeService.
    resume_storage_dir: str = Field(default="./storage/resumes")
    max_resume_upload_size_mb: int = Field(default=10)

    @property
    def max_resume_upload_size_bytes(self) -> int:
        return self.max_resume_upload_size_mb * 1024 * 1024

    # --- LLM Provider (Phase 6) ---
    # Which adapter to use — "openai" or "anthropic". Never hardcode
    # provider-specific logic in agents; everything goes through this.
    llm_provider: str = Field(default="anthropic")
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")
    # Override to point the OpenAI SDK at any OpenAI-compatible endpoint —
    # e.g. Google's free Gemini API (see .env.example for the exact value).
    # Leave blank to use OpenAI's own API.
    openai_base_url: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    anthropic_model: str = Field(default="claude-sonnet-4-5")

    # --- Vector search (Phase 14) ---
    qdrant_url: str = Field(default="http://qdrant:6333")
    # "local", "openai", or "auto". Defaults to "local" so the system runs
    # end-to-end on a fresh clone with no API key and no network.
    #
    # Note that "auto" (openai when a key exists) is NOT the default: a
    # chat API key doesn't imply the same provider's embedding model names
    # are configured, and silently calling a live API with a mismatched
    # model name produces confusing 404s rather than a clear failure.
    embedding_provider: str = Field(default="local")
    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dimensions: int = Field(default=1536)
    # "qdrant" or "memory". Memory is the default for local development so
    # nothing breaks if Qdrant isn't running.
    vector_store_backend: str = Field(default="memory")

    # --- MCP tools (Phase 17) ---
    # GitHub is off by default: it makes real outbound requests, and the
    # username can originate from LLM output influenced by resume content.
    # Opt-in rather than silently reachable.
    github_tool_enabled: bool = Field(default=False)
    github_token: str = Field(default="")
    # Sandbox root for the filesystem tool. Paths are resolved and checked
    # for containment inside this directory; nothing outside is readable.
    tool_filesystem_root: str = Field(default="/app/storage")


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — avoids re-parsing env vars on every call."""
    return Settings()
