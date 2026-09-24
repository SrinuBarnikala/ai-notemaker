import json
import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.config import Settings
from backend.app.models.note import Note, NoteSection, NoteRevision
from backend.app.schemas.note import (
    NoteResponse,
    NoteSectionData,
    NoteBlock,
    EvolveNoteRequest,
    NoteRevisionData,
)
from backend.app.providers.factory import get_llm_provider
from backend.app.note.parser import parse_section_blocks, extract_json_array_or_object
from backend.app.note.versioning import serialize_note_snapshot

logger = logging.getLogger(__name__)

NOTE_EVOLUTION_SYSTEM_PROMPT = """You are the Note Evolution Agent for a personalized living technical note system.
Your role is to update, expand, or refine sections of an existing structured technical note based on learner feedback, questions, or requests for deeper depth and practical code.

Directives:
1. Output structured content blocks as a strict JSON array.
2. Supported Block Types:
   - "paragraph": Rigorous technical explanations.
   - "definition": Technical terminology with "term" and "content".
   - "code": Executable, realistic technical code with "language" (e.g. "python", "sql", "bash") and "code".
   - "warning": Pitfalls, misconceptions, or anti-patterns with "title" and "content".
   - "comparison": Analytical breakdown comparing trade-offs, technologies, or concepts.
   - "diagram": Architectural or flowchart ASCII visual with "title", "caption", and "diagram_spec".
   - "example": Concrete production walkthrough with "title" and "content".
3. Maintain continuity with the existing section content while directly addressing the learner's request.
4. Output ONLY valid JSON matching the schema.
"""

SECTION_EVOLUTION_PROMPT_TEMPLATE = """Topic: "{topic}"
Section Title: "{section_title}"
Section Type: "{section_type}"
Current Depth: "{depth}"

Existing Section Blocks:
{existing_blocks_json}

Learner's Evolution Request:
"{user_prompt}"

Evolution Goal ({evolution_type}):
- If "add_code": Ensure at least one concrete, production-grade code block is added or enhanced.
- If "expand_section": Provide deeper technical nuances and detailed breakdown.
- If "clarify": Address ambiguity, misconceptions, or explain step-by-step.
- If "custom_prompt": Fully address the learner's specific question or request.

Generate the updated or augmented structured blocks for this section.
Return ONLY a JSON array of blocks.
"""

ADD_SECTION_PROMPT_TEMPLATE = """Topic: "{topic}"
Existing Sections in Note:
{existing_sections_summary}

Learner's Request to Add New Section / Topic:
"{user_prompt}"

Generate a new structured section addressing this request.
Return a JSON array of structured blocks (paragraph, code, definition, warning, diagram, example).
"""


async def evolve_structured_note(
    note_id: str,
    request: EvolveNoteRequest,
    db: Session,
    settings: Settings,
) -> Note:
    """
    Evolves an existing living note by updating a section or appending a new section,
    incrementing the note version, and logging a revision entry.
    """
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found.",
        )

    provider = get_llm_provider(settings)
    target_section_title = None

    # Case 1: Targeted Section Evolution
    if request.section_id:
        section = (
            db.query(NoteSection)
            .filter(
                NoteSection.id == request.section_id,
                NoteSection.note_id == note.id,
            )
            .first()
        )
        if not section:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Section '{request.section_id}' not found in note '{note_id}'.",
            )

        target_section_title = section.title
        existing_blocks = json.loads(section.blocks or "[]")

        prompt = SECTION_EVOLUTION_PROMPT_TEMPLATE.format(
            topic=note.topic,
            section_title=section.title,
            section_type=section.section_type,
            depth=section.depth,
            existing_blocks_json=json.dumps(existing_blocks, indent=2),
            user_prompt=request.user_prompt,
            evolution_type=request.evolution_type,
        )

        try:
            raw_output = await provider.generate(
                prompt=prompt,
                system_prompt=NOTE_EVOLUTION_SYSTEM_PROMPT,
                temperature=0.3,
            )
        except Exception as err:
            logger.error("LLM evolution generation failed: %s", err)
            raw_output = ""

        # Parse new blocks
        new_blocks = parse_section_blocks(
            raw_text=raw_output,
            section_title=section.title,
            section_type=section.section_type,
            depth="deep" if request.evolution_type == "expand_section" else section.depth,
            target_concepts=[],
            rationale=request.user_prompt,
            needs_code=request.evolution_type == "add_code",
            needs_visual=False,
        )

        if not new_blocks:
            # Fallback: append an evolution explanation paragraph
            new_blocks = [NoteBlock(**b) for b in existing_blocks] + [
                NoteBlock(
                    type="paragraph",
                    content=f"**Note Evolution Update:** {request.user_prompt}",
                )
            ]

        # Update section blocks in DB
        section.blocks = json.dumps([b.model_dump() for b in new_blocks])
        if request.evolution_type == "expand_section":
            section.depth = "deep"

    # Case 2: Append New Section
    elif request.evolution_type == "add_section":
        existing_sections = (
            db.query(NoteSection)
            .filter(NoteSection.note_id == note.id)
            .order_by(NoteSection.order_index.asc())
            .all()
        )
        existing_summary = "\n".join(
            [f"- {s.order_index}. {s.title} ({s.section_type})" for s in existing_sections]
        )
        new_order = len(existing_sections) + 1
        new_title = (
            request.user_prompt[:60].strip().rstrip(".")
            if len(request.user_prompt) > 5
            else f"Advanced Expansion {new_order}"
        )
        target_section_title = new_title

        prompt = ADD_SECTION_PROMPT_TEMPLATE.format(
            topic=note.topic,
            existing_sections_summary=existing_summary,
            user_prompt=request.user_prompt,
        )

        try:
            raw_output = await provider.generate(
                prompt=prompt,
                system_prompt=NOTE_EVOLUTION_SYSTEM_PROMPT,
                temperature=0.3,
            )
        except Exception as err:
            logger.error("LLM new section evolution generation failed: %s", err)
            raw_output = ""

        new_blocks = parse_section_blocks(
            raw_text=raw_output,
            section_title=new_title,
            section_type="deep_dive",
            depth="standard",
            target_concepts=[],
            rationale=request.user_prompt,
            needs_code=True,
            needs_visual=False,
        )

        new_section = NoteSection(
            note_id=note.id,
            order_index=new_order,
            title=new_title,
            section_type="deep_dive",
            depth="standard",
            blocks=json.dumps([b.model_dump() for b in new_blocks]),
        )
        db.add(new_section)

    # Case 3: Global note evolution without specific section specified -> apply to last section
    else:
        last_section = (
            db.query(NoteSection)
            .filter(NoteSection.note_id == note.id)
            .order_by(NoteSection.order_index.desc())
            .first()
        )
        if last_section:
            target_section_title = last_section.title
            existing_blocks = json.loads(last_section.blocks or "[]")
            prompt = SECTION_EVOLUTION_PROMPT_TEMPLATE.format(
                topic=note.topic,
                section_title=last_section.title,
                section_type=last_section.section_type,
                depth=last_section.depth,
                existing_blocks_json=json.dumps(existing_blocks, indent=2),
                user_prompt=request.user_prompt,
                evolution_type=request.evolution_type,
            )
            try:
                raw_output = await provider.generate(
                    prompt=prompt,
                    system_prompt=NOTE_EVOLUTION_SYSTEM_PROMPT,
                    temperature=0.3,
                )
            except Exception as err:
                logger.error("LLM global evolution generation failed: %s", err)
                raw_output = ""

            new_blocks = parse_section_blocks(
                raw_text=raw_output,
                section_title=last_section.title,
                section_type=last_section.section_type,
                depth=last_section.depth,
                target_concepts=[],
                rationale=request.user_prompt,
                needs_code=request.evolution_type == "add_code",
                needs_visual=False,
            )
            last_section.blocks = json.dumps([b.model_dump() for b in new_blocks])

    # Increment version
    note.version += 1

    # Serialize snapshot of current sections for the new version
    current_sections = (
        db.query(NoteSection)
        .filter(NoteSection.note_id == note.id)
        .order_by(NoteSection.order_index.asc())
        .all()
    )
    snapshot_json = serialize_note_snapshot(note, current_sections)

    if request.evolution_type == "add_section":
        change_summary = f"Added new section: '{target_section_title}'."
    elif request.evolution_type == "add_code":
        change_summary = f"Enhanced section '{target_section_title}' with practical code blocks."
    elif request.evolution_type == "expand_section":
        change_summary = f"Expanded section '{target_section_title}' with in-depth technical detail."
    elif request.evolution_type == "clarify":
        change_summary = f"Clarified conceptual nuances in '{target_section_title}'."
    else:
        change_summary = f"Evolved note: {request.user_prompt[:80]}"

    # Log revision entry
    revision = NoteRevision(
        note_id=note.id,
        version=note.version,
        evolution_type=request.evolution_type,
        section_title=target_section_title,
        user_prompt=request.user_prompt,
        change_summary=change_summary,
        snapshot=snapshot_json,
    )
    db.add(revision)

    db.commit()
    db.refresh(note)
    return note


def export_note_to_markdown(note_data: NoteResponse) -> str:
    """
    Exports a structured NoteResponse into clean, standard GitHub-Flavored Markdown.
    """
    lines: List[str] = []

    # Frontmatter
    lines.append("---")
    lines.append(f'title: "{note_data.topic}"')
    lines.append(f"version: {note_data.version}")
    lines.append(f'created_at: "{note_data.created_at.isoformat()}"')
    lines.append(f'updated_at: "{note_data.updated_at.isoformat()}"')
    lines.append('generator: "Personalized Technical Note Maker"')
    lines.append("---")
    lines.append("")

    # Main Heading & Summary
    lines.append(f"# {note_data.topic}")
    lines.append("")
    lines.append(f"> **Personalized Summary:** {note_data.summary}")
    lines.append("")

    # Revision info if evolved
    if note_data.revisions:
        lines.append(f"*Living Note Version {note_data.version} ({len(note_data.revisions)} evolution updates applied)*")
        lines.append("")

    # Table of Contents
    lines.append("## Table of Contents")
    lines.append("")
    for s in note_data.sections:
        anchor = s.title.lower().replace(" ", "-").replace("/", "").replace(":", "")
        lines.append(f"{s.order_index}. [{s.title}](#{anchor})")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Sections
    for s in note_data.sections:
        lines.append(f"## {s.order_index}. {s.title}")
        lines.append(f"*{s.depth.title()} Depth &bull; {s.section_type.replace('_', ' ').title()}*")
        lines.append("")

        for b in s.blocks:
            if b.type == "paragraph":
                lines.append(b.content or "")
                lines.append("")
            elif b.type == "definition":
                term = b.term or "Definition"
                content = b.content or ""
                lines.append(f"> 📖 **{term}**")
                lines.append(f"> {content}")
                lines.append("")
            elif b.type == "warning":
                title = b.title or "Warning / Pitfall"
                content = b.content or ""
                lines.append("> [!WARNING]")
                lines.append(f"> **{title}**")
                lines.append(f"> {content}")
                lines.append("")
            elif b.type == "example":
                title = b.title or "Example"
                content = b.content or ""
                lines.append(f"> 💡 **Example: {title}**")
                lines.append(f"> {content}")
                lines.append("")
            elif b.type == "code":
                lang = b.language or "text"
                code_text = b.code or b.content or ""
                if b.title:
                    lines.append(f"**Listing: {b.title}**")
                lines.append(f"```{lang}")
                lines.append(code_text.rstrip())
                lines.append("```")
                lines.append("")
            elif b.type == "diagram":
                title = b.title or "Architecture Diagram"
                spec = b.diagram_spec or b.content or ""
                lines.append(f"**Diagram: {title}**")
                lines.append("```text")
                lines.append(spec.rstrip())
                lines.append("```")
                if b.caption:
                    lines.append(f"*Figure: {b.caption}*")
                lines.append("")
            elif b.type == "comparison":
                if b.title:
                    lines.append(f"### {b.title}")
                if b.content:
                    lines.append(b.content)
                    lines.append("")
                if b.items and len(b.items) > 0:
                    keys = list(b.items[0].keys())
                    header_line = "| " + " | ".join(keys) + " |"
                    sep_line = "| " + " | ".join(["---"] * len(keys)) + " |"
                    lines.append(header_line)
                    lines.append(sep_line)
                    for row in b.items:
                        row_line = "| " + " | ".join([str(row.get(k, "")) for k in keys]) + " |"
                        lines.append(row_line)
                    lines.append("")
            else:
                lines.append(b.content or "")
                lines.append("")

        lines.append("---")
        lines.append("")

    # Footer note
    lines.append("*Living note created and maintained by the Personalized Technical Note Maker system.*")
    return "\n".join(lines)
