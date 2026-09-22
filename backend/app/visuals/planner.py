import json
import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.models.note import Note, NoteSection
from backend.app.schemas.note import NoteBlock
from backend.app.schemas.visuals import (
    VisualPlanItem,
    VisualPlanResponse,
    GenerateSectionVisualRequest,
    SectionVisualResponse,
)
from backend.app.providers.base import LLMProvider
from backend.app.visuals.prompts import (
    VISUAL_PLANNER_SYSTEM_PROMPT,
    NOTE_VISUAL_PLAN_PROMPT_TEMPLATE,
    SECTION_VISUAL_PROMPT_TEMPLATE,
)
from backend.app.visuals.sanitizer import (
    extract_json,
    sanitize_mermaid_spec,
    generate_fallback_mermaid,
)

logger = logging.getLogger(__name__)


def summarize_section_blocks(blocks: List[dict]) -> str:
    """Creates a compact text summary of section blocks for prompting."""
    parts = []
    for b in blocks:
        b_type = b.get("type", "")
        if b_type == "paragraph":
            parts.append(b.get("content", "")[:180])
        elif b_type == "definition":
            parts.append(f"{b.get('term', '')}: {b.get('content', '')[:120]}")
        elif b_type == "warning":
            parts.append(f"Warning: {b.get('title', '')} - {b.get('content', '')[:100]}")
        elif b_type == "code":
            parts.append(f"Code ({b.get('language', 'py')}): {b.get('title', '')}")
    return "\n".join(parts) if parts else "Core concept walkthrough and mechanics."


async def plan_visuals_for_note(
    note: Note,
    db: Session,
    provider: LLMProvider,
) -> VisualPlanResponse:
    """
    Scans all sections of a living note, plans architectural Mermaid diagrams,
    and directly injects/updates diagram blocks into sections.
    """
    sections = note.sections
    if not sections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Note has no sections to plan visuals for.",
        )

    sections_overview = []
    for sec in sections:
        try:
            sec_blocks = json.loads(sec.blocks) if isinstance(sec.blocks, str) else sec.blocks
        except Exception:
            sec_blocks = []
        has_diagram = any(b.get("type") == "diagram" for b in sec_blocks)
        sections_overview.append({
            "section_id": sec.id,
            "title": sec.title,
            "section_type": sec.section_type,
            "depth": sec.depth,
            "has_existing_diagram": has_diagram,
            "summary": summarize_section_blocks(sec_blocks)[:200],
        })

    prompt = NOTE_VISUAL_PLAN_PROMPT_TEMPLATE.format(
        topic=note.topic,
        note_summary=note.summary,
        sections_overview_json=json.dumps(sections_overview, indent=2),
    )

    try:
        raw_output = await provider.generate(
            prompt=prompt,
            system_prompt=VISUAL_PLANNER_SYSTEM_PROMPT,
            temperature=0.3,
        )
    except Exception as e:
        logger.warning(f"Visual planner provider call failed: {e}. Using deterministic planning.")
        raw_output = ""

    parsed_plan = extract_json(raw_output)
    plan_items: List[VisualPlanItem] = []

    # Map sections by ID
    sec_map = {s.id: s for s in sections}

    if isinstance(parsed_plan, list) and len(parsed_plan) > 0:
        for item in parsed_plan:
            sec_id = item.get("section_id")
            if sec_id in sec_map:
                sec = sec_map[sec_id]
                v_type = item.get("visual_type", "flowchart")
                title = item.get("title", f"{sec.title} Architecture")
                raw_spec = item.get("diagram_spec", "")
                sanitized_spec = sanitize_mermaid_spec(raw_spec, title)
                plan_items.append(
                    VisualPlanItem(
                        section_id=sec.id,
                        section_title=sec.title,
                        needs_visual=True,
                        visual_type=v_type,
                        title=title,
                        diagram_spec=sanitized_spec,
                        caption=item.get("caption", f"Architectural workflow for {sec.title}."),
                        rationale=item.get("rationale", "Illustrates internal system mechanisms."),
                    )
                )

    # Heuristic fallback if LLM returned nothing or invalid list
    if not plan_items:
        for idx, sec in enumerate(sections):
            # Prioritize deep dive, mental model, or every 2nd section
            if sec.section_type in ("deep_dive", "mental_model", "bridge", "code_walkthrough") or idx == 0:
                v_type = "architecture" if idx == 0 else ("sequence" if "request" in sec.title.lower() or "flow" in sec.title.lower() else "flowchart")
                title = f"{sec.title} Architecture"
                fallback_spec = generate_fallback_mermaid(v_type, sec.title)
                plan_items.append(
                    VisualPlanItem(
                        section_id=sec.id,
                        section_title=sec.title,
                        needs_visual=True,
                        visual_type=v_type,
                        title=title,
                        diagram_spec=fallback_spec,
                        caption=f"Architectural flow and component interactions for {sec.title}.",
                        rationale=f"Clarifies system boundaries and data path for {sec.title}.",
                    )
                )

    # Inject or update diagram blocks into note sections
    for item in plan_items:
        sec = sec_map.get(item.section_id)
        if not sec:
            continue

        try:
            current_blocks = json.loads(sec.blocks) if isinstance(sec.blocks, str) else list(sec.blocks)
        except Exception:
            current_blocks = []

        new_block = {
            "type": "diagram",
            "title": item.title,
            "caption": item.caption,
            "diagram_spec": item.diagram_spec,
            "diagram_type": item.visual_type,
            "visual_description": item.rationale,
            "content": item.caption,
        }

        # Check if diagram block already exists in section
        updated = False
        for b_idx, b in enumerate(current_blocks):
            if b.get("type") == "diagram":
                current_blocks[b_idx] = new_block
                updated = True
                break

        if not updated:
            # Place diagram after first paragraph/definition if possible, else append
            insert_pos = len(current_blocks)
            for b_idx, b in enumerate(current_blocks):
                if b.get("type") in ("paragraph", "definition"):
                    insert_pos = b_idx + 1
                    break
            current_blocks.insert(insert_pos, new_block)

        sec.blocks = json.dumps(current_blocks)

    db.commit()

    return VisualPlanResponse(
        journey_id=note.journey_id,
        note_id=note.id,
        visuals=plan_items,
        total_diagrams=len(plan_items),
    )


async def generate_visual_for_section(
    journey_id: str,
    section_id: str,
    request: GenerateSectionVisualRequest,
    db: Session,
    provider: LLMProvider,
) -> SectionVisualResponse:
    """
    Generates or regenerates a high-quality Mermaid visual diagram for an individual section.
    """
    sec = (
        db.query(NoteSection)
        .join(Note)
        .filter(Note.journey_id == journey_id, NoteSection.id == section_id)
        .first()
    )
    if not sec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Section '{section_id}' not found for journey '{journey_id}'.",
        )

    note = sec.note
    try:
        current_blocks = json.loads(sec.blocks) if isinstance(sec.blocks, str) else list(sec.blocks)
    except Exception:
        current_blocks = []

    content_summary = summarize_section_blocks(current_blocks)
    v_type = request.visual_type or "flowchart"
    custom_prompt = request.custom_prompt or "Generate an end-to-end technical visual diagram."

    prompt = SECTION_VISUAL_PROMPT_TEMPLATE.format(
        topic=note.topic,
        section_title=sec.title,
        section_type=sec.section_type,
        depth=sec.depth,
        section_content_summary=content_summary,
        visual_type=v_type,
        custom_prompt=custom_prompt,
    )

    try:
        raw_output = await provider.generate(
            prompt=prompt,
            system_prompt=VISUAL_PLANNER_SYSTEM_PROMPT,
            temperature=0.3,
        )
    except Exception as e:
        logger.warning(f"Section visual generation provider call failed: {e}. Using deterministic fallback.")
        raw_output = ""

    parsed = extract_json(raw_output)
    diagram_title = request.title or (parsed.get("title") if isinstance(parsed, dict) else None) or f"{sec.title} Architecture"
    caption = (parsed.get("caption") if isinstance(parsed, dict) else None) or f"Interactive architecture and flow diagram for {sec.title}."
    visual_desc = (parsed.get("visual_description") if isinstance(parsed, dict) else None) or custom_prompt

    raw_spec = (parsed.get("diagram_spec") if isinstance(parsed, dict) else "") or ""
    if raw_spec:
        final_spec = sanitize_mermaid_spec(raw_spec, diagram_title)
    else:
        final_spec = generate_fallback_mermaid(v_type, diagram_title)

    diagram_block = NoteBlock(
        type="diagram",
        title=diagram_title,
        caption=caption,
        diagram_spec=final_spec,
        diagram_type=v_type,
        visual_description=visual_desc,
        content=caption,
    )

    # Inject into section blocks
    updated = False
    new_block_dict = diagram_block.model_dump()
    for b_idx, b in enumerate(current_blocks):
        if b.get("type") == "diagram":
            current_blocks[b_idx] = new_block_dict
            updated = True
            break

    if not updated:
        insert_pos = len(current_blocks)
        for b_idx, b in enumerate(current_blocks):
            if b.get("type") in ("paragraph", "definition"):
                insert_pos = b_idx + 1
                break
        current_blocks.insert(insert_pos, new_block_dict)

    sec.blocks = json.dumps(current_blocks)
    db.commit()

    return SectionVisualResponse(
        journey_id=journey_id,
        section_id=sec.id,
        section_title=sec.title,
        diagram_block=diagram_block,
    )
