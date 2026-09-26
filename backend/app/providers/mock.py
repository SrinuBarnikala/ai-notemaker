from typing import Optional
from backend.app.providers.base import LLMProvider


class MockLLMProvider(LLMProvider):
    """
    Mock LLM provider for deterministic tests and offline development.
    """

    def __init__(self, response_text: str = "Mocked LLM response", model_name: str = "mock-model"):
        self._response_text = response_text
        self._model_name = model_name
        self.last_prompt: Optional[str] = None
        self.last_system_prompt: Optional[str] = None
        self.is_healthy: bool = True

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self._model_name

    def set_response(self, text: str):
        self._response_text = text

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
    ) -> str:
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt
        self.last_response_format = response_format
        return self._response_text


    async def health_check(self) -> bool:
        return self.is_healthy
