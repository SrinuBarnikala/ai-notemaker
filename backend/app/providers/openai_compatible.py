import asyncio
import logging
import time
from typing import Optional
import httpx
from backend.app.providers.base import LLMProvider

logger = logging.getLogger(__name__)

# Optional request parameters that some models reject; only these may be dropped on a 400.
_OPTIONAL_PARAMS = ("temperature", "response_format")
_UNSUPPORTED_CODES = ("unsupported_parameter", "unsupported_value")


def _error_body(response: httpx.Response) -> dict:
    """Returns the structured `error` object of an API error response, or {} if absent."""
    try:
        err = response.json().get("error")
    except Exception:
        return {}
    return err if isinstance(err, dict) else {}


def _rejected_optional_param(response: httpx.Response, payload: dict) -> Optional[str]:
    """
    Returns the optional parameter a 400 response explicitly rejects as unsupported, else None.
    Relies on the structured error (`code` / `param`), so unrelated 400s are never matched.
    """
    err = _error_body(response)
    code, param = err.get("code"), err.get("param")
    if code == "json_validate_failed":  # Groq: JSON-mode output failed validation
        return "response_format" if "response_format" in payload else None
    if param not in _OPTIONAL_PARAMS or param not in payload:
        return None
    message = str(err.get("message") or "").lower()
    if code in _UNSUPPORTED_CODES or "not supported" in message or "unsupported" in message:
        return param
    return None


def _api_error_summary(response: httpx.Response) -> str:
    err = _error_body(response)
    if not err:
        return response.text[:300]
    tags = " ".join(f"{k}={err[k]}" for k in ("code", "param") if err.get(k))
    return (f"{tags}: " if tags else "") + str(err.get("message") or "")[:300]


class OpenAICompatibleProvider(LLMProvider):
    """
    LLM provider for OpenAI and OpenAI-compatible endpoints (e.g. Groq, vLLM, Ollama OpenAI endpoint).
    Includes bounded retries with exponential backoff for transient failures (429, 5xx, timeouts).

    `max_tokens_param` names the request key used for an output limit: Groq and most
    compatible servers use `max_tokens`; OpenAI's newer models require `max_completion_tokens`.
    `send_temperature=False` omits `temperature` from requests, for models that only accept
    their default (e.g. gpt-6-luna), so every call doesn't pay for a rejected first request.
    """

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        model_name: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        timeout: float = 60.0,
        provider_label: str = "openai",
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_tokens_param: str = "max_tokens",
        send_temperature: bool = True,
    ):
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._api_key = api_key or ""
        self._timeout = timeout
        self._provider_label = provider_label
        self._max_retries = max_retries
        self._initial_delay = initial_delay
        self._backoff_factor = backoff_factor
        self._max_tokens_param = max_tokens_param
        self._send_temperature = send_temperature

    @property
    def provider_name(self) -> str:
        return self._provider_label

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
    ) -> str:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model_name,
            "messages": messages,
        }
        if self._send_temperature:
            payload["temperature"] = temperature
        if max_tokens:
            payload[self._max_tokens_param] = max_tokens
        if response_format:
            payload["response_format"] = response_format

        last_error = None
        dropped_param = False  # an unsupported-parameter fallback happens at most once per request
        # One spare iteration so the single fallback never consumes a transient-retry attempt.
        for attempt in range(self._max_retries + 2):
            t0 = time.time()
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    elapsed = time.time() - t0

                    # Check for transient HTTP status codes (429, 500, 502, 503, 504)
                    if response.status_code in (429, 500, 502, 503, 504):
                        err_text = response.text[:200]
                        if attempt < self._max_retries:
                            retry_after = response.headers.get("Retry-After")
                            try:
                                delay = min(float(retry_after), 10.0) if retry_after else min(self._initial_delay * (self._backoff_factor ** attempt), 10.0)
                            except (ValueError, TypeError):
                                delay = min(self._initial_delay * (self._backoff_factor ** attempt), 10.0)
                            logger.warning(
                                "[%s] Transient HTTP %d (attempt %d/%d, elapsed %.2fs). Retrying in %.2fs... Error: %s",
                                self._provider_label, response.status_code, attempt + 1, self._max_retries + 1, elapsed, delay, err_text
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            logger.error(
                                "[%s] Exceeded retries on HTTP %d (attempt %d/%d). Error: %s",
                                self._provider_label, response.status_code, attempt + 1, self._max_retries + 1, err_text
                            )
                            response.raise_for_status()

                    # A 400 that explicitly rejects one optional parameter: retry once without only that parameter
                    if response.status_code == 400 and not dropped_param:
                        rejected = _rejected_optional_param(response, payload)
                        if rejected:
                            logger.warning(
                                "[%s] Provider rejected optional parameter '%s' with 400. Retrying once without it...",
                                self._provider_label, rejected
                            )
                            payload = {k: v for k, v in payload.items() if k != rejected}
                            dropped_param = True
                            continue

                    response.raise_for_status()
                    data = response.json()
                    choices = data.get("choices", [])
                    if not choices:
                        return ""
                    content = choices[0].get("message", {}).get("content", "")
                    logger.debug(
                        "[%s] Generation succeeded (model: %s, attempt: %d, latency: %.2fs)",
                        self._provider_label, self._model_name, attempt + 1, elapsed
                    )
                    return content

            except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as err:
                elapsed = time.time() - t0
                last_error = err
                if attempt < self._max_retries:
                    delay = min(self._initial_delay * (self._backoff_factor ** attempt), 10.0)
                    logger.warning(
                        "[%s] Transient network/timeout error (attempt %d/%d, elapsed %.2fs): %s. Retrying in %.2fs...",
                        self._provider_label, attempt + 1, self._max_retries + 1, elapsed, err, delay
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        "[%s] Exceeded retries on network/timeout error: %s",
                        self._provider_label, err
                    )
                    raise RuntimeError(f"{self._provider_label} provider timeout/network error: {err}") from err
            except httpx.HTTPStatusError as err:
                # Permanent HTTP errors (400, 401, 403, 404): DO NOT retry
                logger.error(
                    "[%s] Permanent HTTP %d error: %s. Not retrying.",
                    self._provider_label, err.response.status_code, err.response.text[:300]
                )
                detail = ""
                if err.response.status_code in (400, 404, 422):  # request-shape errors; never auth errors
                    detail = f" - {_api_error_summary(err.response)}"
                raise RuntimeError(f"{self._provider_label} provider error: {err}{detail}") from err
            except Exception as err:
                logger.error("[%s] Unexpected generation error: %s", self._provider_label, err)
                raise RuntimeError(f"{self._provider_label} unexpected error: {err}") from err

        if last_error:
            raise RuntimeError(f"{self._provider_label} provider failed after {self._max_retries} retries: {last_error}") from last_error
        return ""

    async def health_check(self) -> bool:
        url = f"{self._base_url}/models"
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url, headers=headers)
                return response.status_code == 200
        except Exception:
            return False
