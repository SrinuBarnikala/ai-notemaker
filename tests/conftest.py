import atexit
import os
import shutil
import tempfile
from pathlib import Path

# The database engine is created when backend.app.db.session is first imported, so the
# test database must be configured in the environment before anything from `backend` loads.
# Environment variables take precedence over the .env file, so the dev database is never used.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="notemaker-tests-")
atexit.register(shutil.rmtree, _TEST_DB_DIR, ignore_errors=True)
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TEST_DB_DIR, 'test.db').as_posix()}"

import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings, get_settings
from backend.app.db.session import engine
from backend.app.main import app

from backend.app.db.session import Base, ensure_schema_migrations

# Fail loudly instead of silently writing test data into the development database.
assert _TEST_DB_DIR.replace("\\", "/") in str(engine.url).replace("\\", "/"), (
    f"Tests must use an isolated database, but the engine points at {engine.url}"
)


# Create the schema up front so tests that use the database directly (or an async client that does not
# run the app lifespan) never depend on another test having started the app first.
Base.metadata.create_all(bind=engine)
ensure_schema_migrations()


@pytest.fixture
async def async_client(test_settings):
    import httpx

    app.dependency_overrides[get_settings] = lambda: test_settings
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def scripted(monkeypatch):
    """A ScriptedProvider wired into every stage that talks to the LLM, with retry delays disabled."""
    from backend.app.discovery import workflow
    from discovery_helpers import ScriptedProvider

    provider = ScriptedProvider()
    monkeypatch.setattr(workflow, "RETRY_BACKOFF_SECONDS", 0)
    for target in (
        "backend.app.api.discovery.get_llm_provider",
        "backend.app.profile.generator.get_llm_provider",
        "backend.app.architecture.generator.get_llm_provider",
        "backend.app.note.generator.get_llm_provider",
    ):
        monkeypatch.setattr(target, lambda settings=None, _p=provider: _p)
    return provider


@pytest.fixture
def test_settings():
    return Settings(
        app_env="test",
        database_url="sqlite:///:memory:",
        llm_provider="mock",
        llm_model="mock-qwen",
        discovery_max_questions=10,
    )


@pytest.fixture
def client(test_settings):
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
