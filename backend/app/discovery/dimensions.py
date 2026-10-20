"""
The nine learner-discovery dimensions and the code-computed coverage of each.

The dimensions are a COVERAGE FRAMEWORK, not nine interview sections. One answer may evidence several of them,
some may be irrelevant to a journey, and nothing here asks a question. What this module does is look at the
evidence-tagged learner state and report, independently of what the model claims, how well each dimension is
covered, so that question selection and stopping can be checked against it.
"""
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from pydantic import BaseModel

LEARNING_INTENTION = "learning_intention"
DESIRED_OUTCOME = "desired_outcome"
LEARNING_APPROACH = "learning_approach"
COMMITMENT = "commitment_willingness"
MENTAL_MODEL = "current_mental_model"
FAMILIARITY = "conceptual_familiarity"
DESIRED_DEPTH = "desired_depth"
CONFUSIONS = "confusions_and_gaps"
CONSTRAINTS = "practical_constraints"

DIMENSIONS: Tuple[str, ...] = (
    LEARNING_INTENTION, DESIRED_OUTCOME, LEARNING_APPROACH, COMMITMENT, MENTAL_MODEL,
    FAMILIARITY, DESIRED_DEPTH, CONFUSIONS, CONSTRAINTS,
)

DIMENSION_LABELS: Dict[str, str] = {
    LEARNING_INTENTION: "learning intention",
    DESIRED_OUTCOME: "desired outcome",
    LEARNING_APPROACH: "learning approach",
    COMMITMENT: "commitment and willingness",
    MENTAL_MODEL: "current mental model",
    FAMILIARITY: "conceptual familiarity",
    DESIRED_DEPTH: "desired depth",
    CONFUSIONS: "confusions, gaps and open questions",
    CONSTRAINTS: "practical constraints",
}

# Which learner-state fields carry the evidence for each dimension
DIMENSION_FIELDS: Dict[str, Tuple[str, ...]] = {
    LEARNING_INTENTION: ("intent",),
    DESIRED_OUTCOME: ("desired_outcome",),
    LEARNING_APPROACH: ("explanation_preferences", "observed_approach"),
    COMMITMENT: ("challenge_willingness",),
    MENTAL_MODEL: ("understanding",),
    FAMILIARITY: ("related_familiarity",),
    DESIRED_DEPTH: ("desired_depth",),
    CONFUSIONS: ("gaps", "misconceptions", "questions_to_answer"),
    CONSTRAINTS: ("available_time", "constraints"),
}
FIELD_TO_DIMENSION: Dict[str, str] = {f: d for d, fields in DIMENSION_FIELDS.items() for f in fields}

# Without evidence on these, personalization is guesswork, so discovery cannot end early without them
CORE_DIMENSIONS: Tuple[str, ...] = (LEARNING_INTENTION, DESIRED_OUTCOME, LEARNING_APPROACH, DESIRED_DEPTH, MENTAL_MODEL)
# What the opening phase should establish first (current understanding follows once there is context for it)
INTAKE_DIMENSIONS: Tuple[str, ...] = (LEARNING_INTENTION, DESIRED_OUTCOME, LEARNING_APPROACH, DESIRED_DEPTH)
# Only these may be declared "not relevant to this journey"; the core dimensions can never be
MAY_BE_NOT_RELEVANT: Tuple[str, ...] = (COMMITMENT, FAMILIARITY, CONFUSIONS, CONSTRAINTS)

# A core dimension that has been asked about this many times without producing evidence stops blocking the end
# of discovery (silence or "no idea" is recorded as unresolved, never read as inability or disinterest)
MAX_ATTEMPTS_BEFORE_RELAXING = 2
# A conflicting dimension is given a little longer, because the conflict itself is worth resolving
MAX_ATTEMPTS_FOR_CONFLICT = 3

SUFFICIENT = "sufficient"      # at least one finding the learner's own words support
PARTIAL = "partial"            # only tentative inferences so far
NONE = "none"                  # nothing recorded
CONFLICTING = "conflicting"    # the model flagged contradictory evidence that is still unresolved
OUTDATED = "outdated"          # what was known was corrected or retracted and nothing has replaced it
NOT_RELEVANT = "not_relevant"  # judged irrelevant to this journey, with a recorded reason

GROUNDED_BASES = ("stated", "demonstrated")


class DimensionNote(BaseModel):
    """The model's judgment about a dimension that evidence alone cannot express."""
    relevance: str = "relevant"      # "relevant" | "not_relevant"
    conflict: bool = False
    reason: Optional[str] = None


class DimensionCoverage(BaseModel):
    dimension: str
    status: str
    reason: Optional[str] = None
    grounded: int = 0
    inferred: int = 0
    attempts: int = 0


def dimension_findings(state: Any, dimension: str) -> List[Any]:
    found: List[Any] = []
    for field in DIMENSION_FIELDS[dimension]:
        value = getattr(state, field, None)
        if value is None:
            continue
        found.extend(value if isinstance(value, list) else [value])
    return found


def compute_coverage(state: Any, attempts: Optional[Dict[str, int]] = None) -> Dict[str, DimensionCoverage]:
    """Status of each of the nine dimensions, derived from evidence in `state` (never from a model's say-so)."""
    attempts = attempts or {}
    notes: Dict[str, DimensionNote] = getattr(state, "dimension_notes", None) or {}
    resolved_fields = {r.field for r in getattr(state, "resolved", [])}
    coverage: Dict[str, DimensionCoverage] = {}
    for dim in DIMENSIONS:
        findings = dimension_findings(state, dim)
        grounded = sum(1 for f in findings if f.basis in GROUNDED_BASES)
        note = notes.get(dim)
        reason: Optional[str] = None
        if note is not None and note.relevance == "not_relevant" and dim in MAY_BE_NOT_RELEVANT and note.reason:
            status, reason = NOT_RELEVANT, note.reason
        elif note is not None and note.conflict:
            status, reason = CONFLICTING, note.reason
        elif grounded:
            status = SUFFICIENT
        elif findings:
            status = PARTIAL
        elif resolved_fields & set(DIMENSION_FIELDS[dim]):
            status = OUTDATED
        else:
            status = NONE
        coverage[dim] = DimensionCoverage(
            dimension=dim, status=status, reason=reason, grounded=grounded,
            inferred=len(findings) - grounded, attempts=attempts.get(dim, 0),
        )
    return coverage


def blocking_dimensions(coverage: Dict[str, DimensionCoverage]) -> List[str]:
    """Core dimensions that still prevent discovery from ending early."""
    blockers: List[str] = []
    for dim in CORE_DIMENSIONS:
        c = coverage[dim]
        if c.status in (SUFFICIENT, NOT_RELEVANT):
            continue
        limit = MAX_ATTEMPTS_FOR_CONFLICT if c.status == CONFLICTING else MAX_ATTEMPTS_BEFORE_RELAXING
        if c.attempts >= limit:
            continue  # asked enough times: record it as unresolved instead of nagging
        blockers.append(dim)
    return blockers


def unresolved_core(coverage: Dict[str, DimensionCoverage]) -> List[DimensionCoverage]:
    """Core dimensions without grounded evidence (whether or not they still block the end)."""
    return [coverage[d] for d in CORE_DIMENSIONS if coverage[d].status not in (SUFFICIENT, NOT_RELEVANT)]


def neglected_core(coverage: Dict[str, DimensionCoverage]) -> List[str]:
    """Core dimensions without grounded evidence that no answered group has ever targeted."""
    return [d for d in CORE_DIMENSIONS
            if coverage[d].status in (NONE, PARTIAL, OUTDATED) and coverage[d].attempts == 0]


def attempts_by_dimension(groups: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """How many ANSWERED groups targeted each dimension (a pending group has not yet produced anything)."""
    counts: Dict[str, int] = {}
    for g in groups:
        if not g.get("learner_answer"):
            continue
        for dim in set(g.get("targets") or []):
            if dim in DIMENSIONS:
                counts[dim] = counts.get(dim, 0) + 1
    return counts


def coverage_to_prompt_text(coverage: Dict[str, DimensionCoverage]) -> str:
    """The coverage table shown to the model so it can choose what matters most next."""
    lines = []
    for n, dim in enumerate(DIMENSIONS, 1):
        c = coverage[dim]
        tag = "core" if dim in CORE_DIMENSIONS else "supporting"
        detail = f"; {c.reason}" if c.reason else ""
        lines.append(
            f"{n}. {DIMENSION_LABELS[dim]} [{dim}, {tag}]: {c.status.upper()}"
            f" (grounded findings: {c.grounded}, inferred: {c.inferred}, groups asked about it: {c.attempts}{detail})"
        )
    return "\n".join(lines)


def coverage_to_context(coverage: Dict[str, DimensionCoverage]) -> Dict[str, Dict[str, Any]]:
    """Stored with the profile so downstream consumers can see what is and is not established."""
    return {d: {"status": c.status, "reason": c.reason, "attempts": c.attempts} for d, c in coverage.items()}


def parse_dimension_notes(raw: Any) -> Dict[str, DimensionNote]:
    """
    Read the model's dimension notes. A "not_relevant" claim is only honored for a dimension that may be irrelevant
    and only with a stated reason; anything else is ignored rather than trusted.
    """
    if not isinstance(raw, list):
        return {}
    notes: Dict[str, DimensionNote] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        dim = str(item.get("dimension") or "").strip().lower()
        if dim not in DIMENSIONS:
            continue
        status = str(item.get("status") or "").strip().lower()
        reason = " ".join(str(item.get("reason") or "").split())[:240] or None
        current = notes.get(dim, DimensionNote())
        if status == "not_relevant" and dim in MAY_BE_NOT_RELEVANT and reason:
            notes[dim] = DimensionNote(relevance="not_relevant", conflict=current.conflict, reason=reason)
        elif status == "conflicting" and reason:
            notes[dim] = DimensionNote(relevance=current.relevance, conflict=True, reason=reason)
        elif status in ("relevant", "resolved"):
            notes[dim] = DimensionNote(relevance="relevant", conflict=False, reason=None)
    return notes


# ---------------------------------------------------------------------------
# Question-selection guards (code-enforced, independent of the model's reasoning)
# ---------------------------------------------------------------------------

def unprobed_misconceptions(state: Any, groups: Sequence[Dict[str, Any]]) -> List[str]:
    """
    Misconceptions the learner's own words support that no answered group has yet investigated. A misconception is
    "probed" once an answered group, at or after the one it appeared in, targeted confusions_and_gaps.
    """
    open_ones: List[str] = []
    for m in getattr(state, "misconceptions", []):
        if m.basis not in GROUNDED_BASES or m.source_card is None:
            continue
        probed = any(
            g.get("learner_answer") and g.get("question_index", 0) >= m.source_card and CONFUSIONS in (g.get("targets") or [])
            for g in groups
        )
        if not probed:
            open_ones.append(m.value)
    return open_ones


def coverage_guard(
    targets: Sequence[str],
    *,
    coverage: Dict[str, DimensionCoverage],
    answered_groups: Sequence[Dict[str, Any]],
    unprobed: Sequence[str],
) -> Optional[str]:
    """
    Why a proposed group would let the conversation drift, or None.

    1. Early on, the learning approach must be explored: once a first group is answered, a group must target it
       unless it is already evidenced (or the group is investigating a misconception).
    2. No tangent: if core dimensions have never been asked about while two answered groups in a row ignored them,
       the next group must target one of them (again, unless investigating a misconception).
    A group that declares no targets cannot be judged and is let through (the model is told to declare them).
    """
    declared = [t for t in targets if t in DIMENSIONS]
    if not declared:
        return None
    investigating = bool(unprobed) and CONFUSIONS in declared

    approach = coverage[LEARNING_APPROACH]
    if (answered_groups and approach.attempts == 0 and approach.status not in (SUFFICIENT, NOT_RELEVANT)
            and LEARNING_APPROACH not in declared and not investigating):
        return "the learning approach has not been explored yet, so this group must target learning_approach"

    neglected = neglected_core(coverage)
    if neglected and not (set(declared) & set(neglected)) and not investigating:
        recent = list(answered_groups)[-2:]
        if len(recent) >= 2 and all(not (set(g.get("targets") or []) & set(neglected)) for g in recent):
            return ("two groups in a row ignored dimensions that have never been explored ("
                    + ", ".join(neglected) + "), so this group must target one of them")
    return None
