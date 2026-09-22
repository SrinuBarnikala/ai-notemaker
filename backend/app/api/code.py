import json
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.config import Settings, get_settings
from backend.app.models.journey import LearningJourney
from backend.app.models.note import Note, NoteSection
from backend.app.schemas.code import (
    CodePlanItem,
    CodePlanResponse,
    GenerateSectionCodeRequest,
    SectionCodeResponse,
)
from backend.app.providers.factory import get_llm_provider
from backend.app.code.planner import (
    plan_code_for_note,
    generate_code_for_section,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/journeys/{journey_id}/code/plan",
    response_model=CodePlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Plan and synthesize executable code implementations across living note sections",
)
async def plan_code_endpoint(
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
            detail="Cannot plan code before generating a living note. Complete Phase 5 first.",
        )

    provider = get_llm_provider(settings)
    return await plan_code_for_note(note, db, provider)


@router.get(
    "/journeys/{journey_id}/code",
    response_model=CodePlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve all code blocks and runtime metadata for a living note",
)
def get_code_blocks_endpoint(
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
            detail="Living note not found for this journey.",
        )

    items: List[CodePlanItem] = []
    for section in note.sections:
        try:
            blocks = json.loads(section.blocks) if isinstance(section.blocks, str) else (section.blocks or [])
        except Exception:
            blocks = []
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "code":
                items.append(
                    CodePlanItem(
                        section_id=section.id,
                        section_title=section.title,
                        needs_code=True,
                        language=b.get("language") or "python",
                        purpose=b.get("title") or f"{section.title} Implementation",
                        code=b.get("code") or "",
                        runnable=bool(b.get("runnable", True)),
                        expected_output=b.get("expected_output"),
                        complexity=b.get("complexity") or "Time: O(N) | Space: O(1)",
                        test_cases=b.get("test_cases"),
                    )
                )

    return CodePlanResponse(
        journey_id=journey_id,
        note_id=note.id,
        code_items=items,
        total_code_blocks=len(items),
    )


@router.post(
    "/journeys/{journey_id}/sections/{section_id}/code",
    response_model=SectionCodeResponse,
    status_code=status.HTTP_200_OK,
    summary="Synthesize or customize an executable code block for a specific note section",
)
async def generate_section_code_endpoint(
    journey_id: str,
    section_id: str,
    request: GenerateSectionCodeRequest,
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
    return await generate_code_for_section(journey_id, section_id, request, db, provider)
