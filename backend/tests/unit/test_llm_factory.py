"""
Tests for the LLM provider factory — including the free-tier path (Gemini
via the OpenAI-compatible adapter, using a custom base_url).
"""
import pytest

from app.core.config import Settings
from app.infrastructure.llm.factory import LLMConfigurationError, get_llm_provider
from app.infrastructure.llm.openai_provider import OpenAIProvider


def test_openai_provider_missing_key_raises():
    settings = Settings(llm_provider="openai", openai_api_key="")
    with pytest.raises(LLMConfigurationError):
        get_llm_provider(settings)


def test_anthropic_provider_missing_key_raises():
    settings = Settings(llm_provider="anthropic", anthropic_api_key="")
    with pytest.raises(LLMConfigurationError):
        get_llm_provider(settings)


def test_unknown_provider_raises():
    settings = Settings(llm_provider="not-a-real-provider")
    with pytest.raises(LLMConfigurationError):
        get_llm_provider(settings)


def test_openai_provider_uses_default_base_url_when_unset(monkeypatch):
    # Settings() reads real environment variables, which take priority over
    # values passed directly here — so a real OPENAI_BASE_URL set in the
    # environment (e.g. for actual Gemini usage) would otherwise leak into
    # this test and make it flaky depending on where it runs. Explicitly
    # clearing it makes this test deterministic regardless of environment.
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    settings = Settings(llm_provider="openai", openai_api_key="test-key", openai_base_url="")
    provider = get_llm_provider(settings)
    assert isinstance(provider, OpenAIProvider)
    assert str(provider._client.base_url) == "https://api.openai.com/v1/"


def test_openai_provider_uses_custom_base_url_for_free_gemini_tier(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    gemini_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
    settings = Settings(
        llm_provider="openai",
        openai_api_key="test-gemini-key",
        openai_model="gemini-2.5-flash",
        openai_base_url=gemini_url,
    )
    provider = get_llm_provider(settings)
    assert isinstance(provider, OpenAIProvider)
    assert str(provider._client.base_url) == gemini_url
