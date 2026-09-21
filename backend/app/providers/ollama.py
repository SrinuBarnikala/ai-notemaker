import logging
from typing import Optional
import httpx
from backend.app.providers.base import LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """
    LLM provider connecting to local or remote Ollama instance.
    """

    def __init__(self, base_url: str = "http://localhost:11434", model_name: str = "qwen2.5:7b", timeout: float = 60.0):
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        return "ollama"

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
        url = f"{self._base_url}/api/generate"
        payload = {
            "model": self._model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
        except httpx.HTTPError as err:
            logger.error("Ollama generation failed: %s", err)
            raise RuntimeError(f"Ollama provider error: {err}") from err

    async def health_check(self) -> bool:
        url = f"{self._base_url}/api/version"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url)
                return response.status_code == 200
        except Exception:
            return False
