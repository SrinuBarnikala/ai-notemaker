import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from backend.app.core.json_utils import strip_code_fence, find_bracket_span, try_parse_json
from backend.app.discovery.state import DiscoveryLearnerState, Retraction, parse_retractions, parse_state
from backend.app.discovery.text import QUESTION_MARKS, jaccard, tokenize

logger = logging.getLogger(__name__)

MAX_QUESTION_CHARS = 600
MIN_QUESTION_CHARS = 8
DUPLICATE_SIMILARITY = 0.75
MAX_FOCUS_CHARS = 200


class DiscoveryParseError(ValueError):
    """Model output was unusable (malformed JSON or missing required parts)."""


class OpeningParsed(BaseModel):
    question: str = Field(..., min_length=MIN_QUESTION_CHARS)
    focus: str = ""
    reasoning: str = ""


class TurnParsed(BaseModel):
    state: DiscoveryLearnerState
    assessment: Optional[str] = None
    ready_to_finish: bool = False
    finish_reason: str = ""
    focus: str = ""
    next_question: Optional[str] = None
    reasoning: str = ""
    retractions: List[Retraction] = Field(default_factory=list)


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Extracts and parses a JSON object from raw LLM text, safely handling
    markdown backticks, preamble, and postscript comments.
    """
    clean = strip_code_fence(text)

    # Find boundaries of the outermost JSON object
    span = find_bracket_span(clean, "{", "}")
    if span:
        parsed = try_parse_json(clean[span[0] : span[1] + 1])
        if parsed is not None:
            return parsed

    # Direct parse attempt
    return try_parse_json(clean)


def _text(value: Any, limit: int = MAX_QUESTION_CHARS) -> str:
    return re.sub(r"[ \t]+", " ", str(value or "")).strip()[:limit]


def _focus(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:MAX_FOCUS_CHARS]


def _require_object(raw_text: str) -> Dict[str, Any]:
    data = extract_json_object(raw_text or "")
    if not isinstance(data, dict):
        raise DiscoveryParseError("the reply was not a valid JSON object")
    return data


def parse_opening(raw_text: str) -> OpeningParsed:
    data = _require_object(raw_text)
    question = _text(data.get("next_question") or data.get("question"))
    if len(question) < MIN_QUESTION_CHARS:
        raise DiscoveryParseError('"next_question" is missing or too short')
    return OpeningParsed(
        question=question,
        focus=_focus(data.get("focus") or data.get("concept_target")),
        reasoning=_text(data.get("reasoning"), 400),
    )


def parse_turn(raw_text: str, topic: str) -> TurnParsed:
    data = _require_object(raw_text)
    if not isinstance(data.get("state"), dict):
        raise DiscoveryParseError('"state" is missing or not an object')

    ready = data.get("ready_to_finish")
    if not isinstance(ready, bool):
        ready = str(ready).strip().lower() == "true"

    question = _text(data.get("next_question")) or None
    if not ready and not question:
        raise DiscoveryParseError('"next_question" is required when "ready_to_finish" is false')

    assessment = _text(data.get("assessment"), 500) or None
    return TurnParsed(
        state=parse_state(data["state"], topic),
        assessment=assessment,
        ready_to_finish=ready,
        finish_reason=_text(data.get("finish_reason"), 400),
        focus=_focus(data.get("focus")),
        next_question=None if ready else question,
        reasoning=_text(data.get("reasoning"), 400),
        retractions=parse_retractions(data.get("retractions")),
    )


_LABEL_PREFIX = re.compile(r"^\s*(?:next\s+)?question\s*[:\-]\s*", re.IGNORECASE)


def parse_plain_question(raw_text: str) -> Tuple[str, str]:
    """
    Reads a question from a reply that should be plain text, tolerating a JSON object or code
    fences. Returns (question, focus). Text without a question mark is rejected, so unusable
    output (for example "Mocked LLM response") is never shown to a learner as a question.
    """
    data = extract_json_object(raw_text or "")
    if isinstance(data, dict):
        candidate = _text(data.get("next_question") or data.get("question"))
        focus = _focus(data.get("focus"))
    else:
        candidate = _text(strip_code_fence(raw_text or ""))
        focus = ""
    candidate = _LABEL_PREFIX.sub("", candidate).strip().strip("`").strip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in "\"'":
        candidate = candidate[1:-1].strip()
    candidate = re.sub(r"[ \t]*\n[ \t]*", " ", candidate).strip()
    if len(candidate) < MIN_QUESTION_CHARS:
        raise DiscoveryParseError("the reply was empty or too short to be a question")
    if not any(mark in candidate for mark in QUESTION_MARKS):
        raise DiscoveryParseError("the reply did not contain a question")
    return candidate, focus


# ---------------------------------------------------------------------------
# One-question and no-repeat guard
# ---------------------------------------------------------------------------

_LIST_LINE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+", re.MULTILINE)
_QUOTED = re.compile(r'"[^"]*"|“[^”]*”')


def question_problem(question: Optional[str], asked_questions: List[str]) -> Optional[str]:
    """Returns why a question can't be shown to the learner, or None if it is acceptable."""
    q = (question or "").strip()
    if len(q) < MIN_QUESTION_CHARS:
        return "it is empty or too short"
    if len(q) > MAX_QUESTION_CHARS:
        return "it is too long for a single conversational question"
    if len(_LIST_LINE.findall(q)) >= 2:
        return "it is formatted as a list of questions"
    # A quoted phrase (e.g. the learner's own question) may contain "?" without being a second question.
    unquoted = _QUOTED.sub(" ", q)
    if sum(unquoted.count(mark) for mark in QUESTION_MARKS) > 1:
        return "it asks more than one question"
    new_tokens = tokenize(q)
    for earlier in asked_questions:
        if jaccard(new_tokens, tokenize(earlier)) >= DUPLICATE_SIMILARITY:
            return "it repeats an earlier question"
    return None


# ---------------------------------------------------------------------------
# Flagged fallback question (used only when the model cannot supply a usable one)
# ---------------------------------------------------------------------------

def _topic_phrase(topic: str) -> str:
    topic = re.sub(r"\s+", " ", (topic or "").replace('"', "'")).strip().rstrip("?").strip()
    if not topic:
        return "this topic"
    return f'"{topic}"' if len(topic) <= 120 else "this topic"


def fallback_question(
    topic: str,
    state: Optional[DiscoveryLearnerState],
    asked_questions: List[str],
) -> Tuple[str, str]:
    """
    A generic question chosen by what is still unknown, parameterised by the learner's
    topic. It never decides anything about the learner. Returns (question, focus).
    """
    t = _topic_phrase(topic)
    candidates: List[Tuple[str, str, bool]] = [
        (
            f"In your own words, what do you already understand about {t}? A rough idea is completely fine.",
            "Current understanding",
            state is None or not state.is_confirmed("understanding"),
        ),
        (
            f"What are you hoping to be able to do or understand once you've learned about {t}?",
            "Learning goal",
            state is None or not state.is_confirmed("intent"),
        ),
        (
            f"How deep would you like to go with {t}: a quick overview, a solid conceptual understanding, or the full technical detail?",
            "Desired depth",
            state is None or not state.is_confirmed("desired_depth"),
        ),
        (
            "When a new idea finally clicks for you, what usually helps most: diagrams, analogies, worked examples, code, or math?",
            "Explanation style",
            state is None or not state.explanation_preferences,
        ),
        (
            f"Is there anything about {t} you'd especially like your notes to focus on?",
            "Focus areas",
            True,
        ),
        (
            "Is there anything else you'd like me to know before I prepare your notes?",
            "Anything else",
            True,
        ),
    ]
    for question, focus, needed in candidates:
        if needed and question_problem(question, asked_questions) is None:
            return question, focus
    question, focus, _ = candidates[-1]
    return question, focus
