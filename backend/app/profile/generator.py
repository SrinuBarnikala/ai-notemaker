import json
import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.config import Settings
from backend.app.models.journey import LearningJourney
from backend.app.models.discovery import DiscoveryInteraction
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.schemas.profile import KnowledgeProfileResponse, ConceptItem
from backend.app.providers.factory import get_llm_provider
from backend.app.profile.prompts import (
    PROFILE_SYSTEM_PROMPT,
    PROFILE_GENERATION_PROMPT_TEMPLATE,
)
from backend.app.profile.parser import parse_knowledge_profile

logger = logging.getLogger(__name__)


def format_discovery_log(interactions: List[DiscoveryInteraction]) -> str:
    lines = []
    for item in interactions:
        lines.append(f"Turn {item.question_index} Target Concept: {item.concept_target}")
        lines.append(f"Question: {item.question_text}")
        lines.append(f"Learner Answer: {item.learner_answer}")
        if item.quick_assessment:
            lines.append(f"Assessed Observation: {item.quick_assessment}")
        lines.append("---")
    return "\n".join(lines)


async def generate_knowledge_profile(
    journey_id: str,
    db: Session,
    settings: Settings,
) -> KnowledgeProfileResponse:
    """
    Synthesizes the Knowledge Profile for a learning journey from its discovery interactions.
    """
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning journey '{journey_id}' not found.",
        )

    interactions = (
        db.query(DiscoveryInteraction)
        .filter(
            DiscoveryInteraction.journey_id == journey_id,
            DiscoveryInteraction.learner_answer != None,
        )
        .order_by(DiscoveryInteraction.question_index.asc())
        .all()
    )

    if not interactions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate knowledge profile without at least one answered discovery question.",
        )

    log_str = format_discovery_log(interactions)
    dict_interactions = [
        {
            "concept_target": i.concept_target,
            "learner_answer": i.learner_answer,
            "quick_assessment": i.quick_assessment,
        }
        for i in interactions
    ]

    prompt = PROFILE_GENERATION_PROMPT_TEMPLATE.format(
        topic=journey.topic,
        interaction_log=log_str,
    )

    provider = get_llm_provider(settings)
    try:
        raw_output = await provider.generate(
            prompt=prompt,
            system_prompt=PROFILE_SYSTEM_PROMPT,
            temperature=0.3,
        )
    except Exception as err:
        logger.error("LLM call failed in knowledge profile synthesis: %s", err)
        raw_output = ""

    parsed = parse_knowledge_profile(
        raw_text=raw_output,
        topic=journey.topic,
        interactions=dict_interactions,
    )

    # Persist or update existing profile
    profile = (
        db.query(KnowledgeProfile)
        .filter(KnowledgeProfile.journey_id == journey_id)
        .first()
    )

    if not profile:
        profile = KnowledgeProfile(
            journey_id=journey.id,
            overall_confidence=parsed.overall_confidence,
            summary=parsed.summary,
            misconceptions=json.dumps(parsed.misconceptions),
            gaps=json.dumps(parsed.gaps),
        )
        db.add(profile)
        db.flush()
    else:
        profile.overall_confidence = parsed.overall_confidence
        profile.summary = parsed.summary
        profile.misconceptions = json.dumps(parsed.misconceptions)
        profile.gaps = json.dumps(parsed.gaps)
        # Clear existing concepts
        db.query(KnowledgeConcept).filter(KnowledgeConcept.profile_id == profile.id).delete()
        db.flush()

    # Insert new concept records
    for c in parsed.concepts:
        concept_record = KnowledgeConcept(
            profile_id=profile.id,
            name=c.name,
            level=c.level,
            category=c.category,
            notes=c.notes,
        )
        db.add(concept_record)

    journey.status = "profile_ready"
    db.commit()
    db.refresh(profile)

    return KnowledgeProfileResponse(
        id=profile.id,
        journey_id=journey.id,
        topic=journey.topic,
        overall_confidence=profile.overall_confidence,  # type: ignore
        summary=profile.summary,
        concepts=parsed.concepts,
        misconceptions=parsed.misconceptions,
        gaps=parsed.gaps,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )
