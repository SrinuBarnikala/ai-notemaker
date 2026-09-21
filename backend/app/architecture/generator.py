import json
import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.config import Settings
from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.models.architecture import NoteArchitecture, NoteArchitectureSection
from backend.app.schemas.architecture import NoteArchitectureResponse, SectionBlueprint
from backend.app.providers.factory import get_llm_provider
from backend.app.architecture.prompts import (
    ARCHITECTURE_SYSTEM_PROMPT,
    ARCHITECTURE_GENERATION_PROMPT_TEMPLATE,
)
from backend.app.architecture.parser import parse_note_architecture

logger = logging.getLogger(__name__)


def format_concepts_for_prompt(concepts: List[KnowledgeConcept]) -> str:
    if not concepts:
        return "No granular concepts mapped."
    lines = []
    for c in concepts:
        lines.append(f"- {c.name} [Level: {c.level}, Category: {c.category}] Notes: {c.notes or 'N/A'}")
    return "\n".join(lines)


async def generate_note_architecture(
    journey_id: str,
    learning_goal: str,
    db: Session,
    settings: Settings,
) -> NoteArchitectureResponse:
    """
    Synthesizes and persists a personalized note architecture based on the learner's Knowledge Profile.
    """
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning journey '{journey_id}' not found.",
        )

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

    concepts = (
        db.query(KnowledgeConcept)
        .filter(KnowledgeConcept.profile_id == profile.id)
        .all()
    )

    misconceptions = json.loads(profile.misconceptions or "[]")
    gaps = json.loads(profile.gaps or "[]")

    concepts_formatted = format_concepts_for_prompt(concepts)
    misconceptions_formatted = "\n".join(f"- {m}" for m in misconceptions) or "None detected."
    gaps_formatted = "\n".join(f"- {g}" for g in gaps) or "None explicitly flagged."

    prompt = ARCHITECTURE_GENERATION_PROMPT_TEMPLATE.format(
        topic=journey.topic,
        learning_goal=learning_goal,
        overall_confidence=profile.overall_confidence,
        summary=profile.summary,
        concepts_formatted=concepts_formatted,
        misconceptions_formatted=misconceptions_formatted,
        gaps_formatted=gaps_formatted,
    )

    dict_concepts = [
        {"name": c.name, "level": c.level, "category": c.category, "notes": c.notes}
        for c in concepts
    ]

    provider = get_llm_provider(settings)
    try:
        raw_output = await provider.generate(
            prompt=prompt,
            system_prompt=ARCHITECTURE_SYSTEM_PROMPT,
            temperature=0.3,
        )
    except Exception as err:
        logger.error("LLM call failed in note architecture generation: %s", err)
        raw_output = ""

    parsed = parse_note_architecture(
        raw_text=raw_output,
        topic=journey.topic,
        profile_summary=profile.summary,
        concepts=dict_concepts,
        gaps=gaps,
        misconceptions=misconceptions,
    )

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
        )
        db.add(arch)
        db.flush()
    else:
        arch.learning_goal = learning_goal
        arch.summary_rationale = parsed.summary_rationale
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
        created_at=arch.created_at,
        updated_at=arch.updated_at,
    )
