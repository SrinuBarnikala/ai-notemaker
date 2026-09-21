from functools import lru_cache
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_title: str = "Personalized Technical Note Maker API"
    app_version: str = "0.1.0"

    database_url: str = "sqlite:///./data/app.db"

    llm_provider: Literal["ollama", "groq", "openai", "mock"] = "ollama"
    llm_model: str = "qwen2.5:7b"
    llm_timeout_seconds: float = 60.0

    ollama_base_url: str = "http://localhost:11434"

    groq_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
