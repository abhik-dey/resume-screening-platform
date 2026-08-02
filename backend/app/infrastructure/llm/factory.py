"""
LLM provider factory.

The only place in the codebase that knows OpenAIProvider or AnthropicProvider
exist. Everything else (agents, services) depends on the LLMProvider
interface and is handed a concrete instance from here.
"""
from app.core.config import Settings
from app.domain.interfaces.llm_provider import LLMProvider
from app.infrastructure.llm.anthropic_provider import AnthropicProvider
from app.infrastructure.llm.openai_provider import OpenAIProvider


class LLMConfigurationError(Exception):
    """Raised when the configured LLM provider is missing required settings
    (e.g. LLM_PROVIDER=openai but no OPENAI_API_KEY set)."""


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise LLMConfigurationError(
                "LLM_PROVIDER=openai requires OPENAI_API_KEY to be set in the environment"
            )
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url or None,
        )

    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMConfigurationError(
                "LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY to be set in the environment"
            )
        return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)

    raise LLMConfigurationError(
        f"Unknown LLM_PROVIDER '{settings.llm_provider}'. Must be 'openai' or 'anthropic'."
    )
