import logging
from typing import Optional
import httpx
from backend.app.providers.base import LLMProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    """
    LLM provider for OpenAI and OpenAI-compatible endpoints (e.g. Groq, vLLM, Ollama OpenAI endpoint).
    """

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        model_name: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        timeout: float = 60.0,
        provider_label: str = "openai",
    ):
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._api_key = api_key or ""
        self._timeout = timeout
        self._provider_label = provider_label

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

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices", [])
                if not choices:
                    return ""
                return choices[0].get("message", {}).get("content", "")
        except httpx.HTTPError as err:
            logger.error("%s generation failed: %s", self._provider_label, err)
            raise RuntimeError(f"{self._provider_label} provider error: {err}") from err

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
