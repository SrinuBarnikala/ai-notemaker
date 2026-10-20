"""
Provisional learner state built up over a discovery conversation.

Every claim carries its provenance (``basis``):
  - stated:        the learner said it explicitly
  - demonstrated:  the learner's explanation showed it
  - inferred:      a tentative inference by the system (provisional)
Anything not supported by the conversation stays ``None`` / absent, i.e. unknown.

Evidence: a stated/demonstrated claim must carry a quote that appears, token for token, inside a
single learner answer. That check proves the quote exists. It does NOT prove the quote supports
the claim; that remains the model's judgment and is only as reliable as the model.
"""
import json
import re
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from backend.app.discovery.text import contains_sequence, jaccard, tokenize

Basis = Literal["stated", "demonstrated", "inferred"]

MAX_VALUE_CHARS = 300
MAX_LIST_ITEMS = 8
MAX_RESOLVED_ITEMS = 12

# A quote shorter than this (in total token characters) or without any real word is not evidence
MIN_EVIDENCE_TOTAL_CHARS = 4
MIN_EVIDENCE_LONGEST_TOKEN = 3

# Bases that mean "the learner's own words support this"
GROUNDED_BASES = ("stated", "demonstrated")

# Journey statuses at which discovery is over (or the journey has moved on to later stages)
DISCOVERY_CONCLUDED_STATUSES = {"discovery_completed", "profile_ready", "architecture_ready", "note_generated"}

# Dimensions whose absence materially limits personalization
CORE_DIMENSIONS = ("understanding", "intent", "desired_depth")

DIMENSION_LABELS = {
    "understanding": "current understanding of the topic",
    "intent": "learning intention",
    "desired_depth": "desired depth",
}

# Two finding texts this similar are treated as the same finding (retractions, de-duplication)
SAME_FINDING_SIMILARITY = 0.6


class Finding(BaseModel):
    value: str
    basis: Basis = "inferred"
    evidence: Optional[str] = None


class ResolvedItem(BaseModel):
    """A finding the model explicitly retracted or marked resolved; no longer part of the current state."""
    field: str
    value: str
    reason: Optional[str] = None


class Retraction(BaseModel):
    field: str
    value: str = ""
    reason: Optional[str] = None


SINGLE_FIELDS = ("intent", "desired_depth", "understanding", "challenge_willingness", "available_time")
LIST_FIELDS = ("related_familiarity", "gaps", "misconceptions", "explanation_preferences")
RETRACTABLE_FIELDS = SINGLE_FIELDS + LIST_FIELDS


class DiscoveryLearnerState(BaseModel):
    original_topic: str = ""
    intent: Optional[Finding] = None
    desired_depth: Optional[Finding] = None
    understanding: Optional[Finding] = None
    related_familiarity: List[Finding] = Field(default_factory=list)
    gaps: List[Finding] = Field(default_factory=list)
    misconceptions: List[Finding] = Field(default_factory=list)
    explanation_preferences: List[Finding] = Field(default_factory=list)
    challenge_willingness: Optional[Finding] = None
    available_time: Optional[Finding] = None
    unresolved: List[str] = Field(default_factory=list)
    resolved: List[ResolvedItem] = Field(default_factory=list)

    def missing_core(self) -> List[str]:
        """Core dimensions with no finding at all."""
        return [d for d in CORE_DIMENSIONS if getattr(self, d) is None]

    def unconfirmed_core(self) -> List[Tuple[str, str]]:
        """
        Core dimensions not backed by the learner's own words, as (dimension, "unknown" | "inferred").
        A merely inferred finding does not count as established.
        """
        result: List[Tuple[str, str]] = []
        for dim in CORE_DIMENSIONS:
            finding = getattr(self, dim)
            if finding is None:
                result.append((dim, "unknown"))
            elif finding.basis not in GROUNDED_BASES:
                result.append((dim, "inferred"))
        return result

    def is_confirmed(self, dim: str) -> bool:
        finding = getattr(self, dim)
        return finding is not None and finding.basis in GROUNDED_BASES


def load_analysis(raw: Optional[str]) -> Dict[str, Any]:
    """Parses the JSON stored in DiscoveryInteraction.analysis; unreadable or legacy (NULL) values give {}."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_state(raw: Optional[str]) -> Optional[DiscoveryLearnerState]:
    """The learner state recorded in a stored analysis, or None if absent or invalid."""
    stored = load_analysis(raw).get("state")
    if not isinstance(stored, dict):
        return None
    try:
        return DiscoveryLearnerState.model_validate(stored)
    except Exception:
        return None


def _clean(text: Any, limit: int = MAX_VALUE_CHARS) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _parse_finding(raw: Any) -> Optional[Finding]:
    if raw is None:
        return None
    if isinstance(raw, str):
        value = _clean(raw)
        return Finding(value=value) if value else None
    if not isinstance(raw, dict):
        return None
    value = _clean(raw.get("value"))
    basis = str(raw.get("basis", "inferred")).lower().strip()
    if not value or basis == "unknown":
        return None
    if basis not in ("stated", "demonstrated", "inferred"):
        basis = "inferred"
    evidence = _clean(raw.get("evidence")) or None
    return Finding(value=value, basis=basis, evidence=evidence)  # type: ignore[arg-type]


def parse_state(data: Any, topic: str) -> DiscoveryLearnerState:
    """Leniently build a state from model output; unusable parts are dropped (left unknown)."""
    data = data if isinstance(data, dict) else {}
    state = DiscoveryLearnerState(original_topic=topic)
    for name in SINGLE_FIELDS:
        setattr(state, name, _parse_finding(data.get(name)))
    for name in LIST_FIELDS:
        raw_items = data.get(name)
        items = raw_items if isinstance(raw_items, list) else []
        parsed = [f for f in (_parse_finding(i) for i in items) if f]
        setattr(state, name, parsed[:MAX_LIST_ITEMS])
    raw_unresolved = data.get("unresolved")
    if isinstance(raw_unresolved, list):
        state.unresolved = [u for u in (_clean(i) for i in raw_unresolved) if u][:MAX_LIST_ITEMS]
    return state


def parse_retractions(raw: Any) -> List[Retraction]:
    """Leniently read the model's explicit retractions; entries naming an unknown field are ignored."""
    if not isinstance(raw, list):
        return []
    result: List[Retraction] = []
    for item in raw:
        if isinstance(item, str) and ":" in item:
            field, _, value = item.partition(":")
            item = {"field": field, "value": value}
        if not isinstance(item, dict):
            continue
        field = _clean(item.get("field"), 60).lower().replace(" ", "_")
        if field == "intention":
            field = "intent"
        if field not in RETRACTABLE_FIELDS:
            continue
        result.append(Retraction(
            field=field,
            value=_clean(item.get("value")),
            reason=_clean(item.get("reason"), 200) or None,
        ))
    return result[:MAX_LIST_ITEMS]


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

def _split_quote(evidence: str) -> List[List[str]]:
    """A quote may use '...' to skip words; each fragment is verified on its own."""
    fragments = re.split(r"\.{3}|…", evidence or "")
    return [t for t in (tokenize(f) for f in fragments) if t]


def evidence_is_valid(evidence: Optional[str], learner_answers: Sequence[str]) -> bool:
    """
    True if the quote is substantial and every fragment appears, as whole tokens, in one single
    learner answer. (Existence only; semantic support is not verified.)
    """
    fragments = _split_quote(evidence or "")
    if not fragments:
        return False
    all_tokens = [t for frag in fragments for t in frag]
    if sum(len(t) for t in all_tokens) < MIN_EVIDENCE_TOTAL_CHARS:
        return False
    if max(len(t) for t in all_tokens) < MIN_EVIDENCE_LONGEST_TOKEN:
        return False
    for answer in learner_answers:
        answer_tokens = tokenize(answer)
        if all(contains_sequence(answer_tokens, frag) for frag in fragments):
            return True
    return False


def ground_findings(state: DiscoveryLearnerState, learner_answers: List[str]) -> DiscoveryLearnerState:
    """
    Keep only evidence that is genuinely present in a learner answer. A stated/demonstrated claim
    whose evidence is missing, too short, or not found is downgraded to a provisional inference
    and its invalid evidence is discarded, so no fabricated quote is ever exposed.
    """
    def ground(finding: Optional[Finding]) -> Optional[Finding]:
        if finding is None:
            return None
        valid = evidence_is_valid(finding.evidence, learner_answers)
        basis = finding.basis if (finding.basis == "inferred" or valid) else "inferred"
        return Finding(value=finding.value, basis=basis, evidence=finding.evidence if valid else None)

    for name in SINGLE_FIELDS:
        setattr(state, name, ground(getattr(state, name)))
    for name in LIST_FIELDS:
        setattr(state, name, [g for g in (ground(f) for f in getattr(state, name)) if g])
    return state


# ---------------------------------------------------------------------------
# Merge and retraction
# ---------------------------------------------------------------------------

def same_finding(a: str, b: str) -> bool:
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return (a or "").strip().casefold() == (b or "").strip().casefold()
    return set(ta) == set(tb) or jaccard(ta, tb) >= SAME_FINDING_SIMILARITY


def apply_retractions(
    state: DiscoveryLearnerState,
    retractions: Iterable[Retraction],
) -> Tuple[DiscoveryLearnerState, List[ResolvedItem]]:
    """Returns a copy of `state` without the retracted findings, plus what was actually removed."""
    result = state.model_copy(deep=True)
    removed: List[ResolvedItem] = []
    for r in retractions:
        if r.field in SINGLE_FIELDS:
            current: Optional[Finding] = getattr(result, r.field)
            if current is not None and (not r.value or same_finding(current.value, r.value)):
                setattr(result, r.field, None)
                removed.append(ResolvedItem(field=r.field, value=current.value, reason=r.reason))
        elif r.field in LIST_FIELDS and r.value:
            kept: List[Finding] = []
            for item in getattr(result, r.field):
                if same_finding(item.value, r.value):
                    removed.append(ResolvedItem(field=r.field, value=item.value, reason=r.reason))
                else:
                    kept.append(item)
            setattr(result, r.field, kept)
    return result, removed


def _dedupe_resolved(items: Iterable[ResolvedItem]) -> List[ResolvedItem]:
    unique: List[ResolvedItem] = []
    for item in items:
        if not any(u.field == item.field and same_finding(u.value, item.value) for u in unique):
            unique.append(item)
    return unique[-MAX_RESOLVED_ITEMS:]


def merge_states(
    previous: Optional[DiscoveryLearnerState],
    new: DiscoveryLearnerState,
    retractions: Sequence[Retraction] = (),
) -> DiscoveryLearnerState:
    """
    Carry earlier findings forward when a later model reply merely omits them, but honor explicit
    retractions: a retracted finding disappears from the effective state (and from the model's own
    new output, if it was listed again) and is recorded under `resolved`.
    """
    new_eff, removed_new = apply_retractions(new, retractions)
    if previous is None:
        new_eff.resolved = _dedupe_resolved([*new.resolved, *removed_new])
        return new_eff

    prev_eff, removed_prev = apply_retractions(previous, retractions)
    merged = new_eff
    for name in SINGLE_FIELDS:
        if getattr(merged, name) is None:
            setattr(merged, name, getattr(prev_eff, name))
    for name in LIST_FIELDS:
        current = list(getattr(merged, name))
        for old in getattr(prev_eff, name):
            if not any(same_finding(old.value, c.value) for c in current):
                current.append(old)
        setattr(merged, name, current[:MAX_LIST_ITEMS])
    merged.resolved = _dedupe_resolved([*previous.resolved, *new.resolved, *removed_prev, *removed_new])
    return merged


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fmt(finding: Optional[Finding]) -> str:
    return f"{finding.value} [{finding.basis}]" if finding else "unknown"


def state_to_prompt_text(state: Optional[DiscoveryLearnerState]) -> str:
    if state is None:
        return "Nothing established yet."
    lines = [
        f"- Learning intention: {_fmt(state.intent)}",
        f"- Desired depth: {_fmt(state.desired_depth)}",
        f"- Current understanding: {_fmt(state.understanding)}",
        f"- Willingness to engage with challenging material: {_fmt(state.challenge_willingness)}",
        f"- Available time: {_fmt(state.available_time)}",
    ]
    for label, name in (
        ("Related familiarity", "related_familiarity"),
        ("Knowledge gaps", "gaps"),
        ("Possible misconceptions", "misconceptions"),
        ("Explanation preferences", "explanation_preferences"),
    ):
        items = getattr(state, name)
        lines.append(f"- {label}: " + ("; ".join(_fmt(i) for i in items) if items else "unknown"))
    if state.resolved:
        lines.append("- Corrected or resolved earlier (no longer current): "
                     + "; ".join(f"{r.value} ({r.field})" for r in state.resolved))
    if state.unresolved:
        lines.append("- Unresolved: " + "; ".join(state.unresolved))
    return "\n".join(lines)


def state_to_context_dict(state: DiscoveryLearnerState) -> Dict[str, Any]:
    """Structured form stored on the knowledge profile and read by the personalization layer."""
    return {
        "original_topic": state.original_topic,
        "intention": state.intent.model_dump() if state.intent else None,
        "desired_depth": state.desired_depth.model_dump() if state.desired_depth else None,
        "understanding": state.understanding.model_dump() if state.understanding else None,
        "related_familiarity": [f.model_dump() for f in state.related_familiarity],
        "gaps": [f.model_dump() for f in state.gaps],
        "misconceptions": [f.model_dump() for f in state.misconceptions],
        "explanation_preferences": [f.model_dump() for f in state.explanation_preferences],
        "challenge_willingness": state.challenge_willingness.model_dump() if state.challenge_willingness else None,
        "available_time": state.available_time.model_dump() if state.available_time else None,
        "unresolved": list(state.unresolved),
        "resolved": [r.model_dump() for r in state.resolved],
    }
