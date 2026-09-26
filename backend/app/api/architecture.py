import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.config import Settings, get_settings
from backend.app.db.session import get_db
from backend.app.models.journey import LearningJourney
from backend.app.models.architecture import NoteArchitecture, NoteArchitectureSection
from backend.app.schemas.architecture import (
    GenerateArchitectureRequest,
    NoteArchitectureResponse,
    SectionBlueprint,
)
from backend.app.architecture.generator import generate_note_architecture

router = APIRouter()


@router.post(
    "/{journey_id}/architecture",
    response_model=NoteArchitectureResponse,
    status_code=status.HTTP_200_OK,
)
async def create_note_architecture(
    journey_id: str,
    payload: GenerateArchitectureRequest = GenerateArchitectureRequest(),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Generate and persist a personalized note architecture based on the learner's Knowledge Profile.
    """
    return await generate_note_architecture(
        journey_id=journey_id,
        learning_goal=payload.learning_goal or "Master core mechanics and practical architecture",
        db=db,
        settings=settings,
    )


@router.get(
    "/{journey_id}/architecture",
    response_model=NoteArchitectureResponse,
    status_code=status.HTTP_200_OK,
)
def get_note_architecture(
    journey_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve the current personalized Note Architecture for a journey.
    """
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning journey '{journey_id}' not found.",
        )

    arch = (
        db.query(NoteArchitecture)
        .filter(NoteArchitecture.journey_id == journey_id)
        .first()
    )
    if not arch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note architecture for journey '{journey_id}' has not been generated yet.",
        )

    sections = (
        db.query(NoteArchitectureSection)
        .filter(NoteArchitectureSection.architecture_id == arch.id)
        .order_by(NoteArchitectureSection.order_index.asc())
        .all()
    )

    section_blueprints = [
        SectionBlueprint(
            order_index=s.order_index,
            title=s.title,
            section_type=s.section_type,
            depth=s.depth,  # type: ignore
            target_concepts=json.loads(s.target_concepts or "[]"),
            rationale=s.rationale,
            needs_code=s.needs_code,
            needs_visual=s.needs_visual,
            visual_type=s.visual_type,
        )
        for s in sections
    ]

    return NoteArchitectureResponse(
        id=arch.id,
        journey_id=journey.id,
        topic=journey.topic,
        learning_goal=arch.learning_goal,
        summary_rationale=arch.summary_rationale,
        sections=section_blueprints,
        generation_status=getattr(arch, "generation_status", "llm_success") or "llm_success",
        generation_details=getattr(arch, "generation_details", None),
        created_at=arch.created_at,
        updated_at=arch.updated_at,
    )

