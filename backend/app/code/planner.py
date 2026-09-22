import json
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.models.note import Note, NoteSection
from backend.app.schemas.note import NoteBlock
from backend.app.schemas.code import (
    CodePlanItem,
    CodePlanResponse,
    GenerateSectionCodeRequest,
    SectionCodeResponse,
)
from backend.app.providers.base import LLMProvider
from backend.app.code.prompts import (
    CODE_PLANNER_SYSTEM_PROMPT,
    NOTE_CODE_PLAN_PROMPT_TEMPLATE,
    SECTION_CODE_PROMPT_TEMPLATE,
)
from backend.app.code.sanitizer import (
    extract_json,
    sanitize_code_block,
    generate_fallback_code,
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


def summarize_section_blocks(blocks: List[dict]) -> str:
    """Creates a concise textual overview of section content for LLM prompts."""
    parts = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        b_type = b.get("type", "")
        if b_type == "paragraph":
            parts.append(str(b.get("content", ""))[:180])
        elif b_type == "definition":
            parts.append(f"{b.get('term', '')}: {str(b.get('content', ''))[:120]}")
        elif b_type == "warning":
            parts.append(f"Warning: {b.get('title', '')} - {str(b.get('content', ''))[:100]}")
        elif b_type == "code":
            parts.append(f"Existing Code ({b.get('language', 'py')}): {b.get('title', '')}")
    return "\n".join(parts) if parts else "Core concept walkthrough and mechanics."


async def plan_code_for_note(
    note: Note,
    db: Session,
    provider: LLMProvider,
) -> CodePlanResponse:
    """
    Scans all sections of a living note, plans executable code blocks with Agent 8,
    and updates section blocks in the database.
    """
    sections = note.sections
    if not sections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Note has no sections to plan code implementations for.",
        )

    sections_overview = []
    for s in sections:
        blocks_data = safe_load_blocks(s.blocks)
        sections_overview.append(
            {
                "section_id": s.id,
                "section_title": s.title,
                "section_type": s.section_type,
                "depth": s.depth,
                "summary": summarize_section_blocks(blocks_data),
            }
        )

    user_prompt = NOTE_CODE_PLAN_PROMPT_TEMPLATE.format(
        topic=note.topic,
        note_summary=note.summary or note.topic,
        sections_overview_json=json.dumps(sections_overview, indent=2),
    )

    planned_items: List[CodePlanItem] = []

    try:
        raw_response = await provider.generate(
            prompt=user_prompt,
            system_prompt=CODE_PLANNER_SYSTEM_PROMPT,
            temperature=0.3,
        )
        parsed = extract_json(raw_response)

        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                sec_id = item.get("section_id")
                sec_title = item.get("section_title", "Implementation")
                needs_code = item.get("needs_code", True)
                raw_code = item.get("code", "")
                language = (item.get("language") or "python").lower()

                if needs_code and raw_code:
                    cleaned_code = sanitize_code_block(raw_code, language)
                    planned_items.append(
                        CodePlanItem(
                            section_id=sec_id,
                            section_title=sec_title,
                            needs_code=True,
                            language=language,
                            purpose=item.get("purpose", f"Demonstrate mechanics of {sec_title}"),
                            code=cleaned_code,
                            runnable=item.get("runnable", language == "python"),
                            expected_output=item.get("expected_output"),
                            complexity=item.get("complexity", "Time: O(N) | Space: O(1)"),
                            test_cases=item.get("test_cases"),
                        )
                    )
    except Exception as e:
        logger.warning(f"Agent 8 Note Code Planner error: {e}. Generating deterministic fallbacks.")

    # If LLM didn't return any items, provide high-quality fallback implementations
    if not planned_items:
        for s in sections[:3]:  # Enrich first 2-3 sections
            fb = generate_fallback_code(note.topic, s.title, "python")
            planned_items.append(
                CodePlanItem(
                    section_id=s.id,
                    section_title=s.title,
                    needs_code=True,
                    language=fb["language"],
                    purpose=f"Runnable reference implementation for {s.title}",
                    code=fb["code"],
                    runnable=fb["runnable"],
                    expected_output=fb["expected_output"],
                    complexity=fb["complexity"],
                    test_cases=fb["test_cases"],
                )
            )

    # Apply planned code blocks directly into living note sections in DB
    section_map = {s.id: s for s in sections}
    for item in planned_items:
        target_section = section_map.get(item.section_id)
        if not target_section:
            continue

        existing_blocks = safe_load_blocks(target_section.blocks)

        code_block_dict = {
            "type": "code",
            "language": item.language,
            "code": item.code,
            "title": item.purpose or f"{item.section_title} Implementation",
            "runnable": item.runnable,
            "expected_output": item.expected_output,
            "complexity": item.complexity,
            "test_cases": item.test_cases,
        }

        # Check if an existing code block can be upgraded
        replaced = False
        for idx, b in enumerate(existing_blocks):
            if isinstance(b, dict) and b.get("type") == "code":
                existing_blocks[idx] = code_block_dict
                replaced = True
                break

        if not replaced:
            existing_blocks.append(code_block_dict)

        target_section.blocks = json.dumps(existing_blocks)

    db.commit()
    db.refresh(note)

    return CodePlanResponse(
        journey_id=note.journey_id,
        note_id=note.id,
        code_items=planned_items,
        total_code_blocks=len(planned_items),
    )


async def generate_code_for_section(
    journey_id: str,
    section_id: str,
    request: GenerateSectionCodeRequest,
    db: Session,
    provider: LLMProvider,
) -> SectionCodeResponse:
    """
    Synthesizes or updates an executable code block for a specific note section.
    """
    section = (
        db.query(NoteSection)
        .join(Note, Note.id == NoteSection.note_id)
        .filter(Note.journey_id == journey_id, NoteSection.id == section_id)
        .first()
    )

    if not section:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Section {section_id} not found in journey {journey_id}.",
        )

    note = section.note
    existing_blocks = safe_load_blocks(section.blocks)
    content_summary = summarize_section_blocks(existing_blocks)
    language = (request.language or "python").lower()

    user_prompt = SECTION_CODE_PROMPT_TEMPLATE.format(
        topic=note.topic,
        section_title=section.title,
        section_type=section.section_type,
        depth=section.depth,
        section_content_summary=content_summary,
        language=language,
        custom_prompt=request.custom_prompt or request.purpose or f"Provide an executable {language} implementation",
    )

    code_data: Optional[Dict[str, Any]] = None

    try:
        raw_response = await provider.generate(
            prompt=user_prompt,
            system_prompt=CODE_PLANNER_SYSTEM_PROMPT,
            temperature=0.3,
        )
        parsed = extract_json(raw_response)
        if isinstance(parsed, dict) and parsed.get("code"):
            raw_code = parsed.get("code", "")
            code_data = {
                "title": parsed.get("title") or f"{section.title} ({language.upper()})",
                "language": (parsed.get("language") or language).lower(),
                "code": sanitize_code_block(raw_code, language),
                "complexity": parsed.get("complexity") or "Time: O(N) | Space: O(1)",
                "expected_output": parsed.get("expected_output"),
                "runnable": parsed.get("runnable", language == "python"),
                "test_cases": parsed.get("test_cases"),
            }
    except Exception as e:
        logger.warning(f"Error calling LLM for section code: {e}. Using deterministic fallback.")

    if not code_data:
        fb = generate_fallback_code(
            note.topic,
            section.title,
            language,
            request.custom_prompt,
        )
        code_data = {
            "title": fb["title"],
            "language": fb["language"],
            "code": fb["code"],
            "complexity": fb["complexity"],
            "expected_output": fb["expected_output"],
            "runnable": fb["runnable"],
            "test_cases": fb["test_cases"],
        }

    # Build new block
    new_block = NoteBlock(
        type="code",
        language=code_data["language"],
        code=code_data["code"],
        title=code_data["title"],
        runnable=code_data["runnable"],
        expected_output=code_data.get("expected_output"),
        complexity=code_data.get("complexity"),
        test_cases=code_data.get("test_cases"),
    )

    # Replace existing code block or append
    block_dict = new_block.model_dump()
    replaced = False
    for idx, b in enumerate(existing_blocks):
        if isinstance(b, dict) and b.get("type") == "code":
            existing_blocks[idx] = block_dict
            replaced = True
            break

    if not replaced:
        existing_blocks.append(block_dict)

    section.blocks = json.dumps(existing_blocks)
    db.commit()
    db.refresh(section)

    return SectionCodeResponse(
        journey_id=journey_id,
        section_id=section_id,
        section_title=section.title,
        code_block=new_block,
    )
