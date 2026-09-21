import pytest
from backend.app.config import Settings
from backend.app.providers.base import LLMProvider
from backend.app.providers.mock import MockLLMProvider
from backend.app.providers.ollama import OllamaProvider
from backend.app.providers.openai_compatible import OpenAICompatibleProvider
from backend.app.providers.factory import get_llm_provider


@pytest.mark.asyncio
async def test_mock_provider_generation():
    provider = MockLLMProvider(response_text="Test Note Architecture")
    assert isinstance(provider, LLMProvider)
    assert provider.provider_name == "mock"
    assert provider.model_name == "mock-model"

    health = await provider.health_check()
    assert health is True

    result = await provider.generate(prompt="Explain RAG", system_prompt="Be concise")
    assert result == "Test Note Architecture"
    assert provider.last_prompt == "Explain RAG"
    assert provider.last_system_prompt == "Be concise"


def test_provider_factory_mock():
    settings = Settings(llm_provider="mock", llm_model="test-mock")
    provider = get_llm_provider(settings)
    assert isinstance(provider, MockLLMProvider)
    assert provider.model_name == "test-mock"


def test_provider_factory_ollama():
    settings = Settings(llm_provider="ollama", llm_model="qwen2.5:7b")
    provider = get_llm_provider(settings)
    assert isinstance(provider, OllamaProvider)
    assert provider.provider_name == "ollama"
    assert provider.model_name == "qwen2.5:7b"


def test_provider_factory_openai_and_groq():
    settings_groq = Settings(llm_provider="groq", llm_model="llama-3.1-70b", groq_api_key="gsk-fake")
    provider_groq = get_llm_provider(settings_groq)
    assert isinstance(provider_groq, OpenAICompatibleProvider)
    assert provider_groq.provider_name == "groq"

    settings_openai = Settings(llm_provider="openai", llm_model="gpt-4o", openai_api_key="sk-fake")
    provider_openai = get_llm_provider(settings_openai)
    assert isinstance(provider_openai, OpenAICompatibleProvider)
    assert provider_openai.provider_name == "openai"


def test_provider_factory_invalid():
    settings = Settings(llm_provider="mock")
    settings.llm_provider = "unsupported_provider"
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        get_llm_provider(settings)
