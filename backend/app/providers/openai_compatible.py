import asyncio
import logging
import time
from typing import Optional
import httpx
from backend.app.providers.base import LLMProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    """
    LLM provider for OpenAI and OpenAI-compatible endpoints (e.g. Groq, vLLM, Ollama OpenAI endpoint).
    Includes bounded retries with exponential backoff for transient failures (429, 5xx, timeouts).
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
    ):
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._api_key = api_key or ""
        self._timeout = timeout
        self._provider_label = provider_label
        self._max_retries = max_retries
        self._initial_delay = initial_delay
        self._backoff_factor = backoff_factor

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
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if response_format:
            payload["response_format"] = response_format

        last_error = None
        for attempt in range(self._max_retries + 1):
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

                    # Handle 400 with response_format: retry once without response_format if rejected
                    if response.status_code == 400 and "response_format" in payload:
                        err_text = response.text
                        if "json_validate_failed" in err_text or "response_format" in err_text:
                            logger.warning(
                                "[%s] Provider rejected response_format with 400. Retrying without response_format...",
                                self._provider_label
                            )
                            payload_no_rf = dict(payload)
                            payload_no_rf.pop("response_format", None)
                            payload = payload_no_rf
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
                raise RuntimeError(f"{self._provider_label} provider error: {err}") from err
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
