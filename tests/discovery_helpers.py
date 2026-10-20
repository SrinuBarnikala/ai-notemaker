"""Deterministic helpers for Knowledge Discovery tests: a scripted LLM provider and JSON builders."""
import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from backend.app.providers.base import LLMProvider

GARBAGE = "Mocked LLM response"
JUDGE_MARKER = "SEMANTIC REVIEW OF A QUESTION GROUP"


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


def judge(
    irrelevant: Optional[List[int]] = None,
    overlapping: Optional[List[List[int]]] = None,
    revisits: Optional[List[int]] = None,
    motive_matches: bool = True,
    purpose_served: bool = True,
    comment: str = "",
) -> str:
    """A semantic-review reply. With no arguments it passes the group untouched."""
    return json.dumps({
        "irrelevant_questions": irrelevant or [],
        "overlapping_pairs": overlapping or [],
        "revisits_known": revisits or [],
        "motive_matches": motive_matches,
        "purpose_served": purpose_served,
        "comment": comment,
    })


class ScriptedProvider(LLMProvider):
    """
    Returns queued responses in order (strings, or Exceptions to raise) and records every prompt.
    When the queue is empty it returns unusable text (or calls `default` if that is a function), like the default
    mock provider. Semantic-review ("judge") calls are served from their own queue and, when that is empty, simply
    pass the group, so tests about ordinary model calls do not have to script them. `calls` and `prompts` cover
    ordinary calls only; `judge_calls` / `judge_prompts` cover reviews.
    """

    def __init__(self, responses: Optional[List[Union[str, Exception]]] = None, default: Any = GARBAGE):
        self.queue: List[Any] = list(responses or [])
        self.judge_queue: List[Any] = []
        self.system_prompts: List[Optional[str]] = []
        self.default = default
        self.judge_default: Any = judge()
        self.prompts: List[str] = []
        self.judge_prompts: List[str] = []

    @property
    def provider_name(self) -> str:
        return "scripted"

    @property
    def model_name(self) -> str:
        return "scripted-model"

    def push(self, *items: Union[str, Exception]) -> "ScriptedProvider":
        self.queue.extend(items)
        return self

    def push_judge(self, *items: Union[str, Exception]) -> "ScriptedProvider":
        self.judge_queue.extend(items)
        return self

    @property
    def calls(self) -> int:
        return len(self.prompts)

    @property
    def judge_calls(self) -> int:
        return len(self.judge_prompts)

    async def generate(self, prompt, system_prompt=None, temperature=0.7, max_tokens=None, response_format=None) -> str:
        if JUDGE_MARKER in prompt:
            self.judge_prompts.append(prompt)
            item = self.judge_queue.pop(0) if self.judge_queue else self.judge_default
        else:
            self.prompts.append(prompt)
            self.system_prompts.append(system_prompt)
            item = self.queue.pop(0) if self.queue else (self.default(prompt) if callable(self.default) else self.default)
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


# ---------------------------------------------------------------------------
# JSON builders
# ---------------------------------------------------------------------------

_MOTIVE_COUNTER = {"n": 0}


def next_motive() -> str:
    """
    A different motive every time. The code rejects a repeated motive (token similarity 0.8), so each motive shares only a
    short template with the others and contributes five tokens found in no other motive.
    """
    _MOTIVE_COUNTER["n"] += 1
    n = _MOTIVE_COUNTER["n"]
    unique = " ".join(f"aspect{n}x{k}" for k in range(5))
    return f"I'd like to understand {unique} so the notes fit you."


def finding(value: str, basis: str = "stated", evidence: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    return {"value": value, "basis": basis, "evidence": evidence, **extra}


def core_state(quote: str, **overrides: Any) -> Dict[str, Any]:
    """A learner state in which every CORE dimension is established by `quote` (which must appear in the reply)."""
    state: Dict[str, Any] = {
        "intent": finding("Has a reason to learn it", "stated", quote),
        "desired_outcome": finding("Has an outcome in mind", "stated", quote),
        "explanation_preferences": [finding("Has a preferred way to learn", "stated", quote)],
        "understanding": finding("Has a working picture of it", "demonstrated", quote),
        "desired_depth": finding("Has a depth in mind", "stated", quote),
    }
    state.update(overrides)
    return state


def group(
    motive: Optional[str] = None,
    questions: Optional[List[Any]] = None,
    targets: Optional[List[str]] = None,
    rationale: str = "test",
) -> Dict[str, Any]:
    data: Dict[str, Any] = {"motive": motive if motive is not None else next_motive(), "questions": questions if questions is not None else [], "rationale": rationale}
    if targets is not None:
        data["targets"] = targets
    return data


def _group_from(question: Optional[str], subquestions: Any, motive: Optional[str], questions: Optional[List[Any]], targets: Optional[List[str]]) -> Dict[str, Any]:
    if questions is None:
        questions = ([question] if question else []) + list(subquestions or [])
    return group(motive=motive, questions=questions, targets=targets)


def opening(
    question: Optional[str] = None,
    focus: Optional[str] = None,
    subquestions: Any = None,
    *,
    motive: Optional[str] = None,
    questions: Optional[List[Any]] = None,
    targets: Optional[List[str]] = None,
) -> str:
    """An opening (or regeneration) reply: the group itself. `question`/`subquestions` build a plain peer-question list."""
    return json.dumps(_group_from(question, subquestions, motive, questions, targets))


# A regenerated group has the same shape as an opening one
rewrite = opening


def turn(
    state: Optional[Dict[str, Any]] = None,
    question: Optional[str] = "What would you like to be able to do with it?",
    ready: bool = False,
    assessment: Optional[str] = "The learner gave a partial explanation.",
    finish_reason: str = "",
    focus: str = "Next focus",
    subquestions: Any = None,
    *,
    motive: Optional[str] = None,
    questions: Optional[List[Any]] = None,
    targets: Optional[List[str]] = None,
    open_issues: Optional[List[Dict[str, Any]]] = None,
    dimension_notes: Optional[List[Dict[str, Any]]] = None,
    retractions: Optional[List[Dict[str, Any]]] = None,
    group_override: Any = "unset",
) -> str:
    """An analysis reply: the updated learner state plus (unless `ready`) the next question group."""
    if group_override != "unset":
        next_group = group_override
    elif ready:
        next_group = None
    else:
        next_group = _group_from(question, subquestions, motive, questions, targets)
    return json.dumps({
        "state": state if state is not None else {},
        "retractions": retractions or [],
        "dimension_notes": dimension_notes or [],
        "open_issues": open_issues or [],
        "assessment": assessment,
        "ready_to_finish": ready,
        "finish_reason": finish_reason,
        "group": next_group,
        "reasoning": "test",
    })


def profile_json(summary: str = "The learner understands the basics and wants implementation depth.") -> str:
    return json.dumps({
        "overall_confidence": "intermediate",
        "summary": summary,
        "concepts": [{"name": "Core idea", "level": "moderate", "category": "partially_known", "notes": "Explained partly"}],
        "misconceptions": [],
        "gaps": ["Internal mechanics"],
    })


# ---------------------------------------------------------------------------
# A model that always has something new to ask
# ---------------------------------------------------------------------------

_ADJECTIVES = ["gradual", "noisy", "layered", "sparse", "recursive", "stochastic", "modular", "latent", "adaptive", "robust",
               "sequential", "hierarchical", "iterative", "composable", "lossy", "bounded"]
_NOUNS = ["feedback", "boundaries", "sampling", "bottlenecks", "invariants", "gradients", "caching", "ordering", "scaling",
          "failures", "encoding", "ranking", "pruning", "merging", "routing", "indexing"]
_VERBS = ["explain", "sketch", "compare", "predict", "justify", "diagnose", "simplify", "extend"]


def distinct_group_model(
    questions_per_group: int = 1,
    finish_requests: bool = False,
    state: Optional[Dict[str, Any]] = None,
    targets: Optional[List[str]] = None,
):
    """
    A scripted model that always offers a new, clearly different group (it never repeats itself), so a test can drive a
    session all the way to the question budget. It answers the opening, analysis and regeneration prompts. With
    finish_requests=True it asks to finish on every turn (which the code must still refuse until the evidence rules
    are met).
    """
    counter = {"n": 0}

    def make() -> Dict[str, Any]:
        counter["n"] += 1
        n = counter["n"]
        motive = next_motive()
        qs = [
            f"How would you {_VERBS[(n + k) % 8]} {_ADJECTIVES[(n * 3 + k + 5) % 16]} {_NOUNS[(n * 7 + k * 3 + 2) % 16]} in your own words?"
            for k in range(questions_per_group)
        ]
        return group(motive=motive, questions=qs, targets=targets)

    def respond(prompt: str) -> str:
        g = make()
        if "Write ONE new question group" in prompt or "Write the FIRST question group" in prompt:
            return json.dumps(g)
        return json.dumps({
            "state": state or {}, "assessment": "noted", "ready_to_finish": finish_requests,
            "finish_reason": "", "group": None if finish_requests else g, "reasoning": "t",
            "retractions": [], "dimension_notes": [], "open_issues": [],
        })

    return respond
