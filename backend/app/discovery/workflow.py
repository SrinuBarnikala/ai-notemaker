import asyncio
import logging
from typing import TypedDict, List, Optional, Dict, Any, Tuple
from langgraph.graph import StateGraph, START, END

from backend.app.providers.base import LLMProvider
from backend.app.discovery.prompts import (
    DISCOVERY_SYSTEM_PROMPT,
    GROUP_SCHEMA_TEXT,
    INITIAL_GROUP_PROMPT_TEMPLATE,
    ADAPTIVE_STEP_PROMPT_TEMPLATE,
    REPAIR_JSON_PROMPT_TEMPLATE,
    PLAN_GROUP_PROMPT_TEMPLATE,
    JUDGE_PROMPT_TEMPLATE,
)
from backend.app.discovery.dimensions import (
    CORE_DIMENSIONS,
    DIMENSION_LABELS,
    DIMENSIONS,
    LEARNING_APPROACH,
    MAX_ATTEMPTS_BEFORE_RELAXING,
    NOT_RELEVANT,
    SUFFICIENT,
    CONFLICTING,
    OUTDATED,
    PARTIAL,
    DimensionCoverage,
    attempts_by_dimension,
    blocking_dimensions,
    compute_coverage,
    coverage_guard,
    coverage_to_context,
    coverage_to_prompt_text,
    neglected_core,
    unprobed_misconceptions,
    unresolved_core,
)
from backend.app.discovery.groups import (
    DEFAULT_FALLBACK_ORDER,
    MAX_QUESTIONS_PER_GROUP,
    MAX_ZERO_QUESTION_GROUPS,
    QuestionGroup,
    fallback_group,
    validate_group,
)
from backend.app.discovery.parser import (
    DiscoveryParseError,
    JudgeVerdict,
    parse_group,
    parse_judge,
    parse_turn,
)
from backend.app.discovery.state import (
    DiscoveryLearnerState,
    ground_findings,
    merge_states,
    state_to_prompt_text,
)

logger = logging.getLogger(__name__)

# Bounded retries for provider exceptions (network errors, timeouts, rate limits)
PROVIDER_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5

DEFAULT_FINISH_REASON = "Enough was learned to personalize the notes."

# Where the group shown to the learner came from
SOURCE_MODEL = "model"              # the group the analysis step proposed passed every check
SOURCE_REGENERATED = "regenerated"  # the proposal was unusable or rejected; the model wrote a corrected one
SOURCE_FALLBACK = "fallback"        # generic last-resort group (flagged to the caller as fallback_used)

# What the semantic review concluded
SEMANTIC_PASSED = "passed"
SEMANTIC_ADJUSTED = "adjusted"          # some questions were dropped as irrelevant, overlapping or already known
SEMANTIC_UNAVAILABLE = "unavailable"    # the review reply was unusable twice; the group passed the code checks only
SEMANTIC_SKIPPED = "skipped"            # nothing to review (no questions) or a trusted generic group


class DiscoveryProviderError(Exception):
    """The LLM provider kept failing after bounded retries. The operation can be retried."""


class DiscoveryTimeoutError(DiscoveryProviderError):
    """The overall deadline for a discovery request was reached. The operation can be retried."""


class DiscoveryGraphState(TypedDict, total=False):
    mode: str  # "opening" | "turn"
    topic: str
    interactions: List[Dict[str, Any]]
    previous_state: Optional[DiscoveryLearnerState]
    max_questions: int
    # Working / output values
    state: DiscoveryLearnerState
    assessment: Optional[str]
    ready_to_finish: bool
    finish_reason: str
    stopped_reason: Optional[str]
    reasoning: str
    analysis_failed: bool
    proposed: Optional[Dict[str, Any]]      # the model's proposed group, exactly as sent
    coverage: Dict[str, DimensionCoverage]
    group: Optional[QuestionGroup]
    question_source: str
    semantic_check: str
    group_notes: List[str]


# ---------------------------------------------------------------------------
# Transcript, budget and small helpers
# ---------------------------------------------------------------------------

def format_interaction_history(interactions: List[Dict[str, Any]]) -> str:
    if not interactions:
        return "No prior interactions."
    lines = []
    for item in interactions:
        n = item.get("question_index", 1)
        motive = item.get("motive")
        lines.append(f"Group {n}. Motive: {motive}" if motive else f"Group {n} (an earlier question; no motive was recorded):")
        for q in item.get("questions") or []:
            lines.append(f"  - {q}")
        lines.append(f"A{n} (reply to the whole group): {item.get('learner_answer') or '(pending)'}")
        if item.get("quick_assessment"):
            lines.append(f"Assessment: {item['quick_assessment']}")
        lines.append("---")
    return "\n".join(lines)


def _answers(interactions: List[Dict[str, Any]]) -> List[str]:
    return [i["learner_answer"] for i in interactions if i.get("learner_answer")]


def _answer_cards(interactions: List[Dict[str, Any]]) -> List[int]:
    """question_index of each answered group, aligned with _answers()."""
    return [i["question_index"] for i in interactions if i.get("learner_answer")]


def _asked(interactions: List[Dict[str, Any]]) -> List[str]:
    return [q for i in interactions for q in (i.get("questions") or [])]


def _motives(interactions: List[Dict[str, Any]]) -> List[str]:
    return [i["motive"] for i in interactions if i.get("motive")]


def compute_budget(interactions: List[Dict[str, Any]], max_questions: int) -> Tuple[int, int, int, bool]:
    """
    (questions_asked, remaining, max_group, zero_allowed). Derived entirely from what has been persisted, so retries,
    resumes and concurrent requests cannot make it drift. Every question costs one unit; a motive costs nothing.
    A group without questions is rationed (and never allowed first or twice in a row) so it cannot repeat forever.
    """
    asked = sum(len(i.get("questions") or []) for i in interactions)
    remaining = max(max_questions - asked, 0)
    zero_used = sum(1 for i in interactions if not i.get("legacy") and not (i.get("questions") or []))
    last_zero = bool(interactions) and not interactions[-1].get("legacy") and not (interactions[-1].get("questions") or [])
    zero_allowed = bool(interactions) and remaining > 0 and zero_used < MAX_ZERO_QUESTION_GROUPS and not last_zero
    return asked, remaining, min(MAX_QUESTIONS_PER_GROUP, remaining), zero_allowed


def _unresolved_note(c: DimensionCoverage) -> str:
    label = DIMENSION_LABELS[c.dimension]
    return {
        PARTIAL: f"Only inferred, not confirmed by the learner: {label}",
        CONFLICTING: f"Conflicting evidence not resolved: {label}",
        OUTDATED: f"Corrected and not yet re-established: {label}",
    }.get(c.status, f"Not established: {label}")


def _finish_update(
    learner_state: DiscoveryLearnerState,
    coverage: Dict[str, DimensionCoverage],
    stopped_reason: str,
    finish_reason: str,
) -> Dict[str, Any]:
    """State update that ends discovery and records, never hides, what is still unresolved."""
    unresolved = list(learner_state.unresolved)
    notes = [_unresolved_note(c) for c in unresolved_core(coverage)]
    notes += [_unresolved_note(c) for d, c in coverage.items() if d not in CORE_DIMENSIONS and c.status in (CONFLICTING, OUTDATED)]
    notes += [f"Open question ({DIMENSION_LABELS[i.dimension]}): {i.issue}" for i in learner_state.open_issues if i.impact == "high"]
    for note in notes:
        if note not in unresolved:
            unresolved.append(note)
    return {
        "state": learner_state.model_copy(update={"unresolved": unresolved}),
        "ready_to_finish": True,
        "stopped_reason": stopped_reason,
        "finish_reason": finish_reason,
        "group": None,
        "coverage": coverage,
    }


# ---------------------------------------------------------------------------
# Model calls
# ---------------------------------------------------------------------------

async def _generate(provider: LLMProvider, prompt: str) -> str:
    """One model call with bounded retries; provider exceptions are never swallowed into fake output."""
    last_err: Optional[Exception] = None
    for attempt in range(1, PROVIDER_ATTEMPTS + 1):
        try:
            return await provider.generate(prompt=prompt, system_prompt=DISCOVERY_SYSTEM_PROMPT, temperature=0.4)
        except Exception as err:
            last_err = err
            logger.warning("Discovery LLM call failed (attempt %d/%d): %s", attempt, PROVIDER_ATTEMPTS, err)
            if attempt < PROVIDER_ATTEMPTS:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise DiscoveryProviderError(f"The language model provider failed after {PROVIDER_ATTEMPTS} attempts: {last_err}") from last_err


async def _generate_and_parse(provider: LLMProvider, prompt: str, parse, repair: bool = True):
    """Generate and parse; on malformed output make at most one repair attempt. Returns None if still unusable."""
    raw = await _generate(provider, prompt)
    try:
        return parse(raw)
    except DiscoveryParseError as err:
        if not repair:
            logger.warning("Malformed discovery output (%s); not repairing", err)
            return None
        logger.warning("Malformed discovery output (%s); attempting one repair", err)
        repair_prompt = REPAIR_JSON_PROMPT_TEMPLATE.format(problem=err, previous_reply=(raw or "")[:2000])
        raw = await _generate(provider, f"{prompt}\n\n{repair_prompt}")
        try:
            return parse(raw)
        except DiscoveryParseError as err2:
            logger.warning("Discovery output still malformed after repair: %s", err2)
            return None


def _apply_verdict(group: QuestionGroup, verdict: JudgeVerdict) -> Tuple[Optional[QuestionGroup], str, List[str]]:
    """Turn the semantic review into a decision: (group or None, SEMANTIC_*, notes). None means do not show it."""
    if not verdict.motive_matches:
        return None, SEMANTIC_ADJUSTED, ["review: the motive does not describe what the questions investigate"]
    if not verdict.purpose_served:
        return None, SEMANTIC_ADJUSTED, ["review: the questions would not achieve the motive"]
    drop = set(verdict.irrelevant) | set(verdict.revisits_known)
    for i, j in verdict.overlapping:
        drop.add(max(i, j))  # keep the earlier of two questions that ask the same thing
    kept = [q for n, q in enumerate(group.questions) if n not in drop]
    notes = [f"review dropped {len(group.questions) - len(kept)} question(s) as irrelevant, overlapping or already known"] if len(kept) != len(group.questions) else []
    if not kept:
        return None, SEMANTIC_ADJUSTED, ["review: no question was worth asking"] + notes
    status = SEMANTIC_ADJUSTED if notes else SEMANTIC_PASSED
    return QuestionGroup(motive=group.motive, questions=kept, targets=group.targets, rationale=group.rationale), status, notes


def _fallback_priority(coverage: Dict[str, DimensionCoverage], answered_groups: int) -> List[str]:
    """Which dimensions a generic group should cover first: the learning approach early, then what is least established."""
    order = [d for d in DEFAULT_FALLBACK_ORDER if coverage[d].status not in (SUFFICIENT, NOT_RELEVANT)]
    approach = coverage[LEARNING_APPROACH]
    if answered_groups >= 1 and approach.attempts == 0 and LEARNING_APPROACH in order:
        order.remove(LEARNING_APPROACH)
        order.insert(0, LEARNING_APPROACH)
    return order


# ---------------------------------------------------------------------------
# The graph
# ---------------------------------------------------------------------------

def build_discovery_graph(llm_provider: LLMProvider):
    """
    One discovery step:
      analyze_and_plan -> evaluate -> (finish | select_group)

    analyze_and_plan: one model call that reads the reply, updates the learner state for all nine dimensions and
        proposes the next question group.
    evaluate: code only. Computes coverage from the evidence, applies the budget, and decides whether discovery
        may end, independently of the model's "done" flag.
    select_group: code validation, the coverage guard, a semantic review by the model, at most one regeneration,
        and finally a generic fallback. An invalid group is never shown.
    """

    async def analyze_and_plan_node(state: DiscoveryGraphState) -> Dict[str, Any]:
        topic = state["topic"]
        interactions = state.get("interactions", [])
        previous = state.get("previous_state")
        asked, remaining, max_group, _ = compute_budget(interactions, state["max_questions"])
        empty = DiscoveryLearnerState(original_topic=topic)

        if state["mode"] == "opening":
            prompt = INITIAL_GROUP_PROMPT_TEMPLATE.format(
                topic=topic, max_group=max_group, remaining=remaining, group_schema=GROUP_SCHEMA_TEXT)
            parsed = await _generate_and_parse(llm_provider, prompt, parse_group)
            if parsed is None:
                return {"state": empty, "analysis_failed": True, "proposed": None}
            return {"state": empty, "analysis_failed": False, "proposed": parsed.group}

        base = previous or empty
        prompt = ADAPTIVE_STEP_PROMPT_TEMPLATE.format(
            topic=topic,
            answered_groups=len([i for i in interactions if i.get("learner_answer")]),
            questions_asked=asked,
            max_questions=state["max_questions"],
            interaction_history=format_interaction_history(interactions),
            current_state=state_to_prompt_text(previous),
            coverage_table=coverage_to_prompt_text(compute_coverage(base, attempts_by_dimension(interactions))),
            remaining=remaining,
            max_group=max_group,
            group_schema=GROUP_SCHEMA_TEXT,
        )
        parsed = await _generate_and_parse(llm_provider, prompt, lambda raw: parse_turn(raw, topic))
        if parsed is None:
            # Nothing new can be learned from this reply; keep what was already known.
            return {"state": base, "analysis_failed": True, "ready_to_finish": False, "proposed": None, "assessment": None}

        new_state = ground_findings(parsed.state, _answers(interactions), _answer_cards(interactions))
        merged = merge_states(previous, new_state, parsed.retractions, corrected_in=interactions[-1]["question_index"])
        return {
            "state": merged,
            "analysis_failed": False,
            "assessment": parsed.assessment,
            "ready_to_finish": parsed.ready_to_finish,
            "finish_reason": parsed.finish_reason,
            "proposed": parsed.group,
            "reasoning": parsed.reasoning,
        }

    def evaluate_node(state: DiscoveryGraphState) -> Dict[str, Any]:
        """Coverage, budget and stopping. The model's wish to stop is advisory; the evidence decides."""
        learner_state: DiscoveryLearnerState = state["state"]
        interactions = state.get("interactions", [])
        coverage = compute_coverage(learner_state, attempts_by_dimension(interactions))
        if state["mode"] == "opening":
            return {"coverage": coverage, "ready_to_finish": False}

        _, remaining, _, _ = compute_budget(interactions, state["max_questions"])
        if remaining <= 0:
            return _finish_update(learner_state, coverage, "safety_limit", "Reached the question limit.")

        reasons: List[str] = [f"{DIMENSION_LABELS[d]} is not yet established by the learner's own words" for d in blocking_dimensions(coverage)]
        reasons += [f"a misconception has not been investigated: {m}" for m in unprobed_misconceptions(learner_state, interactions)]
        reasons += [
            f"open question ({DIMENSION_LABELS[i.dimension]}): {i.issue}"
            for i in learner_state.open_issues
            if i.impact == "high" and coverage[i.dimension].status != NOT_RELEVANT
            and coverage[i.dimension].attempts < MAX_ATTEMPTS_BEFORE_RELAXING
        ]

        analysed = not state.get("analysis_failed")
        if analysed and state.get("ready_to_finish"):
            if not reasons:
                return _finish_update(learner_state, coverage, "sufficient", state.get("finish_reason") or DEFAULT_FINISH_REASON)
            logger.info("Finish request overridden: %s", reasons)
        elif analysed and not reasons:
            targets = [t for t in ((state.get("proposed") or {}).get("targets") or []) if t in DIMENSIONS]
            if targets and all(coverage[t].status in (SUFFICIENT, NOT_RELEVANT) for t in targets):
                return _finish_update(
                    learner_state, coverage, "sufficient",
                    "The core dimensions are established and the proposed next group would only revisit what is already known.",
                )
        return {"coverage": coverage, "ready_to_finish": False}

    def route_after_evaluate(state: DiscoveryGraphState) -> str:
        return "done" if state.get("ready_to_finish") else "select_group"

    async def select_group_node(state: DiscoveryGraphState) -> Dict[str, Any]:
        topic = state["topic"]
        interactions = state.get("interactions", [])
        learner_state: DiscoveryLearnerState = state["state"]
        coverage: Dict[str, DimensionCoverage] = state["coverage"]
        asked_questions, earlier_motives = _asked(interactions), _motives(interactions)
        _, remaining, max_group, zero_allowed = compute_budget(interactions, state["max_questions"])
        answered = [i for i in interactions if i.get("learner_answer")]
        unprobed = unprobed_misconceptions(learner_state, interactions)
        notes: List[str] = []

        def check(raw: Any) -> Tuple[Optional[QuestionGroup], List[str]]:
            validation = validate_group(
                raw, asked_questions=asked_questions, earlier_motives=earlier_motives,
                remaining_units=remaining, zero_allowed=zero_allowed)
            notes.extend(validation.notes)
            if validation.group is None:
                return None, validation.problems
            issue = coverage_guard(validation.group.targets, coverage=coverage, answered_groups=answered, unprobed=unprobed)
            return (None, [issue]) if issue else (validation.group, [])

        async def review(group: QuestionGroup) -> Tuple[Optional[QuestionGroup], str, List[str]]:
            if not group.questions:
                return group, SEMANTIC_SKIPPED, []
            prompt = JUDGE_PROMPT_TEMPLATE.format(
                topic=topic,
                current_state=state_to_prompt_text(learner_state if state["mode"] == "turn" else None),
                asked_questions="\n".join(f"- {q}" for q in asked_questions) or "(none)",
                motive=group.motive,
                numbered_questions="\n".join(f"{n}. {q}" for n, q in enumerate(group.questions)),
            )
            verdict = await _generate_and_parse(llm_provider, prompt, parse_judge)
            if verdict is None:
                logger.warning("Semantic review unusable; the group passed the code checks only")
                return group, SEMANTIC_UNAVAILABLE, []
            return _apply_verdict(group, verdict)

        def done(group: QuestionGroup, source: str, semantic: str) -> Dict[str, Any]:
            return {"group": group, "question_source": source, "semantic_check": semantic, "group_notes": notes}

        # 1. the proposal from the analysis step
        proposed = state.get("proposed")
        candidate, problems = check(proposed) if proposed is not None else (None, ["no usable group was produced"])
        if candidate is not None:
            final, semantic, why = await review(candidate)
            if final is not None:
                return done(final, SOURCE_MODEL, semantic)
            problems, notes_why = why, why
            notes.extend(notes_why)

        # 2. one regeneration that is told exactly what was wrong
        priority = _fallback_priority(coverage, len(answered))
        attention = neglected_core(coverage) or [d for d in priority if d in CORE_DIMENSIONS][:2]
        prompt = PLAN_GROUP_PROMPT_TEMPLATE.format(
            topic=topic,
            interaction_history=format_interaction_history(interactions),
            current_state=state_to_prompt_text(learner_state if state["mode"] == "turn" else None),
            coverage_table=coverage_to_prompt_text(coverage),
            asked_questions="\n".join(f"- {q}" for q in asked_questions) or "(none)",
            earlier_motives="\n".join(f"- {m}" for m in earlier_motives) or "(none)",
            max_group=max_group,
            remaining=remaining,
            problems="; ".join(problems),
            required_note=(f"Dimensions that most need attention: {', '.join(attention)}.\n" if attention else ""),
            group_schema=GROUP_SCHEMA_TEXT,
        )
        regenerated = await _generate_and_parse(llm_provider, prompt, parse_group, repair=not state.get("analysis_failed"))
        if regenerated is not None:
            candidate, problems = check(regenerated.group)
            if candidate is not None:
                final, semantic, why = await review(candidate)
                if final is not None:
                    return done(final, SOURCE_REGENERATED, semantic)
                notes.extend(why)

        # 3. a generic group that says nothing about the learner, or an honest stop
        generic = fallback_group(
            topic, priority, asked_questions=asked_questions, earlier_motives=earlier_motives, remaining_units=remaining)
        if generic is None:
            logger.warning("No usable discovery group left (%s); ending discovery", problems)
            return _finish_update(
                learner_state, coverage, "no_further_question",
                "No further useful question could be produced, so discovery stopped with what was learned.",
            )
        logger.info("Using generic fallback discovery group (%s)", problems)
        return done(generic, SOURCE_FALLBACK, SEMANTIC_SKIPPED)

    builder = StateGraph(DiscoveryGraphState)
    builder.add_node("analyze_and_plan", analyze_and_plan_node)
    builder.add_node("evaluate", evaluate_node)
    builder.add_node("select_group", select_group_node)
    builder.add_edge(START, "analyze_and_plan")
    builder.add_edge("analyze_and_plan", "evaluate")
    builder.add_conditional_edges("evaluate", route_after_evaluate, {"select_group": "select_group", "done": END})
    builder.add_edge("select_group", END)
    return builder.compile()


def _group_result(result: Dict[str, Any]) -> Dict[str, Any]:
    group: Optional[QuestionGroup] = result.get("group")
    source = result.get("question_source", SOURCE_MODEL)
    return {
        "group": group,
        "question_source": source,
        "semantic_check": result.get("semantic_check", SEMANTIC_SKIPPED),
        "group_notes": result.get("group_notes", []),
        "fallback_used": source == SOURCE_FALLBACK and group is not None,
        "coverage": coverage_to_context(result["coverage"]) if result.get("coverage") else {},
    }


async def run_initial_discovery(
    journey_id: str,
    topic: str,
    provider: LLMProvider,
    max_questions: int = 10,
) -> Dict[str, Any]:
    """Generates the first question group for a topic."""
    graph = build_discovery_graph(provider)
    result = await graph.ainvoke({
        "mode": "opening",
        "topic": topic,
        "interactions": [],
        "previous_state": None,
        "max_questions": max_questions,
        "question_source": SOURCE_MODEL,
    })
    out = _group_result(result)
    out.update({"state": result["state"], "is_finished": bool(result.get("ready_to_finish")),
                "analysis_failed": bool(result.get("analysis_failed")), "stopped_reason": result.get("stopped_reason")})
    return out


async def run_adaptive_discovery_step(
    journey_id: str,
    topic: str,
    interactions: List[Dict[str, Any]],
    provider: LLMProvider,
    previous_state: Optional[DiscoveryLearnerState] = None,
    max_questions: int = 10,
) -> Dict[str, Any]:
    """
    Reads the learner's latest reply in the context of the whole conversation, updates the learner state, and either
    chooses the next question group or ends discovery. `interactions` must contain every group so far, with the
    latest answer already filled in.
    """
    graph = build_discovery_graph(provider)
    result = await graph.ainvoke({
        "mode": "turn",
        "topic": topic,
        "interactions": interactions,
        "previous_state": previous_state,
        "max_questions": max_questions,
        "question_source": SOURCE_MODEL,
    })
    out = _group_result(result)
    out.update({
        "state": result["state"],
        "quick_assessment": result.get("assessment"),
        "is_finished": bool(result.get("ready_to_finish")),
        "finish_reason": result.get("finish_reason", ""),
        "stopped_reason": result.get("stopped_reason"),
        "reasoning": result.get("reasoning", ""),
        "analysis_failed": bool(result.get("analysis_failed")),
    })
    return out
