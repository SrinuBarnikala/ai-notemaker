import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings, get_settings
from backend.app.main import app


@pytest.fixture
def test_settings():
    return Settings(
        app_env="test",
        database_url="sqlite:///:memory:",
        llm_provider="mock",
        llm_model="mock-qwen",
    )


@pytest.fixture
def client(test_settings):
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
