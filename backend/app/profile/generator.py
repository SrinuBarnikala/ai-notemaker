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
from backend.app.discovery.groups import normalize_interaction
from backend.app.discovery.state import (
    DISCOVERY_CONCLUDED_STATUSES,
    load_analysis,
    same_finding,
    load_state,
    state_to_context_dict,
    state_to_prompt_text,
)

logger = logging.getLogger(__name__)


def format_discovery_log(interactions: List[DiscoveryInteraction]) -> str:
    lines = []
    for item in interactions:
        group = normalize_interaction(item.question_text, item.subquestions, item.motive, item.questions)
        lines.append(f"Turn {item.question_index} Focus: {item.concept_target}")
        if group.motive:
            lines.append(f"Motive: {group.motive}")
        for q in group.questions:
            lines.append(f"  Question: {q}")
        lines.append(f"Learner Answer (one reply to the whole group): {item.learner_answer}")
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

    # Learner state recorded by the most recent analyzed answer (absent for legacy sessions)
    learner_state = None
    last_analysis: dict = {}
    for item in interactions:
        state = load_state(item.analysis)
        if state is not None:
            learner_state, last_analysis = state, load_analysis(item.analysis)

    prompt = PROFILE_GENERATION_PROMPT_TEMPLATE.format(
        topic=journey.topic,
        interaction_log=log_str,
        learner_state=state_to_prompt_text(learner_state) if learner_state else "Not recorded for this session.",
    )

    provider = get_llm_provider(settings)
    try:
        raw_output = await provider.generate(
            prompt=prompt,
            system_prompt=PROFILE_SYSTEM_PROMPT,
            temperature=0.3,
        )
    except Exception as err:
        # A provider outage is not a reason to persist a made-up profile; the caller can retry.
        logger.error("LLM call failed in knowledge profile synthesis: %s", err)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI service could not be reached while building your profile. Please try again in a moment.",
        )

    parsed = parse_knowledge_profile(
        raw_text=raw_output,
        topic=journey.topic,
        interactions=dict_interactions,
        learner_state=learner_state,
    )

    # Whatever the model says, findings the learner corrected during discovery are not current.
    if learner_state is not None and learner_state.resolved:
        retired = [r.value for r in learner_state.resolved if r.field in ("misconceptions", "gaps")]
        parsed.misconceptions = [m for m in parsed.misconceptions if not any(same_finding(m, r) for r in retired)]
        parsed.gaps = [g for g in parsed.gaps if not any(same_finding(g, r) for r in retired)]

    learner_context = None
    if learner_state is not None:
        analyses = [load_analysis(i.analysis) for i in interactions]
        learner_context = state_to_context_dict(learner_state)
        learner_context["discovery"] = {
            "answered_questions": sum(
                normalize_interaction(i.question_text, i.subquestions, i.motive, i.questions).units for i in interactions
            ),
            "answered_groups": len(interactions),
            "coverage": last_analysis.get("coverage") or None,
            "completed": journey.status in DISCOVERY_CONCLUDED_STATUSES,
            "stopped_reason": last_analysis.get("stopped_reason"),
            "fallback_questions": sum(1 for a in analyses if a.get("question_fallback")),
            "unanalyzed_answers": sum(1 for a in analyses if a.get("analysis_failed")),
            "profile_synthesis": "fallback" if parsed.used_fallback else "model",
        }
    elif parsed.used_fallback:
        # Legacy session (no stored discovery state): still record that this profile is a fallback
        learner_context = {"discovery": {"profile_synthesis": "fallback"}}
    learner_context_json = json.dumps(learner_context) if learner_context is not None else None

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
            learner_context=learner_context_json,
        )
        db.add(profile)
        db.flush()
    else:
        profile.overall_confidence = parsed.overall_confidence
        profile.summary = parsed.summary
        profile.misconceptions = json.dumps(parsed.misconceptions)
        profile.gaps = json.dumps(parsed.gaps)
        profile.learner_context = learner_context_json
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

    # Regenerating a profile (for example a retry) must not move a journey that has already
    # progressed to the architecture or note stage backwards.
    if journey.status in ("created", "discovery", "discovery_completed", "profile_ready"):
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
        learner_context=learner_context,
        synthesis_fallback=parsed.used_fallback,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )
