import asyncio
import logging
from typing import TypedDict, List, Optional, Dict, Any
from langgraph.graph import StateGraph, START, END

from backend.app.providers.base import LLMProvider
from backend.app.discovery.prompts import (
    DISCOVERY_SYSTEM_PROMPT,
    DISCOVERY_TEXT_SYSTEM_PROMPT,
    INITIAL_QUESTION_PROMPT_TEMPLATE,
    ADAPTIVE_STEP_PROMPT_TEMPLATE,
    REPAIR_JSON_PROMPT_TEMPLATE,
    TEXT_QUESTION_PROMPT_TEMPLATE,
)
from backend.app.discovery.parser import (
    DiscoveryParseError,
    parse_opening,
    parse_turn,
    parse_plain_question,
    question_problem,
    fallback_question,
)
from backend.app.discovery.state import (
    CORE_DIMENSIONS,
    DIMENSION_LABELS,
    DiscoveryLearnerState,
    ground_findings,
    merge_states,
    state_to_prompt_text,
)

logger = logging.getLogger(__name__)

# Bounded retries for provider exceptions (network errors, timeouts, rate limits)
PROVIDER_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5

# The learning intention may stay unconfirmed once this many answers are in (recorded as unresolved).
# Current understanding must always be confirmed by the learner's own words before discovery can end,
# except at the safety limit.
MIN_ANSWERS_TO_FINISH_WITHOUT_INTENT = 3

DEFAULT_FINISH_REASON = "Enough was learned to personalize the notes."

# Where the question shown to the learner came from
SOURCE_MODEL = "model"          # produced by the normal analysis step
SOURCE_REWRITTEN = "rewritten"  # analysis was fine but its question was rejected; the model wrote another
SOURCE_RECOVERED = "recovered"  # analysis output was unusable; the model wrote a plain-text question instead
SOURCE_CANNED = "canned"        # generic last-resort question (flagged to the caller as fallback_used)


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
    answered_count: int
    # Working / output values
    state: DiscoveryLearnerState
    assessment: Optional[str]
    ready_to_finish: bool
    finish_reason: str
    stopped_reason: Optional[str]
    focus: str
    next_question: Optional[str]
    reasoning: str
    parse_failed: bool
    question_issue: Optional[str]
    question_source: str


def format_interaction_history(interactions: List[Dict[str, Any]]) -> str:
    if not interactions:
        return "No prior interactions."
    lines = []
    for item in interactions:
        q_num = item.get("question_index", 1)
        q_text = item.get("question_text", "")
        target = item.get("concept_target", "")
        ans = item.get("learner_answer") or "(pending)"
        assessment = item.get("quick_assessment") or ""
        lines.append(f"Q{q_num} [{target}]: {q_text}")
        lines.append(f"A{q_num}: {ans}")
        if assessment:
            lines.append(f"Assessment: {assessment}")
        lines.append("---")
    return "\n".join(lines)


def _answers(interactions: List[Dict[str, Any]]) -> List[str]:
    return [i["learner_answer"] for i in interactions if i.get("learner_answer")]


def _asked(interactions: List[Dict[str, Any]]) -> List[str]:
    return [i["question_text"] for i in interactions if i.get("question_text")]


def unconfirmed_text(state: Optional[DiscoveryLearnerState]) -> str:
    """Prompt text naming the core dimensions the learner has not established in their own words."""
    items = state.unconfirmed_core() if state is not None else [(d, "unknown") for d in CORE_DIMENSIONS]
    parts = [
        f"{DIMENSION_LABELS[dim]} ({'only inferred so far' if kind == 'inferred' else 'not yet known'})"
        for dim, kind in items
    ]
    return ", ".join(parts) or "none"


async def _generate(provider: LLMProvider, prompt: str, system_prompt: str = DISCOVERY_SYSTEM_PROMPT) -> str:
    """One model call with bounded retries; provider exceptions are never swallowed into fake output."""
    last_err: Optional[Exception] = None
    for attempt in range(1, PROVIDER_ATTEMPTS + 1):
        try:
            return await provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.4,
            )
        except Exception as err:
            last_err = err
            logger.warning("Discovery LLM call failed (attempt %d/%d): %s", attempt, PROVIDER_ATTEMPTS, err)
            if attempt < PROVIDER_ATTEMPTS:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise DiscoveryProviderError(f"The language model provider failed after {PROVIDER_ATTEMPTS} attempts: {last_err}") from last_err


async def _generate_and_parse(provider: LLMProvider, prompt: str, parse):
    """Generate, parse, and on malformed output make exactly one repair attempt. Returns None if still unusable."""
    raw = await _generate(provider, prompt)
    try:
        return parse(raw)
    except DiscoveryParseError as err:
        logger.warning("Malformed discovery output (%s); attempting one repair", err)
        repair_prompt = REPAIR_JSON_PROMPT_TEMPLATE.format(problem=err, previous_reply=(raw or "")[:2000])
        raw = await _generate(provider, f"{prompt}\n\n{repair_prompt}")
        try:
            return parse(raw)
        except DiscoveryParseError as err2:
            logger.warning("Discovery output still malformed after repair: %s", err2)
            return None


def build_discovery_graph(llm_provider: LLMProvider):
    """
    Builds the LangGraph workflow for one discovery turn:
    analyze_and_plan -> guardrails -> (write_question)? -> END
    """

    async def analyze_and_plan_node(state: DiscoveryGraphState) -> Dict[str, Any]:
        topic = state["topic"]
        interactions = state.get("interactions", [])
        previous = state.get("previous_state")

        if state["mode"] == "opening":
            parsed = await _generate_and_parse(
                llm_provider,
                INITIAL_QUESTION_PROMPT_TEMPLATE.format(topic=topic),
                parse_opening,
            )
            empty = DiscoveryLearnerState(original_topic=topic)
            if parsed is None:
                return {"state": empty, "parse_failed": True, "ready_to_finish": False, "next_question": None}
            return {
                "state": empty,
                "parse_failed": False,
                "ready_to_finish": False,
                "next_question": parsed.question,
                "focus": parsed.focus,
                "reasoning": parsed.reasoning,
                "question_source": SOURCE_MODEL,
            }

        prompt = ADAPTIVE_STEP_PROMPT_TEMPLATE.format(
            topic=topic,
            answered_count=state["answered_count"],
            max_questions=state["max_questions"],
            interaction_history=format_interaction_history(interactions),
            current_state=state_to_prompt_text(previous),
            missing_dimensions=unconfirmed_text(previous),
        )
        parsed = await _generate_and_parse(llm_provider, prompt, lambda raw: parse_turn(raw, topic))
        if parsed is None:
            # Nothing new can be learned from this answer; keep what was already known.
            carried = previous or DiscoveryLearnerState(original_topic=topic)
            return {"state": carried, "parse_failed": True, "ready_to_finish": False, "next_question": None, "assessment": None}

        new_state = ground_findings(parsed.state, _answers(interactions))
        return {
            "state": merge_states(previous, new_state, parsed.retractions),
            "parse_failed": False,
            "assessment": parsed.assessment,
            "ready_to_finish": parsed.ready_to_finish,
            "finish_reason": parsed.finish_reason,
            "focus": parsed.focus,
            "next_question": parsed.next_question,
            "reasoning": parsed.reasoning,
            "question_source": SOURCE_MODEL,
        }

    def guardrails_node(state: DiscoveryGraphState) -> Dict[str, Any]:
        """Deterministic rules: the safety limit, when finishing is justified by evidence, and one valid question."""
        learner_state: DiscoveryLearnerState = state["state"]
        answered = state.get("answered_count", 0)
        max_q = state["max_questions"]
        finishing = bool(state.get("ready_to_finish"))
        stopped_reason: Optional[str] = None

        if state["mode"] == "turn":
            if answered >= max_q:
                finishing, stopped_reason = True, "safety_limit"
            elif finishing:
                # Unsupported inference alone is never enough to stop.
                intent_ok = learner_state.is_confirmed("intent") or answered >= MIN_ANSWERS_TO_FINISH_WITHOUT_INTENT
                if learner_state.is_confirmed("understanding") and intent_ok:
                    stopped_reason = "sufficient"
                else:
                    finishing = False
                    logger.info(
                        "Finish request overridden: not established by the learner's own words: %s",
                        learner_state.unconfirmed_core(),
                    )

        if finishing:
            unresolved = list(learner_state.unresolved)
            for dim, kind in learner_state.unconfirmed_core():
                prefix = "Only inferred, not confirmed by the learner" if kind == "inferred" else "Not established"
                note = f"{prefix}: {DIMENSION_LABELS[dim]}"
                if note not in unresolved:
                    unresolved.append(note)
            learner_state = learner_state.model_copy(update={"unresolved": unresolved})
            return {
                "state": learner_state,
                "ready_to_finish": True,
                "stopped_reason": stopped_reason,
                "finish_reason": state.get("finish_reason") or (
                    "Reached the safety limit on questions." if stopped_reason == "safety_limit" else DEFAULT_FINISH_REASON
                ),
                "next_question": None,
                "question_issue": None,
            }

        issue = None
        if not state.get("parse_failed"):
            issue = question_problem(state.get("next_question"), _asked(state.get("interactions", [])))
        elif not state.get("next_question"):
            issue = "no usable question was produced"
        return {"ready_to_finish": False, "question_issue": issue}

    async def write_question_node(state: DiscoveryGraphState) -> Dict[str, Any]:
        """
        Obtain one valid question. Make a single bounded plain-text request that sees the transcript and
        learner state; if that is unusable, use a generic canned question, flagged as such. Neither path
        records any finding about the learner or ends discovery.
        """
        topic = state["topic"]
        interactions = state.get("interactions", [])
        asked = _asked(interactions)
        learner_state = state["state"]
        issue = state.get("question_issue") or "no usable question was produced"
        unconfirmed = learner_state.unconfirmed_core()
        if state["mode"] == "opening":
            focus_hint = "the learner's current mental model of the topic"
        elif unconfirmed:
            focus_hint = DIMENSION_LABELS[unconfirmed[0][0]]
        else:
            focus_hint = "whatever is most useful for personalizing the notes"

        prompt = TEXT_QUESTION_PROMPT_TEMPLATE.format(
            topic=topic,
            interaction_history=format_interaction_history(interactions),
            current_state=state_to_prompt_text(learner_state if state["mode"] == "turn" else None),
            asked_questions="\n".join(f"- {q}" for q in asked) or "(none)",
            problem_note=(
                f"\nThe previously proposed question was rejected because {issue}: \"{state['next_question'][:300]}\"\n"
                if state.get("next_question") and not state.get("parse_failed")
                else ""
            ),
            suggested_focus=focus_hint,
        )
        raw = await _generate(llm_provider, prompt, DISCOVERY_TEXT_SYSTEM_PROMPT)
        try:
            question, focus = parse_plain_question(raw)
        except DiscoveryParseError as err:
            logger.warning("Plain-text question recovery unusable: %s", err)
        else:
            problem = question_problem(question, asked)
            if problem is None:
                return {
                    "next_question": question,
                    "focus": focus or state.get("focus") or focus_hint.capitalize()[:60],
                    "question_issue": None,
                    "question_source": SOURCE_RECOVERED if state.get("parse_failed") else SOURCE_REWRITTEN,
                }
            logger.warning("Plain-text question recovery rejected: %s", problem)

        question, focus = fallback_question(topic, learner_state, asked)
        logger.info("Using flagged canned fallback discovery question (%s)", issue)
        return {"next_question": question, "focus": focus, "question_issue": None, "question_source": SOURCE_CANNED}

    def route_after_guardrails(state: DiscoveryGraphState) -> str:
        if not state.get("ready_to_finish") and state.get("question_issue"):
            return "write_question"
        return "done"

    builder = StateGraph(DiscoveryGraphState)
    builder.add_node("analyze_and_plan", analyze_and_plan_node)
    builder.add_node("guardrails", guardrails_node)
    builder.add_node("write_question", write_question_node)
    builder.add_edge(START, "analyze_and_plan")
    builder.add_edge("analyze_and_plan", "guardrails")
    builder.add_conditional_edges("guardrails", route_after_guardrails, {"write_question": "write_question", "done": END})
    builder.add_edge("write_question", END)
    return builder.compile()


async def run_initial_discovery(
    journey_id: str,
    topic: str,
    provider: LLMProvider,
    max_questions: int = 6,
) -> Dict[str, Any]:
    """Generates the single opening discovery question for a topic."""
    graph = build_discovery_graph(provider)
    result = await graph.ainvoke({
        "mode": "opening",
        "topic": topic,
        "interactions": [],
        "previous_state": None,
        "max_questions": max_questions,
        "answered_count": 0,
        "question_source": SOURCE_MODEL,
    })
    source = result.get("question_source", SOURCE_MODEL)
    return {
        "question_index": 1,
        "question_text": result["next_question"],
        "concept_target": result.get("focus") or "Current understanding",
        "is_finished": False,
        "reasoning": result.get("reasoning", ""),
        "question_source": source,
        "fallback_used": source == SOURCE_CANNED,
        "state": result["state"],
    }


async def run_adaptive_discovery_step(
    journey_id: str,
    topic: str,
    interactions: List[Dict[str, Any]],
    provider: LLMProvider,
    previous_state: Optional[DiscoveryLearnerState] = None,
    max_questions: int = 6,
) -> Dict[str, Any]:
    """
    Analyzes the learner's latest answer in the context of the whole conversation, updates the
    provisional learner state, and either selects the next question or finishes.
    `interactions` must contain every interaction so far, with the latest answer already filled in.
    """
    graph = build_discovery_graph(provider)
    answered = [i for i in interactions if i.get("learner_answer")]
    result = await graph.ainvoke({
        "mode": "turn",
        "topic": topic,
        "interactions": interactions,
        "previous_state": previous_state,
        "max_questions": max_questions,
        "answered_count": len(answered),
        "question_source": SOURCE_MODEL,
    })
    source = result.get("question_source", SOURCE_MODEL)
    return {
        "state": result["state"],
        "quick_assessment": result.get("assessment"),
        "is_finished": bool(result.get("ready_to_finish")),
        "finish_reason": result.get("finish_reason", ""),
        "stopped_reason": result.get("stopped_reason"),
        "next_question": result.get("next_question"),
        "next_concept_target": result.get("focus") or None,
        "reasoning": result.get("reasoning", ""),
        "question_source": source,
        "fallback_used": source == SOURCE_CANNED,
        "analysis_failed": bool(result.get("parse_failed")),
    }
