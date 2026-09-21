from backend.app.config import Settings, get_settings
from backend.app.providers.base import LLMProvider
from backend.app.providers.ollama import OllamaProvider
from backend.app.providers.openai_compatible import OpenAICompatibleProvider
from backend.app.providers.mock import MockLLMProvider


def get_llm_provider(settings: Settings = None) -> LLMProvider:
    """
    Factory function to return the configured LLM provider instance.
    """
    if settings is None:
        settings = get_settings()

    provider_type = settings.llm_provider.lower()

    if provider_type == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model_name=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
        )
    elif provider_type == "groq":
        return OpenAICompatibleProvider(
            base_url="https://api.groq.com/openai/v1",
            model_name=settings.llm_model,
            api_key=settings.groq_api_key,
            timeout=settings.llm_timeout_seconds,
            provider_label="groq",
        )
    elif provider_type == "openai":
        return OpenAICompatibleProvider(
            base_url=settings.openai_base_url,
            model_name=settings.llm_model,
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
            provider_label="openai",
        )
    elif provider_type == "mock":
        return MockLLMProvider(
            model_name=settings.llm_model,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {provider_type}")
