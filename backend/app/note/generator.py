import json
import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.config import Settings
from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.models.discovery import DiscoveryInteraction
from backend.app.models.architecture import NoteArchitecture, NoteArchitectureSection
from backend.app.models.note import Note, NoteSection, NoteRevision
from backend.app.schemas.note import NoteResponse, NoteSectionData, NoteBlock
from backend.app.providers.factory import get_llm_provider
from backend.app.note.prompts import (
    NOTE_GENERATION_SYSTEM_PROMPT,
    SECTION_GENERATION_PROMPT_TEMPLATE,
)
from backend.app.note.parser import parse_section_blocks
from backend.app.note.versioning import serialize_note_snapshot

logger = logging.getLogger(__name__)


async def generate_note_content(
    journey_id: str,
    db: Session,
    settings: Settings,
    style_preference: str = "rigorous_technical",
) -> NoteResponse:
    return await generate_structured_note(
        journey_id=journey_id,
        db=db,
        settings=settings,
        style_preference=style_preference,
    )


async def generate_structured_note(
    journey_id: str,
    db: Session,
    settings: Settings,
    style_preference: str = "rigorous_technical",
) -> NoteResponse:

    """
    Synthesizes the complete personalized Technical Note from the Note Architecture,
    propagating full learner context, discovery responses, and document roadmaps.
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

    # Load rich learner context
    profile = db.query(KnowledgeProfile).filter(KnowledgeProfile.journey_id == journey_id).first()
    profile_summary = profile.summary if profile else "No profile summary available."
    overall_confidence = profile.overall_confidence if profile else "intermediate"
    misconceptions_list = json.loads(profile.misconceptions or "[]") if profile else []
    gaps_list = json.loads(profile.gaps or "[]") if profile else []

    concepts = (
        db.query(KnowledgeConcept).filter(KnowledgeConcept.profile_id == profile.id).all()
        if profile else []
    )
    known_concepts = [c.name for c in concepts if c.level == "strong"]
    partial_concepts = [c.name for c in concepts if c.level == "moderate"]

    interactions = (
        db.query(DiscoveryInteraction)
        .filter(DiscoveryInteraction.journey_id == journey_id)
        .order_by(DiscoveryInteraction.question_index.asc())
        .all()
    )
    discovery_lines = []
    for item in interactions:
        if item.learner_answer:
            target = item.concept_target or "General"
            discovery_lines.append(f"- Concept: {target} | Learner stated: '{item.learner_answer}'")
            if item.quick_assessment:
                discovery_lines.append(f"  Assessment: {item.quick_assessment}")
    discovery_summary = "\n".join(discovery_lines) or "No discovery interactions recorded."

    provider = get_llm_provider(settings)
    generated_sections_data = []
    fallback_count = 0
    total_sections = len(sections)

    # Persist or update Note container
    note = db.query(Note).filter(Note.journey_id == journey_id).first()
    if not note:
        note = Note(
            journey_id=journey.id,
            topic=journey.topic,
            version=1,
            summary=arch.summary_rationale,
            generation_status="llm_success",
        )
        db.add(note)
        db.flush()
    else:
        note.summary = arch.summary_rationale
        note.version += 1
        db.query(NoteSection).filter(NoteSection.note_id == note.id).delete()
        db.flush()

    for idx, s in enumerate(sections):
        target_concepts_list = json.loads(s.target_concepts or "[]")
        prev_s = sections[idx - 1] if idx > 0 else None
        next_s = sections[idx + 1] if idx < total_sections - 1 else None

        prev_context = (
            f"Section {prev_s.order_index}: '{prev_s.title}' ({prev_s.section_type})"
            if prev_s else "None (Opening Section)"
        )
        next_context = (
            f"Section {next_s.order_index}: '{next_s.title}' ({next_s.section_type})"
            if next_s else "None (Final Section)"
        )

        prompt = SECTION_GENERATION_PROMPT_TEMPLATE.format(
            topic=journey.topic,
            learning_goal=arch.learning_goal,
            overall_confidence=overall_confidence,
            profile_summary=profile_summary,
            known_concepts=", ".join(known_concepts) or "None explicitly confirmed",
            gaps=", ".join(gaps_list) or "None explicitly flagged",
            misconceptions=", ".join(misconceptions_list) or "None detected",
            discovery_summary=discovery_summary,
            total_sections=total_sections,
            section_order=s.order_index,
            section_title=s.title,
            section_type=s.section_type,
            depth=s.depth,
            target_concepts=target_concepts_list,
            rationale=s.rationale,
            prev_section_context=prev_context,
            next_section_context=next_context,
            needs_code=s.needs_code,
            needs_visual=s.needs_visual,
            visual_type=s.visual_type or "None",
        )

        failure_reason = None
        try:
            raw_output = await provider.generate(
                prompt=prompt,
                system_prompt=NOTE_GENERATION_SYSTEM_PROMPT,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
        except Exception as err:
            logger.error("LLM generation failed for section %s: %s", s.title, err)
            raw_output = ""
            failure_reason = f"Provider call error: {err}"

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
            topic=journey.topic,
        )

        used_fallback = getattr(blocks, "used_fallback", False)
        if used_fallback:
            fallback_count += 1
            sec_status = "llm_fallback"
            sec_details = {
                "provider": provider.provider_name,
                "model": provider.model_name,
                "fallback_used": True,
                "reason": getattr(blocks, "failure_reason", None) or failure_reason,
            }
        else:
            sec_status = "llm_success"
            sec_details = {
                "provider": provider.provider_name,
                "model": provider.model_name,
                "fallback_used": False,
            }

        # Persist NoteSection
        sec_record = NoteSection(
            note_id=note.id,
            order_index=s.order_index,
            title=s.title,
            section_type=s.section_type,
            depth=s.depth,
            blocks=json.dumps([b.model_dump() for b in blocks]),
            generation_status=sec_status,
            generation_details=json.dumps(sec_details),
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
                generation_status=sec_status,
                generation_details=sec_details,
            )
        )

    # Note overall status
    if fallback_count == 0:
        note.generation_status = "llm_success"
    elif fallback_count == total_sections:
        note.generation_status = "llm_fallback"
    else:
        note.generation_status = "llm_partial_fallback"

    note.generation_details = json.dumps({
        "provider": provider.provider_name,
        "model": provider.model_name,
        "fallback_sections_count": fallback_count,
        "total_sections": total_sections,
    })

    # Save Version 1 snapshot and revision record
    sec_records = (
        db.query(NoteSection)
        .filter(NoteSection.note_id == note.id)
        .order_by(NoteSection.order_index.asc())
        .all()
    )
    v1_snapshot = serialize_note_snapshot(note, sec_records)
    v1_revision = NoteRevision(
        note_id=note.id,
        version=note.version,
        evolution_type="initial_generation" if note.version == 1 else "regeneration",
        section_title=None,
        user_prompt="Initial living note generation based on personalized architecture.",
        change_summary=f"Initial living note created with {len(sec_records)} structured sections ({note.generation_status}).",

        snapshot=v1_snapshot,
    )
    db.add(v1_revision)

    journey.status = "note_generated"
    db.commit()
    db.refresh(note)

    revisions_data = []

    return NoteResponse(
        id=note.id,
        journey_id=journey.id,
        topic=journey.topic,
        version=note.version,
        summary=note.summary,
        sections=generated_sections_data,
        revisions=revisions_data,
        generation_status=note.generation_status,
        generation_details=note.generation_details,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )
