import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.config import Settings, get_settings
from backend.app.db.session import get_db
from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.schemas.profile import KnowledgeProfileResponse, ConceptItem
from backend.app.profile.generator import generate_knowledge_profile

router = APIRouter()


@router.post(
    "/{journey_id}/knowledge-profile",
    response_model=KnowledgeProfileResponse,
    status_code=status.HTTP_200_OK,
)
async def create_or_update_knowledge_profile(
    journey_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Synthesize and persist the learner's Knowledge Profile from discovery dialogue.
    """
    return await generate_knowledge_profile(
        journey_id=journey_id,
        db=db,
        settings=settings,
    )


@router.get(
    "/{journey_id}/knowledge-profile",
    response_model=KnowledgeProfileResponse,
    status_code=status.HTTP_200_OK,
)
def get_knowledge_profile(
    journey_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve the current Knowledge Profile for a learning journey.
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge profile for journey '{journey_id}' has not been generated yet.",
        )

    concepts = (
        db.query(KnowledgeConcept)
        .filter(KnowledgeConcept.profile_id == profile.id)
        .all()
    )
    concept_items = [
        ConceptItem(
            name=c.name,
            level=c.level,  # type: ignore
            category=c.category,  # type: ignore
            notes=c.notes,
        )
        for c in concepts
    ]

    misconceptions = json.loads(profile.misconceptions or "[]")
    gaps = json.loads(profile.gaps or "[]")

    return KnowledgeProfileResponse(
        id=profile.id,
        journey_id=journey.id,
        topic=journey.topic,
        overall_confidence=profile.overall_confidence,  # type: ignore
        summary=profile.summary,
        concepts=concept_items,
        misconceptions=misconceptions,
        gaps=gaps,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )
