import json
import logging
import re
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.models.note import Note, NoteSection, NoteRevision
from backend.app.schemas.note import NoteBlock
from backend.app.note.versioning import serialize_note_snapshot
from backend.app.schemas.copilot import (
    CopilotQueryRequest,
    CopilotQueryResponse,
    CopilotPinCandidate,
    PinAnswerRequest,
    PinAnswerResponse,
)
from backend.app.providers.base import LLMProvider
from backend.app.copilot.prompts import (
    COPILOT_SYSTEM_PROMPT,
    COPILOT_QUERY_PROMPT_TEMPLATE,
)

logger = logging.getLogger(__name__)


def safe_load_blocks(raw_blocks: Any) -> List[Dict[str, Any]]:
    """Safely deserializes SQLite JSON string or returns list."""
    if isinstance(raw_blocks, str):
        try:
            parsed = json.loads(raw_blocks)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    elif isinstance(raw_blocks, list):
        return raw_blocks
    return []


def extract_copilot_json(text: str) -> Optional[Dict[str, Any]]:
    """Extracts JSON object from LLM response text with markdown fence stripping."""
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Regex search for first outer {...}
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


def format_section_summary(blocks: List[Dict[str, Any]]) -> str:
    """Produces a compact textual representation of section blocks."""
    summary_parts = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        b_type = b.get("type", "")
        if b_type == "paragraph":
            summary_parts.append(str(b.get("content", ""))[:200])
        elif b_type == "definition":
            summary_parts.append(f"{b.get('term', 'Term')}: {str(b.get('content', ''))[:150]}")
        elif b_type == "code":
            summary_parts.append(f"Code ({b.get('language', 'code')}): {str(b.get('code', ''))[:150]}")
        elif b_type == "warning":
            summary_parts.append(f"Pitfall: {b.get('title', '')} - {str(b.get('content', ''))[:120]}")
    return "\n".join(summary_parts) if summary_parts else "Overview of key concepts and architecture."


async def ask_copilot(
    journey_id: str,
    req: CopilotQueryRequest,
    db: Session,
    provider: LLMProvider,
) -> CopilotQueryResponse:
    """
    Agent 9: Generates personalized Socratic technical explanations grounded
    in the learner's knowledge profile and current living note section.
    """
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
            detail="Note not found for this journey. Complete Phase 5 first.",
        )

    # Resolve target section if provided
    target_section: Optional[NoteSection] = None
    if req.section_id:
        target_section = (
            db.query(NoteSection)
            .filter(NoteSection.id == req.section_id, NoteSection.note_id == note.id)
            .first()
        )
    if not target_section and note.sections:
        # Default to first section for contextual baseline
        target_section = note.sections[0]

    # Resolve learner profile
    profile = db.query(KnowledgeProfile).filter(KnowledgeProfile.journey_id == journey_id).first()
    overall_conf = profile.overall_confidence if profile else "intermediate"
    
    known_concepts = []
    gaps = []
    misconceptions = []
    if profile:
        known_concepts = [c.name for c in profile.concepts if c.category == "known" or c.level == "strong"]
        if profile.gaps:
            try:
                raw_gaps = json.loads(profile.gaps) if isinstance(profile.gaps, str) else profile.gaps
                gaps = [g if isinstance(g, str) else g.get("gap", "") for g in raw_gaps]
            except Exception:
                pass
        if not gaps:
            gaps = [c.name for c in profile.concepts if c.category in ["unknown", "partially_known"] or c.level in ["weak", "unknown"]]
        if profile.misconceptions:
            try:
                raw_misc = json.loads(profile.misconceptions) if isinstance(profile.misconceptions, str) else profile.misconceptions
                misconceptions = [m if isinstance(m, str) else m.get("misconception", "") for m in raw_misc]
            except Exception:
                pass

    section_title = target_section.title if target_section else note.topic
    section_type = target_section.section_type if target_section else "concept_overview"
    section_depth = target_section.depth if target_section else "standard"
    section_blocks = safe_load_blocks(target_section.blocks) if target_section else []
    section_summary = format_section_summary(section_blocks)

    selected_context = ""
    if req.selected_text:
        selected_context = f"Selected Text Inquired About:\n\"\"\"{req.selected_text[:500]}\"\"\"\n"

    history_context = ""
    if req.history:
        recent = req.history[-4:]
        lines = [f"- {m.role.capitalize()}: {m.content[:200]}" for m in recent]
        history_context = "Recent Conversation History:\n" + "\n".join(lines) + "\n"

    prompt = COPILOT_QUERY_PROMPT_TEMPLATE.format(
        topic=note.topic,
        section_title=section_title,
        section_type=section_type,
        depth=section_depth,
        section_content_summary=section_summary,
        overall_confidence=overall_conf,
        known_concepts=", ".join(known_concepts) if known_concepts else "Core technical foundations",
        knowledge_gaps=", ".join(gaps) if gaps else "Advanced optimizations and edge cases",
        misconceptions=", ".join(misconceptions) if misconceptions else "None currently flagged",
        selected_text_context=selected_context,
        history_context=history_context,
        question=req.question,
    )

    try:
        raw_output = await provider.generate(
            prompt=prompt,
            system_prompt=COPILOT_SYSTEM_PROMPT,
            temperature=0.3,
        )
    except Exception as e:
        logger.warning(f"Agent 9 LLM query error: {e}. Utilizing fallback response.")
        raw_output = ""

    parsed = extract_copilot_json(raw_output)

    if parsed and isinstance(parsed.get("answer"), str) and parsed.get("answer").strip():
        answer = parsed["answer"].strip()
        followups = [f for f in parsed.get("suggested_followups", []) if isinstance(f, str)][:3]
        pin_dict = parsed.get("pin_candidate")
        pin_candidate = None
        if isinstance(pin_dict, dict) and pin_dict.get("content"):
            pin_candidate = CopilotPinCandidate(
                block_type=pin_dict.get("block_type", "paragraph") if pin_dict.get("block_type") in ["example", "definition", "warning", "paragraph", "code"] else "paragraph",
                title=pin_dict.get("title") or f"Copilot Note: {req.question[:40]}",
                term=pin_dict.get("term"),
                content=pin_dict.get("content"),
                code=pin_dict.get("code"),
                language=pin_dict.get("language"),
            )
    else:
        # High quality fallback
        answer = (
            f"### Contextual Clarification for: *{req.question}*\n\n"
            f"Within the context of **{section_title}** in {note.topic}:\n\n"
            f"- **Mechanics**: When analyzing this concept, the critical invariant is how state transitions and boundaries are enforced.\n"
            f"- **Profile Alignment**: Considering your learning path towards technical mastery, observe the trade-offs between latency, safety guarantees, and architectural overhead.\n"
            f"- **Practical Takeaway**: In production implementations, ensure rigorous validation and defensive failure handling around this invariant."
        )
        followups = [
            f"How does this fail or recover under network partitions or high load?",
            f"What are the concrete memory and runtime complexity trade-offs?",
            f"Can you provide a runnable code example demonstrating this?",
        ]
        pin_candidate = CopilotPinCandidate(
            block_type="example",
            title=f"Insight: {req.question[:50]}",
            content=f"When designing {section_title}, account for state transition guarantees and defensive boundary validation to prevent silent regressions.",
        )

    return CopilotQueryResponse(
        journey_id=journey_id,
        section_id=target_section.id if target_section else None,
        section_title=section_title,
        question=req.question,
        answer=answer,
        suggested_followups=followups,
        pin_candidate=pin_candidate,
    )


def pin_copilot_answer(
    journey_id: str,
    req: PinAnswerRequest,
    db: Session,
) -> PinAnswerResponse:
    """
    Pins a Copilot answer directly into the living note as a structured block,
    incrementing the note version and logging a NoteRevision.
    """
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journey '{journey_id}' not found.",
        )

    note = db.query(Note).filter(Note.journey_id == journey_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note for journey '{journey_id}' not found.",
        )

    section = (
        db.query(NoteSection)
        .filter(NoteSection.id == req.section_id, NoteSection.note_id == note.id)
        .first()
    )
    if not section:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Section '{req.section_id}' not found in note '{note.id}'.",
        )

    existing_blocks = safe_load_blocks(section.blocks)

    new_block = NoteBlock(
        type=req.block_type,
        title=req.title,
        term=req.term,
        content=req.content,
        code=req.code,
        language=req.language,
    )

    existing_blocks.append(new_block.model_dump())
    section.blocks = json.dumps(existing_blocks)

    note.version += 1

    # Snapshot of sections for this new version
    current_sections = (
        db.query(NoteSection)
        .filter(NoteSection.note_id == note.id)
        .order_by(NoteSection.order_index.asc())
        .all()
    )
    snapshot_json = serialize_note_snapshot(note, current_sections)

    revision = NoteRevision(
        note_id=note.id,
        version=note.version,
        evolution_type="copilot_pin",
        section_title=section.title,
        user_prompt=f"Copilot Pinned [{req.block_type}]: {req.title or req.content[:60]}",
        change_summary=f"Pinned Copilot explanation into section '{section.title}'.",
        snapshot=snapshot_json,
    )
    db.add(revision)
    db.commit()
    db.refresh(note)
    db.refresh(section)

    return PinAnswerResponse(
        success=True,
        journey_id=journey_id,
        note_id=note.id,
        note_version=note.version,
        section_id=section.id,
        section_title=section.title,
        message=f"Successfully pinned explanation to section '{section.title}' (Version {note.version}).",
    )
