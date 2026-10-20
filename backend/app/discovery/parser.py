import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from backend.app.core.json_utils import strip_code_fence, find_bracket_span, try_parse_json
from backend.app.discovery.dimensions import DIMENSIONS, parse_dimension_notes
from backend.app.discovery.state import (
    DiscoveryLearnerState,
    OpenIssue,
    Retraction,
    parse_retractions,
    parse_state,
)

logger = logging.getLogger(__name__)

MAX_OPEN_ISSUES = 6


class DiscoveryParseError(ValueError):
    """Model output was unusable (malformed JSON or missing required parts)."""


class GroupParsed(BaseModel):
    """A group exactly as the model sent it. Whether it is acceptable is decided by groups.validate_group()."""
    group: Dict[str, Any]


class TurnParsed(BaseModel):
    state: DiscoveryLearnerState
    assessment: Optional[str] = None
    ready_to_finish: bool = False
    finish_reason: str = ""
    group: Optional[Dict[str, Any]] = None
    reasoning: str = ""
    retractions: List[Retraction] = Field(default_factory=list)
    open_issues: List[OpenIssue] = Field(default_factory=list)


class JudgeVerdict(BaseModel):
    """The model's semantic review of a question group (relevance, overlap, repetition of known facts)."""
    irrelevant: List[int] = Field(default_factory=list)
    overlapping: List[Tuple[int, int]] = Field(default_factory=list)
    revisits_known: List[int] = Field(default_factory=list)
    motive_matches: bool = True
    purpose_served: bool = True
    comment: str = ""


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


def _text(value: Any, limit: int = 600) -> str:
    return re.sub(r"[ \t]+", " ", str(value or "")).strip()[:limit]


def _require_object(raw_text: str) -> Dict[str, Any]:
    data = extract_json_object(raw_text or "")
    if not isinstance(data, dict):
        raise DiscoveryParseError("the reply was not a valid JSON object")
    return data


def _group_object(data: Dict[str, Any]) -> Dict[str, Any]:
    """The group is either the whole reply or nested under "group"; it must at least name a motive."""
    group = data.get("group") if isinstance(data.get("group"), dict) else data
    if "motive" not in group:
        raise DiscoveryParseError('the reply has no "motive"')
    return group


def parse_group(raw_text: str) -> GroupParsed:
    """Reads a question group from an opening or regeneration reply."""
    return GroupParsed(group=_group_object(_require_object(raw_text)))


def parse_turn(raw_text: str, topic: str) -> TurnParsed:
    data = _require_object(raw_text)
    if not isinstance(data.get("state"), dict):
        raise DiscoveryParseError('"state" is missing or not an object')

    ready = data.get("ready_to_finish")
    if not isinstance(ready, bool):
        ready = str(ready).strip().lower() == "true"

    group = data.get("group")
    if not ready and not isinstance(group, dict):
        raise DiscoveryParseError('"group" is required when "ready_to_finish" is false')

    state = parse_state(data["state"], topic)
    state.dimension_notes = parse_dimension_notes(data.get("dimension_notes"))

    issues: List[OpenIssue] = []
    for item in (data.get("open_issues") if isinstance(data.get("open_issues"), list) else []):
        if not isinstance(item, dict):
            continue
        dim = str(item.get("dimension") or "").strip().lower()
        text = _text(item.get("issue"), 240)
        if dim in DIMENSIONS and text:
            impact = "high" if str(item.get("impact") or "").strip().lower() == "high" else "low"
            issues.append(OpenIssue(dimension=dim, issue=text, impact=impact))
    state.open_issues = issues[:MAX_OPEN_ISSUES]

    return TurnParsed(
        state=state,
        assessment=_text(data.get("assessment"), 500) or None,
        ready_to_finish=ready,
        finish_reason=_text(data.get("finish_reason"), 400),
        group=None if ready else group,
        reasoning=_text(data.get("reasoning"), 400),
        retractions=parse_retractions(data.get("retractions")),
        open_issues=state.open_issues,
    )


def _int_list(value: Any, limit: int = 20) -> List[int]:
    if not isinstance(value, list):
        return []
    out: List[int] = []
    for v in value:
        try:
            i = int(v)
        except (TypeError, ValueError):
            continue
        if i >= 0 and i not in out:
            out.append(i)
    return out[:limit]


def _flag(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() not in ("false", "no", "0")


def parse_judge(raw_text: str) -> JudgeVerdict:
    """Reads the semantic review. Indexes are zero-based positions in the reviewed question list."""
    data = _require_object(raw_text)
    if not any(k in data for k in ("irrelevant_questions", "overlapping_pairs", "revisits_known", "motive_matches", "purpose_served")):
        raise DiscoveryParseError("the reply contained none of the review fields")
    pairs: List[Tuple[int, int]] = []
    for pair in (data.get("overlapping_pairs") if isinstance(data.get("overlapping_pairs"), list) else []):
        ints = _int_list(pair, 2)
        if len(ints) == 2:
            pairs.append((ints[0], ints[1]))
    return JudgeVerdict(
        irrelevant=_int_list(data.get("irrelevant_questions")),
        overlapping=pairs[:10],
        revisits_known=_int_list(data.get("revisits_known")),
        motive_matches=_flag(data.get("motive_matches")),
        purpose_served=_flag(data.get("purpose_served")),
        comment=_text(data.get("comment"), 300),
    )
