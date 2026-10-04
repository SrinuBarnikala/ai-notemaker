import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.config import Settings
from backend.app.models.journey import LearningJourney
from backend.app.models.discovery import DiscoveryInteraction
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.models.architecture import NoteArchitecture, NoteArchitectureSection
from backend.app.schemas.architecture import NoteArchitectureResponse, SectionBlueprint
from backend.app.providers.factory import get_llm_provider
from backend.app.architecture.prompts import (
    ARCHITECTURE_SYSTEM_PROMPT,
    ARCHITECTURE_GENERATION_PROMPT_TEMPLATE,
)
from backend.app.architecture.parser import parse_note_architecture
from backend.app.personalization.builder import PersonalizationContextBuilder
from backend.app.personalization.models import PersonalizationContext

logger = logging.getLogger(__name__)


def format_concepts_for_prompt(concepts: List[Any]) -> str:
    if not concepts:
        return "No specific concepts classified."
    lines = []
    for c in concepts:
        if isinstance(c, str):
            lines.append(f"- {c}")
        elif hasattr(c, "name"):
            notes = getattr(c, "notes", None) or "No notes"
            lines.append(f"- {c.name} (level: {getattr(c, 'level', 'unknown')}, category: {getattr(c, 'category', 'general')}): {notes}")
        elif isinstance(c, dict):
            notes = c.get("notes") or "No notes"
            lines.append(f"- {c.get('name', '')} (level: {c.get('level', 'unknown')}, category: {c.get('category', 'general')}): {notes}")
    return "\n".join(lines) or "No specific concepts classified."


async def generate_note_architecture(
    journey_id: str,
    db: Session,
    settings: Settings,
    learning_goal: Optional[str] = "Master core mechanics, resolve gaps, and implement in production",
    user_id: Optional[str] = None,
) -> NoteArchitectureResponse:
    """
    Synthesizes a personalized NoteArchitecture for a learning journey based on its KnowledgeProfile
    and unified PersonalizationContext.
    """
    profile = (
        db.query(KnowledgeProfile)
        .filter(KnowledgeProfile.journey_id == journey_id)
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate note architecture without a completed knowledge profile.",
        )

    # Build unified personalization context (enforces journey validation & ownership)
    context: PersonalizationContext = PersonalizationContextBuilder.build(
        journey_id=journey_id,
        db=db,
        user_id=user_id,
    )

    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()

    # Preserve compact discovery interaction summary
    interactions = (
        db.query(DiscoveryInteraction)
        .filter(DiscoveryInteraction.journey_id == journey_id)
        .order_by(DiscoveryInteraction.question_index.asc())
        .all()
    )
    discovery_lines = []
    for item in interactions:
        if item.learner_answer:
            target = item.concept_target or "General"
            discovery_lines.append(f"- Concept: {target} | Learner stated: '{item.learner_answer}'")
            if item.quick_assessment:
                discovery_lines.append(f"  Assessed: {item.quick_assessment}")
    discovery_summary = "\n".join(discovery_lines) or "No prior discovery responses recorded."

    # Format structured concept classifications from context
    concept_lines = []
    for c in context.known_concepts:
        concept_lines.append(f"- {c} (level: strong, category: known)")
    for c in context.partially_known_concepts:
        concept_lines.append(f"- {c} (level: moderate, category: partially_known)")
    concepts_formatted = "\n".join(concept_lines) or "No specific concepts classified."

    dict_concepts = [
        {"name": c, "level": "strong", "category": "known", "notes": None}
        for c in context.known_concepts
    ] + [
        {"name": c, "level": "moderate", "category": "partially_known", "notes": None}
        for c in context.partially_known_concepts
    ]

    misconceptions_formatted = (
        "\n".join(f"- {m}" for m in context.misconceptions) or "None detected."
    )
    gaps_formatted = (
        "\n".join(f"- {g}" for g in context.active_gaps) or "None explicitly flagged."
    )

    verified_mastery_formatted = (
        ", ".join(context.verified_mastered_concepts)
        if context.verified_mastered_concepts
        else "None verified yet"
    )
    prior_concepts_formatted = (
        ", ".join(context.prior_related_concepts)
        if context.prior_related_concepts
        else "None recorded from prior journeys"
    )

    prompt = ARCHITECTURE_GENERATION_PROMPT_TEMPLATE.format(
        topic=context.topic,
        learning_goal=learning_goal,
        experience_level=context.experience_level,
        preferred_language=context.preferred_language,
        explanation_depth=context.explanation_depth,
        learning_style=context.learning_style,
        target_goals=context.target_goals or "None explicitly specified",
        verified_mastery_formatted=verified_mastery_formatted,
        prior_concepts_formatted=prior_concepts_formatted,
        overall_confidence=context.overall_confidence,
        summary=context.mental_model_summary,
        discovery_summary=discovery_summary,
        concepts_formatted=concepts_formatted,
        misconceptions_formatted=misconceptions_formatted,
        gaps_formatted=gaps_formatted,
    )

    provider = get_llm_provider(settings)
    failure_reason = None
    try:
        raw_output = await provider.generate(
            prompt=prompt,
            system_prompt=ARCHITECTURE_SYSTEM_PROMPT,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
    except Exception as err:
        logger.error("LLM call failed in note architecture generation: %s", err)
        raw_output = ""
        failure_reason = f"Provider exception: {err}"

    parsed = parse_note_architecture(
        raw_text=raw_output,
        topic=context.topic,
        profile_summary=context.mental_model_summary,
        concepts=dict_concepts,
        gaps=context.active_gaps,
        misconceptions=context.misconceptions,
    )

    generation_status = "llm_fallback" if parsed.used_fallback else "llm_success"
    generation_details = {
        "provider": provider.provider_name,
        "model": provider.model_name,
        "fallback_used": parsed.used_fallback,
        "failure_reason": parsed.failure_reason or failure_reason,
    }

    # Persist or update existing architecture
    arch = (
        db.query(NoteArchitecture)
        .filter(NoteArchitecture.journey_id == journey_id)
        .first()
    )

    if not arch:
        arch = NoteArchitecture(
            journey_id=journey.id,
            topic=journey.topic,
            learning_goal=learning_goal,
            summary_rationale=parsed.summary_rationale,
            generation_status=generation_status,
            generation_details=json.dumps(generation_details),
        )
        db.add(arch)
        db.flush()
    else:
        arch.learning_goal = learning_goal
        arch.summary_rationale = parsed.summary_rationale
        arch.generation_status = generation_status
        arch.generation_details = json.dumps(generation_details)
        # Clear existing sections
        db.query(NoteArchitectureSection).filter(NoteArchitectureSection.architecture_id == arch.id).delete()
        db.flush()

    for s in parsed.sections:
        sec_record = NoteArchitectureSection(
            architecture_id=arch.id,
            order_index=s.order_index,
            title=s.title,
            section_type=s.section_type,
            depth=s.depth,
            target_concepts=json.dumps(s.target_concepts),
            rationale=s.rationale,
            needs_code=s.needs_code,
            needs_visual=s.needs_visual,
            visual_type=s.visual_type,
        )
        db.add(sec_record)

    journey.status = "architecture_ready"
    db.commit()
    db.refresh(arch)

    return NoteArchitectureResponse(
        id=arch.id,
        journey_id=journey.id,
        topic=journey.topic,
        learning_goal=arch.learning_goal,
        summary_rationale=arch.summary_rationale,
        sections=parsed.sections,
        generation_status=arch.generation_status,
        generation_details=arch.generation_details,
        created_at=arch.created_at,
        updated_at=arch.updated_at,
    )
