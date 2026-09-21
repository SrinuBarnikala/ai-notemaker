import json
import logging
import re
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class InitialQuestionParsed(BaseModel):
    question: str = Field(..., min_length=5)
    concept_target: str = Field(..., min_length=2)
    reasoning: Optional[str] = ""


class AdaptiveStepParsed(BaseModel):
    quick_assessment: str = Field(..., min_length=3)
    is_finished: bool = False
    next_question: Optional[str] = None
    concept_target: Optional[str] = None
    reasoning: Optional[str] = ""


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Extracts and parses a JSON object from raw LLM text, safely handling
    markdown backticks, preamble, and postscript comments.
    """
    clean = text.strip()

    # Remove markdown code blocks if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean)
    if match:
        clean = match.group(1).strip()

    # Find boundaries of the outermost JSON object
    start = clean.find("{")
    end = clean.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = clean[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Direct parse attempt
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return None


def parse_initial_question(raw_text: str, topic: str) -> InitialQuestionParsed:
    """
    Parses LLM output for initial question. Falls back to deterministic domain question
    if LLM output is malformed.
    """
    data = extract_json_object(raw_text)
    if data:
        try:
            return InitialQuestionParsed(
                question=str(data.get("question", "")).strip(),
                concept_target=str(data.get("concept_target", topic)).strip() or topic,
                reasoning=str(data.get("reasoning", "")).strip(),
            )
        except Exception as e:
            logger.warning("Pydantic validation failed for initial question: %s", e)

    # Safe deterministic fallback
    logger.info("Using fallback for initial discovery question on topic: %s", topic)
    return InitialQuestionParsed(
        question=f"What is your high-level mental model of {topic}, and how would you explain its primary purpose?",
        concept_target="Core Foundations",
        reasoning="Fallback initialized to establish broad baseline understanding.",
    )


def parse_adaptive_step(
    raw_text: str,
    current_index: int,
    max_questions: int,
    topic: str,
) -> AdaptiveStepParsed:
    """
    Parses LLM output for adaptive next step. Enforces max_questions termination
    and provides safe fallbacks.
    """
    data = extract_json_object(raw_text)

    # If maximum turns reached, always enforce termination
    if current_index >= max_questions:
        assessment = "Completed discovery across key concepts."
        if data and data.get("quick_assessment"):
            assessment = str(data["quick_assessment"]).strip()
        return AdaptiveStepParsed(
            quick_assessment=assessment,
            is_finished=True,
            next_question=None,
            concept_target=None,
            reasoning=f"Reached maximum discovery limit ({max_questions} questions).",
        )

    if data:
        try:
            is_finished = bool(data.get("is_finished", False))
            next_q = data.get("next_question")
            next_target = data.get("concept_target")

            if is_finished or not next_q:
                return AdaptiveStepParsed(
                    quick_assessment=str(data.get("quick_assessment", "Sufficient knowledge discovered.")).strip(),
                    is_finished=True,
                    next_question=None,
                    concept_target=None,
                    reasoning=str(data.get("reasoning", "")).strip(),
                )

            return AdaptiveStepParsed(
                quick_assessment=str(data.get("quick_assessment", "Answer analyzed.")).strip(),
                is_finished=False,
                next_question=str(next_q).strip(),
                concept_target=str(next_target or "Advanced Concepts").strip(),
                reasoning=str(data.get("reasoning", "")).strip(),
            )
        except Exception as e:
            logger.warning("Pydantic validation failed for adaptive step: %s", e)

    # Safe deterministic fallback
    return AdaptiveStepParsed(
        quick_assessment=f"Noted your perspective on {topic}.",
        is_finished=(current_index >= max_questions - 1),
        next_question=(
            f"Have you implemented or debugged {topic} in practice, and what trade-offs did you encounter?"
            if current_index < max_questions - 1
            else None
        ),
        concept_target="Practical Implementation" if current_index < max_questions - 1 else None,
        reasoning="Fallback adaptive question probing practical implementation experience.",
    )
