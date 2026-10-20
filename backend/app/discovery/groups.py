"""
Question groups: a motive plus zero to five PEER questions, answered together in one free-text reply.

There is no "main question" and no subordinate "subquestions". The motive is a short statement of what the system
wants to understand and why; every question in the group serves it, and each is worth exactly one unit of the
question budget (the motive is free).

Storage: DiscoveryInteraction.motive and DiscoveryInteraction.questions (a JSON list, "[]" for a group with none).
DiscoveryInteraction.question_text keeps a readable flattened rendering so older consumers still see text.
Rows written before this model existed (a single question, or a v2 "card" with subquestions) have no `questions`
value; they are normalized when read, never rewritten.
"""
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from backend.app.discovery.dimensions import (
    CONFUSIONS, CONSTRAINTS, COMMITMENT, DESIRED_DEPTH, DESIRED_OUTCOME, DIMENSIONS, FAMILIARITY,
    LEARNING_APPROACH, LEARNING_INTENTION, MENTAL_MODEL,
)
from backend.app.discovery.text import QUESTION_MARKS, jaccard, tokenize

MAX_QUESTIONS_PER_GROUP = 5
# A group with no questions is an open invitation, costs nothing, and could therefore repeat forever. So it is
# rationed, and never allowed twice in a row.
MAX_ZERO_QUESTION_GROUPS = 2
MAX_TARGETS = 3

MIN_QUESTION_CHARS = 8
MAX_QUESTION_CHARS = 300
MIN_MOTIVE_CHARS = 12
MAX_MOTIVE_CHARS = 280
QUESTION_DUPLICATE_SIMILARITY = 0.75
MOTIVE_DUPLICATE_SIMILARITY = 0.8

_NUMBERING = re.compile(r"^\s*(?:\(?\d+[.)]|[-*•])\s*")
_QUOTED = re.compile(r'"[^"]*"|“[^”]*”')
_LIST_LINE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+", re.MULTILINE)


@dataclass
class QuestionGroup:
    motive: str
    questions: List[str] = field(default_factory=list)
    targets: List[str] = field(default_factory=list)   # dimension ids this motive serves
    rationale: str = ""                                # why this motive was chosen now


@dataclass
class NormalizedGroup:
    """A stored interaction read in the current model, whatever era it was written in."""
    motive: Optional[str]
    questions: List[str]
    legacy: bool

    @property
    def units(self) -> int:
        return len(self.questions)


@dataclass
class GroupValidation:
    group: Optional[QuestionGroup]
    problems: List[str] = field(default_factory=list)  # non-empty: the group must NOT be shown
    notes: List[str] = field(default_factory=list)     # things that were dropped or trimmed to make it valid


# ---------------------------------------------------------------------------
# Storage and legacy normalization
# ---------------------------------------------------------------------------

def dump_questions(questions: Sequence[str]) -> str:
    """JSON for the column. Always a list ("[]" for none), so a stored group is distinguishable from a legacy row."""
    return json.dumps([q for q in questions if isinstance(q, str) and q.strip()], ensure_ascii=False)


def _load_str_list(raw: Optional[str], limit: int) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [s.strip() for s in data if isinstance(s, str) and s.strip()][:limit]


def group_text(motive: Optional[str], questions: Sequence[str]) -> str:
    """Readable flattened form kept in question_text for consumers that only know a single text column."""
    lines = [motive] if motive else []
    lines.extend(f"- {q}" for q in questions)
    return "\n".join(lines)


def normalize_interaction(
    question_text: str,
    subquestions_raw: Optional[str],
    motive: Optional[str],
    questions_raw: Optional[str],
) -> NormalizedGroup:
    """
    Current-model view of a stored row.
    - Written under this model (`questions` is a JSON list): motive and questions as stored.
    - Legacy (`questions` is NULL): a single question, or a v2 card. There was no motive, and nothing is invented
      for it: the old main question and its subquestions are simply peer questions, one budget unit each.
    """
    if questions_raw is not None:
        return NormalizedGroup(motive=(motive or None), questions=_load_str_list(questions_raw, 50), legacy=False)
    legacy_questions = [question_text.strip()] if (question_text or "").strip() else []
    legacy_questions += _load_str_list(subquestions_raw, 3)
    return NormalizedGroup(motive=None, questions=legacy_questions, legacy=True)


# ---------------------------------------------------------------------------
# Deterministic validation
# ---------------------------------------------------------------------------

def sanitize_question(text: Any) -> str:
    """Remove numbering or bullets (the UI shows peer questions unnumbered) and collapse whitespace."""
    return re.sub(r"\s+", " ", _NUMBERING.sub("", str(text or ""))).strip()


def question_problem(question: Optional[str], asked_questions: Iterable[str]) -> Optional[str]:
    """Why a question cannot be shown to the learner, or None. Structure, length, one question, no repeats."""
    q = (question or "").strip()
    if len(q) < MIN_QUESTION_CHARS:
        return "it is empty or too short"
    if len(q) > MAX_QUESTION_CHARS:
        return "it is too long to be a single conversational question"
    if len(_LIST_LINE.findall(q)) >= 2:
        return "it is formatted as a list of questions"
    unquoted = _QUOTED.sub(" ", q)  # a quoted phrase (e.g. the learner's own words) may contain "?"
    marks = sum(unquoted.count(mark) for mark in QUESTION_MARKS)
    if marks > 1:
        return "it asks more than one question"
    if marks == 0:
        return "it is not phrased as a question"
    new_tokens = tokenize(q)
    for earlier in asked_questions:
        if jaccard(new_tokens, tokenize(earlier)) >= QUESTION_DUPLICATE_SIMILARITY:
            return "it repeats an earlier question"
    return None


def motive_problem(motive: Optional[str], earlier_motives: Iterable[str]) -> Optional[str]:
    m = " ".join(str(motive or "").split())
    if len(m) < MIN_MOTIVE_CHARS:
        return "the motive is missing or too short"
    if len(m) > MAX_MOTIVE_CHARS:
        return "the motive is too long to be a short statement"
    if sum(m.count(mark) for mark in QUESTION_MARKS) > 0:
        return "the motive must be a statement, not a question"
    tokens = tokenize(m)
    for earlier in earlier_motives:
        if jaccard(tokens, tokenize(earlier)) >= MOTIVE_DUPLICATE_SIMILARITY:
            return "the motive repeats an earlier motive"
    return None


def validate_group(
    raw: Any,
    *,
    asked_questions: Sequence[str],
    earlier_motives: Sequence[str],
    remaining_units: int,
    zero_allowed: bool,
) -> GroupValidation:
    """
    Structure, limits, repetition and budget. Whether the questions are genuinely relevant to the motive, and whether
    they overlap in meaning, is semantic and is judged separately; this function only enforces what code can.

    - More than five questions, a missing or question-like motive, or an unusable result is a PROBLEM (never shown).
    - Individual unusable or repeated questions are dropped (noted), and an over-budget tail is trimmed (noted).
    """
    if not isinstance(raw, dict):
        return GroupValidation(None, ["the group is missing or not an object"])
    problems: List[str] = []
    notes: List[str] = []

    motive = " ".join(str(raw.get("motive") or "").split())
    mp = motive_problem(motive, earlier_motives)
    if mp:
        problems.append(mp)

    raw_questions = raw.get("questions")
    if raw_questions is None:
        problems.append("the questions list is missing")
        raw_questions = []
    elif not isinstance(raw_questions, list):
        problems.append("questions must be a list")
        raw_questions = []
    elif len(raw_questions) > MAX_QUESTIONS_PER_GROUP:
        problems.append(f"more than {MAX_QUESTIONS_PER_GROUP} questions")
        raw_questions = []

    kept: List[str] = []
    seen_tokens: List[List[str]] = []
    for item in raw_questions:
        if not isinstance(item, str):
            notes.append("a question was not text")
            continue
        q = sanitize_question(item)
        issue = question_problem(q, asked_questions)
        if issue:
            notes.append(f"dropped a question: {issue}")
            continue
        tokens = tokenize(q)
        if any(jaccard(tokens, t) >= QUESTION_DUPLICATE_SIMILARITY for t in seen_tokens):
            notes.append("dropped a question that repeats another question in the group")
            continue
        kept.append(q)
        seen_tokens.append(tokens)

    if remaining_units >= 0 and len(kept) > remaining_units:
        notes.append(f"trimmed to the {remaining_units} question(s) left in the budget")
        kept = kept[:remaining_units]

    asked_zero = isinstance(raw.get("questions"), list) and len(raw["questions"]) == 0
    if not kept and not problems:
        if not (asked_zero and zero_allowed):
            problems.append("no usable questions remained" if not asked_zero else "a group without questions is not allowed now")

    targets: List[str] = []
    raw_targets = raw.get("targets")
    for t in (raw_targets if isinstance(raw_targets, list) else []):
        t = str(t or "").strip().lower()
        if t in DIMENSIONS and t not in targets:
            targets.append(t)
    targets = targets[:MAX_TARGETS]

    if problems:
        return GroupValidation(None, problems, notes)
    rationale = " ".join(str(raw.get("rationale") or "").split())[:300]
    return GroupValidation(QuestionGroup(motive=motive, questions=kept, targets=targets, rationale=rationale), [], notes)


# ---------------------------------------------------------------------------
# Generic fallback groups (used only when the model cannot supply a valid group)
# ---------------------------------------------------------------------------

def topic_phrase(topic: str) -> str:
    topic = re.sub(r"\s+", " ", (topic or "").replace('"', "'")).strip().rstrip("?").strip()
    if not topic:
        return "this topic"
    return f'"{topic}"' if len(topic) <= 120 else "this topic"


def _bank(t: str) -> Dict[str, List[QuestionGroup]]:
    def g(dim: str, motive: str, *questions: str) -> QuestionGroup:
        return QuestionGroup(motive=motive, questions=list(questions), targets=[dim],
                             rationale="Generic group used because no better one could be produced.")
    return {
        LEARNING_INTENTION: [g(
            LEARNING_INTENTION, f"I'd like to understand what prompted your interest in {t}, so the notes fit your reason for learning it.",
            f"What made you want to learn about {t} right now?",
            "Is there a particular problem, curiosity or requirement behind it?")],
        DESIRED_OUTCOME: [g(
            DESIRED_OUTCOME, f"I'd like to know what you ultimately want to achieve with {t}, so the notes aim at it.",
            f"Once you have learned {t}, what would you like to be able to understand, build or decide?")],
        LEARNING_APPROACH: [g(
            LEARNING_APPROACH, f"I'd like to understand how you prefer to explore technical ideas, so I can explain {t} in a way that suits you.",
            "When you learn something technical, what usually makes an idea click: intuition first, diagrams, worked examples, code, or maths?",
            "Can you think of an explanation that worked really well for you, and what made it work?")],
        DESIRED_DEPTH: [g(
            DESIRED_DEPTH, f"I'd like to know how deep you want to go with {t}.",
            f"How far into {t} would you like to go: an intuitive overview, a solid conceptual grasp, detailed mechanisms, the mathematics, or hands-on implementation?")],
        MENTAL_MODEL: [g(
            MENTAL_MODEL, f"I'd like to hear how you currently understand {t}, in your own words.",
            f"How would you explain {t} to a colleague today?",
            "Which parts feel solid to you, and which feel shaky?")],
        CONFUSIONS: [g(
            CONFUSIONS, "I'd like to know what confuses you or what you most want answered.",
            f"What, if anything, confuses you about {t}?",
            "Is there a specific question you would love the notes to answer?")],
        COMMITMENT: [g(
            COMMITMENT, "I'd like to know how you feel about working through difficult material.",
            f"If part of {t} gets difficult, such as tricky maths or hard examples, would you rather work through it or keep things lighter?")],
        FAMILIARITY: [g(
            FAMILIARITY, f"I'd like to see which ideas related to {t} you already know.",
            f"Which ideas related to {t} already feel solid to you, and which feel shaky?")],
        CONSTRAINTS: [g(
            CONSTRAINTS, "I'd like to know about any practical limits that should shape the notes.",
            "Are there practical limits, such as time, tools, hardware or a deadline, that I should keep in mind?")],
    }


DEFAULT_FALLBACK_ORDER = (
    LEARNING_INTENTION, DESIRED_OUTCOME, LEARNING_APPROACH, DESIRED_DEPTH, MENTAL_MODEL,
    CONFUSIONS, COMMITMENT, FAMILIARITY, CONSTRAINTS,
)


def fallback_group(
    topic: str,
    priority: Sequence[str],
    *,
    asked_questions: Sequence[str],
    earlier_motives: Sequence[str],
    remaining_units: int,
) -> Optional[QuestionGroup]:
    """
    A generic, topic-parameterised group for the first dimension in `priority` that still has an unasked one.
    It never repeats an earlier question or motive, never exceeds the remaining budget, and says nothing about the
    learner. Returns None when nothing is left to ask (the caller must then stop, not repeat or pad).
    """
    bank = _bank(topic_phrase(topic))
    for dim in priority:
        for candidate in bank.get(dim, []):
            if motive_problem(candidate.motive, earlier_motives):
                continue
            questions = [q for q in candidate.questions if question_problem(q, asked_questions) is None][:max(remaining_units, 0)]
            if not questions:
                continue
            return QuestionGroup(motive=candidate.motive, questions=questions, targets=list(candidate.targets), rationale=candidate.rationale)
    return None
