"""Deterministic helpers for Knowledge Discovery tests: a scripted LLM provider and JSON builders."""
import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from backend.app.providers.base import LLMProvider

GARBAGE = "Mocked LLM response"


@dataclass
class Sleep:
    """Queued response that is returned only after `seconds` (cancellable, e.g. by a deadline)."""
    seconds: float
    text: str = GARBAGE


@dataclass
class Gate:
    """Queued response that blocks inside generate() until the test calls gate.release.set()."""
    text: str = GARBAGE
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)


class ScriptedProvider(LLMProvider):
    """
    Returns queued responses in order (strings, or Exceptions to raise) and records every prompt.
    When the queue is empty it returns unusable text, like the default mock provider.
    """

    def __init__(self, responses: Optional[List[Union[str, Exception]]] = None, default: str = GARBAGE):
        self.queue: List[Any] = list(responses or [])
        self.system_prompts: List[Optional[str]] = []
        self.default = default
        self.prompts: List[str] = []

    @property
    def provider_name(self) -> str:
        return "scripted"

    @property
    def model_name(self) -> str:
        return "scripted-model"

    def push(self, *items: Union[str, Exception]) -> "ScriptedProvider":
        self.queue.extend(items)
        return self

    @property
    def calls(self) -> int:
        return len(self.prompts)

    async def generate(self, prompt, system_prompt=None, temperature=0.7, max_tokens=None, response_format=None) -> str:
        self.prompts.append(prompt)
        self.system_prompts.append(system_prompt)
        item = self.queue.pop(0) if self.queue else self.default
        if isinstance(item, Exception):
            raise item
        if isinstance(item, Sleep):
            await asyncio.sleep(item.seconds)
            return item.text
        if isinstance(item, Gate):
            item.entered.set()
            await item.release.wait()
            return item.text
        return item

    async def health_check(self) -> bool:
        return True


def finding(value: str, basis: str = "stated", evidence: Optional[str] = None) -> Dict[str, Any]:
    return {"value": value, "basis": basis, "evidence": evidence}


def opening(question: str, focus: str = "Mental model") -> str:
    return json.dumps({"focus": focus, "next_question": question, "reasoning": "test"})


def turn(
    state: Optional[Dict[str, Any]] = None,
    question: Optional[str] = "What would you like to be able to do with it?",
    ready: bool = False,
    assessment: Optional[str] = "The learner gave a partial explanation.",
    finish_reason: str = "",
    focus: str = "Next focus",
) -> str:
    return json.dumps({
        "state": state if state is not None else {},
        "assessment": assessment,
        "ready_to_finish": ready,
        "finish_reason": finish_reason,
        "focus": focus,
        "next_question": None if ready else question,
        "reasoning": "test",
    })


def rewrite(question: str, focus: str = "Rewritten") -> str:
    return json.dumps({"focus": focus, "next_question": question})


def profile_json(summary: str = "The learner understands the basics and wants implementation depth.") -> str:
    return json.dumps({
        "overall_confidence": "intermediate",
        "summary": summary,
        "concepts": [{"name": "Core idea", "level": "moderate", "category": "partially_known", "notes": "Explained partly"}],
        "misconceptions": [],
        "gaps": ["Internal mechanics"],
    })
