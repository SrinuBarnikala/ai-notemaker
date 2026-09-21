import json
import logging
from typing import List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.config import Settings
from backend.app.models.journey import LearningJourney
from backend.app.models.architecture import NoteArchitecture, NoteArchitectureSection
from backend.app.models.note import Note, NoteSection
from backend.app.schemas.note import NoteResponse, NoteSectionData, NoteBlock
from backend.app.providers.factory import get_llm_provider
from backend.app.note.prompts import (
    NOTE_GENERATION_SYSTEM_PROMPT,
    SECTION_GENERATION_PROMPT_TEMPLATE,
)
from backend.app.note.parser import parse_section_blocks

logger = logging.getLogger(__name__)


async def generate_structured_note(
    journey_id: str,
    db: Session,
    settings: Settings,
) -> NoteResponse:
    """
    Generates and persists the canonical living technical note based on the personalized Note Architecture.
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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate note without a completed note architecture. Run Phase 4 first.",
        )

    sections = (
        db.query(NoteArchitectureSection)
        .filter(NoteArchitectureSection.architecture_id == arch.id)
        .order_by(NoteArchitectureSection.order_index.asc())
        .all()
    )

    if not sections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Note architecture contains no sections.",
        )

    provider = get_llm_provider(settings)
    generated_sections_data = []

    # Persist or update Note container
    note = db.query(Note).filter(Note.journey_id == journey_id).first()
    if not note:
        note = Note(
            journey_id=journey.id,
            topic=journey.topic,
            version=1,
            summary=arch.summary_rationale,
        )
        db.add(note)
        db.flush()
    else:
        note.summary = arch.summary_rationale
        note.version += 1
        db.query(NoteSection).filter(NoteSection.note_id == note.id).delete()
        db.flush()

    for s in sections:
        target_concepts_list = json.loads(s.target_concepts or "[]")
        prompt = SECTION_GENERATION_PROMPT_TEMPLATE.format(
            topic=journey.topic,
            section_title=s.title,
            section_type=s.section_type,
            depth=s.depth,
            target_concepts=target_concepts_list,
            rationale=s.rationale,
            needs_code=s.needs_code,
            needs_visual=s.needs_visual,
            visual_type=s.visual_type or "None",
        )

        try:
            raw_output = await provider.generate(
                prompt=prompt,
                system_prompt=NOTE_GENERATION_SYSTEM_PROMPT,
                temperature=0.3,
            )
        except Exception as err:
            logger.error("LLM generation failed for section %s: %s", s.title, err)
            raw_output = ""

        blocks = parse_section_blocks(
            raw_text=raw_output,
            section_title=s.title,
            section_type=s.section_type,
            depth=s.depth,
            target_concepts=target_concepts_list,
            rationale=s.rationale,
            needs_code=s.needs_code,
            needs_visual=s.needs_visual,
            visual_type=s.visual_type,
        )

        # Persist NoteSection
        sec_record = NoteSection(
            note_id=note.id,
            order_index=s.order_index,
            title=s.title,
            section_type=s.section_type,
            depth=s.depth,
            blocks=json.dumps([b.model_dump() for b in blocks]),
        )
        db.add(sec_record)
        db.flush()

        generated_sections_data.append(
            NoteSectionData(
                id=sec_record.id,
                order_index=sec_record.order_index,
                title=sec_record.title,
                section_type=sec_record.section_type,
                depth=sec_record.depth,
                blocks=blocks,
            )
        )

    journey.status = "note_generated"
    db.commit()
    db.refresh(note)

    return NoteResponse(
        id=note.id,
        journey_id=journey.id,
        topic=journey.topic,
        version=note.version,
        summary=note.summary,
        sections=generated_sections_data,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )
