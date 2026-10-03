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

    # Authentication & Session Security
    jwt_secret_key: str = "dev-secret-key-personalized-technical-notemaker-replace-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    auth_cookie_name: str = "auth_token"
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"


@lru_cache
def get_settings() -> Settings:
    return Settings()
