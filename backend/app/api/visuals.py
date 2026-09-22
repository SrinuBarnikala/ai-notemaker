import json
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.config import Settings, get_settings
from backend.app.models.journey import LearningJourney
from backend.app.models.note import Note, NoteSection
from backend.app.schemas.visuals import (
    VisualPlanItem,
    VisualPlanResponse,
    GenerateSectionVisualRequest,
    SectionVisualResponse,
)
from backend.app.providers.factory import get_llm_provider
from backend.app.visuals.planner import plan_visuals_for_note, generate_visual_for_section

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/journeys/{journey_id}/visuals/plan",
    response_model=VisualPlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Plan and synthesize architectural diagrams across note sections",
)
async def plan_visuals_endpoint(
    journey_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning journey '{journey_id}' not found.",
        )

    note = db.query(Note).filter(Note.journey_id == journey_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cannot plan visuals before generating a living note. Complete Phase 5 first.",
        )

    provider = get_llm_provider(settings)
    return await plan_visuals_for_note(note, db, provider)


@router.get(
    "/journeys/{journey_id}/visuals",
    response_model=VisualPlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve all architectural visual diagrams for a living note",
)
def get_visuals_endpoint(
    journey_id: str,
    db: Session = Depends(get_db),
):
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning journey '{journey_id}' not found.",
        )

    note = db.query(Note).filter(Note.journey_id == journey_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found for this learning journey.",
        )

    visual_items: List[VisualPlanItem] = []
    for sec in note.sections:
        try:
            sec_blocks = json.loads(sec.blocks) if isinstance(sec.blocks, str) else sec.blocks
        except Exception:
            sec_blocks = []

        for b in sec_blocks:
            if b.get("type") == "diagram":
                visual_items.append(
                    VisualPlanItem(
                        section_id=sec.id,
                        section_title=sec.title,
                        needs_visual=True,
                        visual_type=b.get("diagram_type", "flowchart"),
                        title=b.get("title", f"{sec.title} Diagram"),
                        diagram_spec=b.get("diagram_spec", ""),
                        caption=b.get("caption", ""),
                        rationale=b.get("visual_description", ""),
                    )
                )

    return VisualPlanResponse(
        journey_id=journey_id,
        note_id=note.id,
        visuals=visual_items,
        total_diagrams=len(visual_items),
    )


@router.post(
    "/journeys/{journey_id}/sections/{section_id}/visual",
    response_model=SectionVisualResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate or enhance an architectural visual diagram for a specific section",
)
async def generate_section_visual_endpoint(
    journey_id: str,
    section_id: str,
    request: GenerateSectionVisualRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning journey '{journey_id}' not found.",
        )

    provider = get_llm_provider(settings)
    return await generate_visual_for_section(journey_id, section_id, request, db, provider)
