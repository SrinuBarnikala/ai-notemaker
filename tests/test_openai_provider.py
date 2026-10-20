"""
Request-shape and error-handling tests for OpenAICompatibleProvider as configured for
OpenAI (gpt-6-luna) and Groq. All HTTP is mocked; keys below are placeholders, not real.
"""
import httpx
import pytest
from unittest.mock import patch

from backend.app.config import Settings
from backend.app.providers.factory import get_llm_provider
from backend.app.providers.openai_compatible import OpenAICompatibleProvider

FAKE_OPENAI_KEY = "test-openai-key-not-real"
FAKE_GROQ_KEY = "test-groq-key-not-real"
REQ = httpx.Request("POST", "https://example.test/v1/chat/completions")


def ok(content: str = "hello") -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]}, request=REQ)


def api_error(status: int, **error) -> httpx.Response:
    return httpx.Response(status, json={"error": error}, request=REQ)


def openai_provider(**overrides) -> OpenAICompatibleProvider:
    settings = Settings(
        llm_provider="openai",
        llm_model="gpt-6-luna",
        openai_api_key=FAKE_OPENAI_KEY,
        openai_base_url="https://api.openai.com/v1",
        **overrides,
    )
    return get_llm_provider(settings)


def generic_provider(**overrides) -> OpenAICompatibleProvider:
    """A directly-constructed provider using defaults (temperature IS sent); exercises the generic fallback paths."""
    return OpenAICompatibleProvider(api_key=FAKE_OPENAI_KEY, **overrides)


def groq_provider() -> OpenAICompatibleProvider:
    settings = Settings(llm_provider="groq", llm_model="openai/gpt-oss-20b", groq_api_key=FAKE_GROQ_KEY)
    return get_llm_provider(settings)


def sent(mock_post, index: int = 0) -> dict:
    return mock_post.call_args_list[index].kwargs["json"]


# ---------------------------------------------------------------- OpenAI

@pytest.mark.asyncio
async def test_openai_endpoint_model_auth_and_parsing():
    provider = openai_provider()
    assert provider.provider_name == "openai"
    assert provider.model_name == "gpt-6-luna"

    with patch("httpx.AsyncClient.post", side_effect=[ok("parsed text")]) as mock_post:
        result = await provider.generate(prompt="user text", system_prompt="system text", temperature=0.3)

    assert result == "parsed text"
    assert mock_post.call_args.args[0] == "https://api.openai.com/v1/chat/completions"
    assert mock_post.call_args.kwargs["headers"]["Authorization"] == f"Bearer {FAKE_OPENAI_KEY}"
    body = sent(mock_post)
    assert body["model"] == "gpt-6-luna"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


@pytest.mark.asyncio
async def test_openai_omits_temperature_so_no_failed_request_is_needed():
    with patch("httpx.AsyncClient.post", side_effect=[ok('{"ok": true}')]) as mock_post:
        result = await openai_provider().generate(
            prompt="p", temperature=0.3, response_format={"type": "json_object"}
        )

    assert result == '{"ok": true}'
    assert mock_post.call_count == 1  # first request succeeds; no rejected-temperature round trip
    body = sent(mock_post)
    assert "temperature" not in body
    assert body["response_format"] == {"type": "json_object"}  # JSON formatting is still requested
    assert body["model"] == "gpt-6-luna"


@pytest.mark.asyncio
async def test_default_provider_still_sends_temperature():
    with patch("httpx.AsyncClient.post", side_effect=[ok()]) as mock_post:
        await generic_provider().generate(prompt="p", temperature=0.4)
    assert sent(mock_post)["temperature"] == 0.4


@pytest.mark.asyncio
async def test_openai_uses_max_completion_tokens_when_limit_supplied():
    with patch("httpx.AsyncClient.post", side_effect=[ok()]) as mock_post:
        await openai_provider().generate(prompt="p", max_tokens=1234)
    body = sent(mock_post)
    assert body["max_completion_tokens"] == 1234
    assert "max_tokens" not in body


@pytest.mark.asyncio
async def test_openai_adds_no_output_limit_when_none_supplied():
    with patch("httpx.AsyncClient.post", side_effect=[ok()]) as mock_post:
        await openai_provider().generate(prompt="p")
    body = sent(mock_post)
    assert "max_completion_tokens" not in body
    assert "max_tokens" not in body


@pytest.mark.asyncio
async def test_generic_provider_retries_once_without_unsupported_temperature():
    rejected = api_error(
        400, code="unsupported_value", param="temperature",
        message="Unsupported value: 'temperature' does not support 0.3 with this model.",
    )
    with patch("httpx.AsyncClient.post", side_effect=[rejected, ok("recovered")]) as mock_post:
        result = await generic_provider(model_name="gpt-6-luna").generate(
            prompt="p", temperature=0.3, response_format={"type": "json_object"}
        )

    assert result == "recovered"
    assert mock_post.call_count == 2
    assert "temperature" in sent(mock_post, 0)
    retry_body = sent(mock_post, 1)
    assert "temperature" not in retry_body
    assert retry_body["response_format"] == {"type": "json_object"}  # only the rejected parameter is removed
    assert retry_body["model"] == "gpt-6-luna"


@pytest.mark.asyncio
async def test_openai_retries_once_without_unsupported_response_format():
    rejected = api_error(
        400, code=None, param="response_format",
        message="Invalid parameter: 'response_format' of type 'json_object' is not supported with this model.",
    )
    with patch("httpx.AsyncClient.post", side_effect=[rejected, ok("recovered")]) as mock_post:
        result = await openai_provider().generate(
            prompt="p", temperature=0.3, response_format={"type": "json_object"}
        )

    assert result == "recovered"
    assert mock_post.call_count == 2
    assert "temperature" not in sent(mock_post, 0)  # OpenAI provider never sent it
    retry_body = sent(mock_post, 1)
    assert "response_format" not in retry_body
    assert "temperature" not in retry_body


@pytest.mark.asyncio
async def test_openai_fallback_retry_happens_at_most_once():
    first = api_error(400, code="unsupported_value", param="temperature", message="Unsupported value: 'temperature'")
    second = api_error(
        400, code="unsupported_parameter", param="response_format",
        message="'response_format' is not supported with this model.",
    )
    with patch("httpx.AsyncClient.post", side_effect=[first, second, ok()]) as mock_post:
        with pytest.raises(RuntimeError) as exc_info:
            await generic_provider().generate(prompt="p", temperature=0.3, response_format={"type": "json_object"})

    assert mock_post.call_count == 2  # never a third request
    assert "response_format" in str(exc_info.value)


@pytest.mark.asyncio
async def test_openai_fallback_does_not_consume_transient_retry_budget():
    rejected = api_error(400, code="unsupported_value", param="temperature", message="Unsupported value: 'temperature'")
    provider = OpenAICompatibleProvider(api_key=FAKE_OPENAI_KEY, max_retries=0)
    with patch("httpx.AsyncClient.post", side_effect=[rejected, ok("recovered")]):
        assert await provider.generate(prompt="p", temperature=0.3) == "recovered"


@pytest.mark.asyncio
async def test_openai_unrelated_400_is_not_retried_and_keeps_detail():
    bad = api_error(400, code="invalid_type", param="messages", message="Invalid type for 'messages'.")
    with patch("httpx.AsyncClient.post", side_effect=[bad, ok()]) as mock_post:
        with pytest.raises(RuntimeError) as exc_info:
            await openai_provider().generate(prompt="p", temperature=0.3, response_format={"type": "json_object"})

    assert mock_post.call_count == 1
    assert "invalid_type" in str(exc_info.value)
    assert "messages" in str(exc_info.value)


@pytest.mark.asyncio
async def test_openai_out_of_range_temperature_is_a_malformed_request_not_retried():
    bad = api_error(
        400, code="decimal_above_max_value", param="temperature",
        message="Invalid 'temperature': decimal above maximum value.",
    )
    with patch("httpx.AsyncClient.post", side_effect=[bad, ok()]) as mock_post:
        with pytest.raises(RuntimeError):
            await generic_provider().generate(prompt="p", temperature=9.0)
    assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_openai_invalid_model_is_not_retried_and_keeps_detail():
    missing = api_error(404, code="model_not_found", message="The model `gpt-6-luna` does not exist.")
    with patch("httpx.AsyncClient.post", side_effect=[missing, ok()]) as mock_post:
        with pytest.raises(RuntimeError) as exc_info:
            await openai_provider().generate(prompt="p")
    assert mock_post.call_count == 1
    assert "model_not_found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_openai_auth_error_is_not_retried_and_detail_is_not_surfaced():
    unauthorized = api_error(
        401, code="invalid_api_key", message="Incorrect API key provided: test-openai-********.",
    )
    with patch("httpx.AsyncClient.post", side_effect=[unauthorized, ok()]) as mock_post:
        with pytest.raises(RuntimeError) as exc_info:
            await openai_provider().generate(prompt="p")
    assert mock_post.call_count == 1
    assert "401" in str(exc_info.value)
    assert "Incorrect API key" not in str(exc_info.value)  # auth error bodies are not copied into exceptions


# ---------------------------------------------------------------- Groq (existing behavior)

@pytest.mark.asyncio
async def test_groq_endpoint_model_auth_and_parsing():
    provider = groq_provider()
    assert provider.provider_name == "groq"
    assert provider.model_name == "openai/gpt-oss-20b"

    with patch("httpx.AsyncClient.post", side_effect=[ok("groq text")]) as mock_post:
        result = await provider.generate(prompt="p", system_prompt="s")

    assert result == "groq text"
    assert mock_post.call_args.args[0] == "https://api.groq.com/openai/v1/chat/completions"
    assert mock_post.call_args.kwargs["headers"]["Authorization"] == f"Bearer {FAKE_GROQ_KEY}"
    assert sent(mock_post)["model"] == "openai/gpt-oss-20b"


@pytest.mark.asyncio
async def test_groq_keeps_max_tokens_parameter():
    with patch("httpx.AsyncClient.post", side_effect=[ok()]) as mock_post:
        await groq_provider().generate(prompt="p", max_tokens=777)
    body = sent(mock_post)
    assert body["max_tokens"] == 777
    assert "max_completion_tokens" not in body


@pytest.mark.asyncio
async def test_groq_still_sends_temperature():
    with patch("httpx.AsyncClient.post", side_effect=[ok()]) as mock_post:
        await groq_provider().generate(prompt="p", temperature=0.3)
    assert sent(mock_post)["temperature"] == 0.3


@pytest.mark.asyncio
async def test_groq_json_validate_failed_still_retries_once_without_response_format():
    rejected = api_error(
        400, code="json_validate_failed", type="invalid_request_error",
        message="Failed to generate JSON. Please adjust your prompt.",
    )
    with patch("httpx.AsyncClient.post", side_effect=[rejected, ok('{"a": 1}')]) as mock_post:
        result = await groq_provider().generate(
            prompt="p", temperature=0.3, response_format={"type": "json_object"}
        )

    assert result == '{"a": 1}'
    assert mock_post.call_count == 2
    assert "response_format" in sent(mock_post, 0)
    retry_body = sent(mock_post, 1)
    assert "response_format" not in retry_body
    assert retry_body["temperature"] == 0.3
