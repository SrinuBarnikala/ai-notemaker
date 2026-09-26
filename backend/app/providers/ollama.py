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
        response_format: Optional[dict] = None,
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
        if response_format:
            payload["format"] = "json"


        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
        except httpx.HTTPStatusError as err:
            if err.response.status_code == 404:
                logger.warning(
                    "Ollama model '%s' not found on server at %s. Preserving fallback.",
                    self._model_name, self._base_url
                )
                raise RuntimeError(
                    f"Ollama model '{self._model_name}' is not pulled on the server. "
                    f"Run 'ollama pull {self._model_name}'."
                ) from None
            logger.warning("Ollama HTTP status error %s: %s", err.response.status_code, err)
            raise RuntimeError(f"Ollama provider HTTP error {err.response.status_code}") from None
        except httpx.HTTPError as err:
            logger.warning("Ollama connection error: %s", err)
            raise RuntimeError("Ollama connection failed") from None

    async def check_model_availability(self) -> dict:
        """
        Queries Ollama /api/tags to detect if Ollama server is running
        and whether the configured model is pulled.
        Returns:
            {
                "server_reachable": bool,
                "model_available": bool,
                "detail": str,
                "available_models": list[str],
            }
        """
        url = f"{self._base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(url)
                if res.status_code != 200:
                    return {
                        "server_reachable": False,
                        "model_available": False,
                        "detail": f"Ollama returned HTTP status {res.status_code}.",
                        "available_models": [],
                    }
                data = res.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                
                normalized_target = self._model_name.lower().strip()
                target_base = normalized_target.split(":")[0] if ":" in normalized_target else normalized_target
                
                match_found = False
                for m in models:
                    m_lower = m.lower().strip()
                    if m_lower == normalized_target or m_lower.startswith(f"{target_base}:") or m_lower == f"{target_base}:latest":
                        match_found = True
                        break

                if match_found:
                    return {
                        "server_reachable": True,
                        "model_available": True,
                        "detail": f"Model '{self._model_name}' is available in local Ollama.",
                        "available_models": models,
                    }
                else:
                    return {
                        "server_reachable": True,
                        "model_available": False,
                        "detail": (
                            f"Ollama server is active, but configured model '{self._model_name}' is not pulled. "
                            f"Run 'ollama pull {self._model_name}' to enable local AI inference."
                        ),
                        "available_models": models,
                    }
        except Exception:
            return {
                "server_reachable": False,
                "model_available": False,
                "detail": "Ollama server connection failed.",
                "available_models": [],
            }

    async def health_check(self) -> bool:
        url = f"{self._base_url}/api/version"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url)
                return response.status_code == 200
        except Exception:
            return False
