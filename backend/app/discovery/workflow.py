import logging
from typing import TypedDict, List, Optional, Dict, Any
from langgraph.graph import StateGraph, START, END

from backend.app.providers.base import LLMProvider
from backend.app.discovery.prompts import (
    DISCOVERY_SYSTEM_PROMPT,
    INITIAL_QUESTION_PROMPT_TEMPLATE,
    ADAPTIVE_STEP_PROMPT_TEMPLATE,
)
from backend.app.discovery.parser import (
    parse_initial_question,
    parse_adaptive_step,
)

logger = logging.getLogger(__name__)


class DiscoveryState(TypedDict):
    journey_id: str
    topic: str
    interactions: List[Dict[str, Any]]
    current_question_index: int
    max_questions: int
    latest_answer: Optional[str]
    latest_question: Optional[str]
    latest_concept_target: Optional[str]
    quick_assessment: Optional[str]
    next_question: Optional[str]
    next_concept_target: Optional[str]
    is_finished: bool
    reasoning: Optional[str]


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


def build_discovery_graph(llm_provider: LLMProvider):
    """
    Builds the LangGraph StateGraph for the Knowledge Discovery workflow.
    """

    async def generate_initial_node(state: DiscoveryState) -> Dict[str, Any]:
        prompt = INITIAL_QUESTION_PROMPT_TEMPLATE.format(topic=state["topic"])
        try:
            raw_response = await llm_provider.generate(
                prompt=prompt,
                system_prompt=DISCOVERY_SYSTEM_PROMPT,
                temperature=0.4,
            )
        except Exception as err:
            logger.error("LLM call failed in initial question generation: %s", err)
            raw_response = ""

        parsed = parse_initial_question(raw_response, topic=state["topic"])
        return {
            "current_question_index": 1,
            "next_question": parsed.question,
            "next_concept_target": parsed.concept_target,
            "is_finished": False,
            "reasoning": parsed.reasoning,
        }

    async def evaluate_and_decide_node(state: DiscoveryState) -> Dict[str, Any]:
        curr_idx = state.get("current_question_index", 1)
        max_q = state.get("max_questions", 4)
        history_str = format_interaction_history(state.get("interactions", []))

        prompt = ADAPTIVE_STEP_PROMPT_TEMPLATE.format(
            topic=state["topic"],
            current_question_index=curr_idx,
            max_questions=max_q,
            interaction_history=history_str,
            latest_question=state.get("latest_question", ""),
            latest_answer=state.get("latest_answer", ""),
            latest_concept_target=state.get("latest_concept_target", ""),
        )

        try:
            raw_response = await llm_provider.generate(
                prompt=prompt,
                system_prompt=DISCOVERY_SYSTEM_PROMPT,
                temperature=0.4,
            )
        except Exception as err:
            logger.error("LLM call failed in adaptive discovery step: %s", err)
            raw_response = ""

        parsed = parse_adaptive_step(
            raw_text=raw_response,
            current_index=curr_idx,
            max_questions=max_q,
            topic=state["topic"],
        )

        return {
            "quick_assessment": parsed.quick_assessment,
            "is_finished": parsed.is_finished,
            "next_question": parsed.next_question,
            "next_concept_target": parsed.concept_target,
            "reasoning": parsed.reasoning,
        }

    builder = StateGraph(DiscoveryState)
    builder.add_node("generate_initial", generate_initial_node)
    builder.add_node("evaluate_and_decide", evaluate_and_decide_node)

    return builder


async def run_initial_discovery(
    journey_id: str,
    topic: str,
    provider: LLMProvider,
    max_questions: int = 4,
) -> Dict[str, Any]:
    """
    Executes LangGraph to generate the initial discovery question for a topic.
    """
    builder = build_discovery_graph(provider)
    builder.add_edge(START, "generate_initial")
    builder.add_edge("generate_initial", END)
    graph = builder.compile()

    initial_state: DiscoveryState = {
        "journey_id": journey_id,
        "topic": topic,
        "interactions": [],
        "current_question_index": 1,
        "max_questions": max_questions,
        "latest_answer": None,
        "latest_question": None,
        "latest_concept_target": None,
        "quick_assessment": None,
        "next_question": None,
        "next_concept_target": None,
        "is_finished": False,
        "reasoning": None,
    }

    result = await graph.ainvoke(initial_state)
    return {
        "question_index": 1,
        "question_text": result["next_question"],
        "concept_target": result["next_concept_target"],
        "is_finished": False,
        "reasoning": result.get("reasoning", ""),
    }


async def run_adaptive_discovery_step(
    journey_id: str,
    topic: str,
    interactions: List[Dict[str, Any]],
    current_question_index: int,
    latest_question: str,
    latest_concept_target: str,
    latest_answer: str,
    provider: LLMProvider,
    max_questions: int = 4,
) -> Dict[str, Any]:
    """
    Executes LangGraph to assess the learner's answer and produce the next adaptive probe or finish.
    """
    builder = build_discovery_graph(provider)
    builder.add_edge(START, "evaluate_and_decide")
    builder.add_edge("evaluate_and_decide", END)
    graph = builder.compile()

    state: DiscoveryState = {
        "journey_id": journey_id,
        "topic": topic,
        "interactions": interactions,
        "current_question_index": current_question_index,
        "max_questions": max_questions,
        "latest_answer": latest_answer,
        "latest_question": latest_question,
        "latest_concept_target": latest_concept_target,
        "quick_assessment": None,
        "next_question": None,
        "next_concept_target": None,
        "is_finished": False,
        "reasoning": None,
    }

    result = await graph.ainvoke(state)
    return {
        "quick_assessment": result.get("quick_assessment", ""),
        "is_finished": result.get("is_finished", False),
        "next_question": result.get("next_question"),
        "next_concept_target": result.get("next_concept_target"),
        "reasoning": result.get("reasoning", ""),
    }
