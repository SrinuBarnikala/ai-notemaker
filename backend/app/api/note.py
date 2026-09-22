import json
import re
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Response, status, Query
from sqlalchemy.orm import Session

from backend.app.config import Settings, get_settings
from backend.app.db.session import get_db
from backend.app.models.journey import LearningJourney
from backend.app.models.note import Note, NoteSection, NoteRevision
from backend.app.schemas.note import (
    NoteResponse,
    NoteSectionData,
    NoteBlock,
    NoteRevisionData,
    EvolveNoteRequest,
)
from backend.app.note.generator import generate_structured_note
from backend.app.note.evolver import evolve_structured_note, export_note_to_markdown

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

    revisions = (
        db.query(NoteRevision)
        .filter(NoteRevision.note_id == note.id)
        .order_by(NoteRevision.version.asc())
        .all()
    )
    revision_data_list = [
        NoteRevisionData(
            id=r.id,
            version=r.version,
            evolution_type=r.evolution_type,
            section_title=r.section_title,
            user_prompt=r.user_prompt,
            created_at=r.created_at,
        )
        for r in revisions
    ]

    return NoteResponse(
        id=note.id,
        journey_id=note.journey_id,
        topic=note.topic,
        version=note.version,
        summary=note.summary,
        sections=section_data_list,
        revisions=revision_data_list,
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


@router.post(
    "/journeys/{journey_id}/note/evolve",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
    tags=["Living Note Evolution"],
)
async def evolve_note_by_journey(
    journey_id: str,
    request: EvolveNoteRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Evolve the living note for a journey (update a section or append new section),
    incrementing version and logging revision history.
    """
    note = db.query(Note).filter(Note.journey_id == journey_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note for journey '{journey_id}' has not been generated yet.",
        )
    updated_note = await evolve_structured_note(
        note_id=note.id,
        request=request,
        db=db,
        settings=settings,
    )
    return build_note_response(updated_note, db)


@router.post(
    "/notes/{note_id}/evolve",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
    tags=["Living Note Evolution"],
)
async def evolve_note_by_id(
    note_id: str,
    request: EvolveNoteRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Evolve a structured living note directly by its unique Note ID.
    """
    updated_note = await evolve_structured_note(
        note_id=note_id,
        request=request,
        db=db,
        settings=settings,
    )
    return build_note_response(updated_note, db)


@router.get(
    "/notes/{note_id}/export",
    tags=["Living Note Export"],
)
def export_note_by_id(
    note_id: str,
    format: Literal["markdown", "json"] = Query("markdown", description="Export format"),
    db: Session = Depends(get_db),
):
    """
    Export the living structured note into GitHub-Flavored Markdown or raw JSON.
    """
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found.",
        )
    note_resp = build_note_response(note, db)

    clean_filename = re.sub(r"[^\w\s-]", "", note.topic).strip().replace(" ", "_").lower()
    if not clean_filename:
        clean_filename = "technical_note"
    filename = f"{clean_filename}_v{note.version}"

    if format == "markdown":
        md_text = export_note_to_markdown(note_resp)
        return Response(
            content=md_text,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}.md"',
            },
        )
    return note_resp


@router.get(
    "/journeys/{journey_id}/note/export",
    tags=["Living Note Export"],
)
def export_note_by_journey(
    journey_id: str,
    format: Literal["markdown", "json"] = Query("markdown", description="Export format"),
    db: Session = Depends(get_db),
):
    """
    Export the living structured note for a specific journey.
    """
    note = db.query(Note).filter(Note.journey_id == journey_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note for journey '{journey_id}' has not been generated yet.",
        )
    return export_note_by_id(note_id=note.id, format=format, db=db)

