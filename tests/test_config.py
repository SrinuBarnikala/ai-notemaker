from backend.app.config import Settings


def test_settings_defaults():
    settings = Settings()
    assert settings.app_title == "Personalized Technical Note Maker API"
    assert settings.app_port == 8000
    assert settings.llm_provider in ["ollama", "groq", "openai", "mock"]
    assert settings.database_url.startswith("sqlite")


def test_settings_custom_override():
    settings = Settings(
        app_env="production",
        app_port=9000,
        llm_provider="mock",
        llm_model="custom-model",
    )
    assert settings.app_env == "production"
    assert settings.app_port == 9000
    assert settings.llm_provider == "mock"
    assert settings.llm_model == "custom-model"
