import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.config import Settings, get_settings
from backend.app.db.session import get_db
from backend.app.models.journey import LearningJourney
from backend.app.models.note import Note, NoteSection
from backend.app.schemas.note import NoteResponse, NoteSectionData, NoteBlock
from backend.app.note.generator import generate_structured_note

router = APIRouter()


def build_note_response(note: Note, db: Session) -> NoteResponse:
    sections = (
        db.query(NoteSection)
        .filter(NoteSection.note_id == note.id)
        .order_by(NoteSection.order_index.asc())
        .all()
    )

    section_data_list = []
    for s in sections:
        raw_blocks = json.loads(s.blocks or "[]")
        blocks = [NoteBlock(**b) for b in raw_blocks]
        section_data_list.append(
            NoteSectionData(
                id=s.id,
                order_index=s.order_index,
                title=s.title,
                section_type=s.section_type,
                depth=s.depth,
                blocks=blocks,
            )
        )

    return NoteResponse(
        id=note.id,
        journey_id=note.journey_id,
        topic=note.topic,
        version=note.version,
        summary=note.summary,
        sections=section_data_list,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.post(
    "/journeys/{journey_id}/generate-note",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
    tags=["Notes"],
)
async def generate_note_endpoint(
    journey_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Generate and persist the canonical living structured note based on the personalized architecture.
    """
    return await generate_structured_note(
        journey_id=journey_id,
        db=db,
        settings=settings,
    )


@router.get(
    "/journeys/{journey_id}/note",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
    tags=["Notes"],
)
def get_note_by_journey(
    journey_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve the structured note for a specific learning journey.
    """
    note = db.query(Note).filter(Note.journey_id == journey_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note for journey '{journey_id}' has not been generated yet.",
        )
    return build_note_response(note, db)


@router.get(
    "/notes/{note_id}",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
    tags=["Notes"],
)
def get_note_by_id(
    note_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve a structured note directly by its unique Note ID.
    """
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found.",
        )
    return build_note_response(note, db)
