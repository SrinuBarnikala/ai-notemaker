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
    NoteVersionItem,
    NoteVersionsListResponse,
    NoteVersionDiffResponse,
    RestoreVersionResponse,
    EvolveNoteRequest,
)
from backend.app.note.generator import generate_structured_note
from backend.app.note.evolver import evolve_structured_note, export_note_to_markdown
from backend.app.note.pdf import generate_note_pdf
from backend.app.note.versioning import (
    list_note_versions,
    get_note_version_response,
    compute_note_diff,
    restore_note_version,
)

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
                generation_status=getattr(s, "generation_status", "llm_success") or "llm_success",
                generation_details=json.loads(s.generation_details) if getattr(s, "generation_details", None) else None,
            )
        )

    revisions = (
        db.query(NoteRevision)
        .filter(
            NoteRevision.note_id == note.id,
            NoteRevision.evolution_type != "initial_generation",
        )
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
            change_summary=r.change_summary,
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
        generation_status=getattr(note, "generation_status", "llm_success") or "llm_success",
        generation_details=getattr(note, "generation_details", None),
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
    format: Literal["markdown", "json", "pdf"] = Query("markdown", description="Export format"),
    db: Session = Depends(get_db),
):
    """
    Export the living structured note into GitHub-Flavored Markdown, raw JSON, or publication-ready PDF.
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
    elif format == "pdf":
        pdf_bytes = generate_note_pdf(note_resp)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}.pdf"',
            },
        )
    return note_resp


@router.get(
    "/notes/{note_id}/export/pdf",
    tags=["Living Note Export"],
    summary="Export living note as a publication-ready PDF document",
)
def export_note_pdf_endpoint(
    note_id: str,
    db: Session = Depends(get_db),
):
    """
    Direct endpoint to export the living note as a print-ready PDF document.
    """
    return export_note_by_id(note_id=note_id, format="pdf", db=db)


@router.get(
    "/journeys/{journey_id}/note/export",
    tags=["Living Note Export"],
)
def export_note_by_journey(
    journey_id: str,
    format: Literal["markdown", "json", "pdf"] = Query("markdown", description="Export format"),
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


@router.get(
    "/journeys/{journey_id}/note/export/pdf",
    tags=["Living Note Export"],
    summary="Export journey living note as a publication-ready PDF document",
)
def export_journey_note_pdf_endpoint(
    journey_id: str,
    db: Session = Depends(get_db),
):
    """
    Direct endpoint to export the journey living note as a print-ready PDF document.
    """
    return export_note_by_journey(journey_id=journey_id, format="pdf", db=db)


# ==========================================
# PHASE 13 — NOTE VERSIONING & DIFF APIS
# ==========================================

@router.get(
    "/notes/{note_id}/versions",
    response_model=NoteVersionsListResponse,
    status_code=status.HTTP_200_OK,
    tags=["Note Versioning"],
    summary="List all versions of a living note",
)
def get_note_versions_endpoint(
    note_id: str,
    db: Session = Depends(get_db),
):
    """
    Returns an audit list of all version snapshots for the specified note,
    including version number, timestamp, evolution triggers, and change summaries.
    """
    return list_note_versions(note_id=note_id, db=db)


@router.get(
    "/journeys/{journey_id}/note/versions",
    response_model=NoteVersionsListResponse,
    status_code=status.HTTP_200_OK,
    tags=["Note Versioning"],
    summary="List all versions of a living note for a journey",
)
def get_journey_note_versions_endpoint(
    journey_id: str,
    db: Session = Depends(get_db),
):
    note = db.query(Note).filter(Note.journey_id == journey_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note for journey '{journey_id}' has not been generated yet.",
        )
    return list_note_versions(note_id=note.id, db=db)


@router.get(
    "/notes/{note_id}/versions/{version}",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
    tags=["Note Versioning"],
    summary="Retrieve exact historical snapshot of a note version",
)
def get_note_version_snapshot_endpoint(
    note_id: str,
    version: int,
    db: Session = Depends(get_db),
):
    """
    Returns the complete structured note as it existed at the specified historical version.
    """
    return get_note_version_response(note_id=note_id, version=version, db=db)


@router.get(
    "/journeys/{journey_id}/note/versions/{version}",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
    tags=["Note Versioning"],
    summary="Retrieve exact historical snapshot of a note version by journey",
)
def get_journey_note_version_snapshot_endpoint(
    journey_id: str,
    version: int,
    db: Session = Depends(get_db),
):
    note = db.query(Note).filter(Note.journey_id == journey_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note for journey '{journey_id}' has not been generated yet.",
        )
    return get_note_version_response(note_id=note.id, version=version, db=db)


@router.get(
    "/notes/{note_id}/diff",
    response_model=NoteVersionDiffResponse,
    status_code=status.HTTP_200_OK,
    tags=["Note Versioning"],
    summary="Compute semantic diff between two versions of a note",
)
def get_note_diff_endpoint(
    note_id: str,
    from_version: int = Query(..., ge=1, description="Base historical version"),
    to_version: int = Query(..., ge=1, description="Target version to compare against"),
    db: Session = Depends(get_db),
):
    """
    Compares two note versions and generates a granular section and block-level diff
    highlighting additions, removals, and modifications.
    """
    return compute_note_diff(
        note_id=note_id,
        from_version=from_version,
        to_version=to_version,
        db=db,
    )


@router.get(
    "/journeys/{journey_id}/note/diff",
    response_model=NoteVersionDiffResponse,
    status_code=status.HTTP_200_OK,
    tags=["Note Versioning"],
    summary="Compute semantic diff between two versions of a note by journey",
)
def get_journey_note_diff_endpoint(
    journey_id: str,
    from_version: int = Query(..., ge=1, description="Base historical version"),
    to_version: int = Query(..., ge=1, description="Target version to compare against"),
    db: Session = Depends(get_db),
):
    note = db.query(Note).filter(Note.journey_id == journey_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note for journey '{journey_id}' has not been generated yet.",
        )
    return compute_note_diff(
        note_id=note.id,
        from_version=from_version,
        to_version=to_version,
        db=db,
    )


@router.post(
    "/notes/{note_id}/versions/{version}/restore",
    response_model=RestoreVersionResponse,
    status_code=status.HTTP_200_OK,
    tags=["Note Versioning"],
    summary="Restore living note to match a historical version snapshot",
)
def restore_note_version_endpoint(
    note_id: str,
    version: int,
    db: Session = Depends(get_db),
):
    """
    Restores the living note state to match a selected historical version,
    creating a new version checkpoint (non-destructive rollback).
    """
    return restore_note_version(note_id=note_id, target_version=version, db=db)


@router.post(
    "/journeys/{journey_id}/note/versions/{version}/restore",
    response_model=RestoreVersionResponse,
    status_code=status.HTTP_200_OK,
    tags=["Note Versioning"],
    summary="Restore living note to match a historical version snapshot by journey",
)
def restore_journey_note_version_endpoint(
    journey_id: str,
    version: int,
    db: Session = Depends(get_db),
):
    note = db.query(Note).filter(Note.journey_id == journey_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note for journey '{journey_id}' has not been generated yet.",
        )
    return restore_note_version(note_id=note.id, target_version=version, db=db)


