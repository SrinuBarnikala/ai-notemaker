import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.models.note import Note, NoteSection, NoteRevision
from backend.app.schemas.note import (
    NoteResponse,
    NoteSectionData,
    NoteBlock,
    NoteRevisionData,
    NoteVersionItem,
    NoteVersionsListResponse,
    BlockDiff,
    SectionDiff,
    NoteVersionDiffResponse,
    RestoreVersionResponse,
)

logger = logging.getLogger(__name__)


def serialize_note_snapshot(note: Note, sections: List[NoteSection]) -> str:
    """
    Serializes a note and its sections into a JSON string snapshot for version persistence.
    """
    sections_payload = []
    for s in sections:
        blocks_data = []
        if isinstance(s.blocks, str):
            try:
                blocks_data = json.loads(s.blocks or "[]")
            except Exception:
                blocks_data = []
        elif isinstance(s.blocks, list):
            blocks_data = s.blocks

        sections_payload.append(
            {
                "id": str(s.id),
                "order_index": s.order_index,
                "title": s.title,
                "section_type": s.section_type,
                "depth": s.depth,
                "blocks": blocks_data,
            }
        )

    snapshot_data = {
        "version": note.version,
        "topic": note.topic,
        "summary": note.summary,
        "sections": sections_payload,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }
    return json.dumps(snapshot_data)


def parse_snapshot_data(snapshot_str: Optional[str]) -> Optional[Dict[str, Any]]:
    if not snapshot_str:
        return None
    try:
        return json.loads(snapshot_str)
    except Exception as err:
        logger.error("Failed to parse snapshot JSON: %s", err)
        return None


def get_snapshot_for_version(note: Note, target_version: int, db: Session) -> Dict[str, Any]:
    """
    Retrieves the parsed snapshot dictionary for a given version.
    If the target version is the current version and no snapshot is recorded,
    or if snapshot is missing, dynamically generates it from current sections.
    """
    revision = (
        db.query(NoteRevision)
        .filter(
            NoteRevision.note_id == note.id,
            NoteRevision.version == target_version,
        )
        .first()
    )

    if revision and revision.snapshot:
        data = parse_snapshot_data(revision.snapshot)
        if data:
            return data

    # If it's the current version, reconstruct from current DB sections
    if note.version == target_version:
        sections = (
            db.query(NoteSection)
            .filter(NoteSection.note_id == note.id)
            .order_by(NoteSection.order_index.asc())
            .all()
        )
        serialized = serialize_note_snapshot(note, sections)
        return json.loads(serialized)

    # If older revision without snapshot, reconstruct best-effort
    if revision:
        return {
            "version": target_version,
            "topic": note.topic,
            "summary": note.summary,
            "sections": [
                {
                    "id": f"fallback_sec_{target_version}",
                    "order_index": 1,
                    "title": revision.section_title or "Historical Section",
                    "section_type": "concept",
                    "depth": "standard",
                    "blocks": [
                        {
                            "type": "paragraph",
                            "content": f"Historical Version {target_version} ({revision.evolution_type}): {revision.user_prompt}",
                        }
                    ],
                }
            ],
        }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Version {target_version} not found for note '{note.id}'.",
    )


def list_note_versions(note_id: str, db: Session) -> NoteVersionsListResponse:
    """
    Lists all available versions for a living note with metadata and change summaries.
    """
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found.",
        )

    revisions = (
        db.query(NoteRevision)
        .filter(NoteRevision.note_id == note.id)
        .order_by(NoteRevision.version.asc())
        .all()
    )

    current_sections_count = (
        db.query(NoteSection).filter(NoteSection.note_id == note.id).count()
    )

    version_items: List[NoteVersionItem] = []

    # Map existing revisions
    rev_by_version = {r.version: r for r in revisions}

    # Ensure all version numbers from 1 to note.version are present
    max_ver = max(note.version, max(rev_by_version.keys(), default=1))
    for v in range(1, max_ver + 1):
        rev = rev_by_version.get(v)
        is_cur = (v == note.version)

        total_secs = current_sections_count if is_cur else 0
        if rev and rev.snapshot:
            snap = parse_snapshot_data(rev.snapshot)
            if snap and "sections" in snap:
                total_secs = len(snap["sections"])

        if rev:
            change_sum = rev.change_summary
            if not change_sum:
                if rev.evolution_type == "initial_generation":
                    change_sum = "Initial living note generated from personalized learning architecture."
                elif rev.evolution_type == "add_section":
                    change_sum = f"Added new chapter section: '{rev.section_title or 'Expanded Section'}."
                elif rev.evolution_type == "add_code":
                    change_sum = f"Enhanced section '{rev.section_title or 'Section'}' with executable code blocks."
                elif rev.evolution_type == "expand_section":
                    change_sum = f"Deepened technical depth and detailed breakdown of '{rev.section_title or 'Section'}'."
                elif rev.evolution_type == "copilot_pin":
                    change_sum = f"Pinned Socratic Copilot technical explanation into '{rev.section_title or 'Living Note'}'."
                elif rev.evolution_type == "restore_version":
                    change_sum = f"Restored note state to historical Version {rev.user_prompt}."
                else:
                    change_sum = f"Evolved note ({rev.evolution_type}): {rev.user_prompt[:80]}"

            version_items.append(
                NoteVersionItem(
                    version=v,
                    evolution_type=rev.evolution_type,
                    section_title=rev.section_title,
                    user_prompt=rev.user_prompt,
                    change_summary=change_sum,
                    created_at=rev.created_at,
                    total_sections=total_secs,
                    is_current=is_cur,
                )
            )
        else:
            version_items.append(
                NoteVersionItem(
                    version=v,
                    evolution_type="initial_generation" if v == 1 else "evolution",
                    section_title=None,
                    user_prompt="Living note version checkpoint.",
                    change_summary="Initial living note creation." if v == 1 else "Living note evolution checkpoint.",
                    created_at=note.created_at,
                    total_sections=total_secs,
                    is_current=is_cur,
                )
            )

    return NoteVersionsListResponse(
        note_id=note.id,
        journey_id=note.journey_id,
        topic=note.topic,
        current_version=note.version,
        total_versions=len(version_items),
        versions=version_items,
    )


def get_note_version_response(note_id: str, version: int, db: Session) -> NoteResponse:
    """
    Returns the NoteResponse corresponding to an exact historical version.
    """
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found.",
        )

    snapshot = get_snapshot_for_version(note, version, db)

    sections_data: List[NoteSectionData] = []
    for s in snapshot.get("sections", []):
        blocks_data = [NoteBlock(**b) for b in s.get("blocks", [])]
        sections_data.append(
            NoteSectionData(
                id=str(s.get("id", f"sec_{version}_{s.get('order_index', 0)}")),
                order_index=int(s.get("order_index", 0)),
                title=str(s.get("title", "Untitled Section")),
                section_type=str(s.get("section_type", "concept")),
                depth=str(s.get("depth", "standard")),
                blocks=blocks_data,
            )
        )

    revisions_records = (
        db.query(NoteRevision)
        .filter(
            NoteRevision.note_id == note.id,
            NoteRevision.version <= version,
        )
        .order_by(NoteRevision.version.asc())
        .all()
    )

    revisions_data = [
        NoteRevisionData(
            id=r.id,
            version=r.version,
            evolution_type=r.evolution_type,
            section_title=r.section_title,
            user_prompt=r.user_prompt,
            change_summary=r.change_summary,
            created_at=r.created_at,
        )
        for r in revisions_records
    ]

    return NoteResponse(
        id=note.id,
        journey_id=note.journey_id,
        topic=str(snapshot.get("topic", note.topic)),
        version=version,
        summary=str(snapshot.get("summary", note.summary)),
        sections=sections_data,
        revisions=revisions_data,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _block_content_string(b: Dict[str, Any]) -> str:
    """Helper to extract comparable string representation of a block."""
    b_type = b.get("type", "paragraph")
    if b_type == "code":
        return f"[{b.get('language', '')}] {b.get('code', '')}"
    elif b_type == "definition":
        return f"{b.get('term', '')}: {b.get('content', '')}"
    elif b_type in ["warning", "example"]:
        return f"{b.get('title', '')} | {b.get('content', '')}"
    elif b_type == "diagram":
        return f"{b.get('title', '')} | {b.get('diagram_spec', '')}"
    return b.get("content", "") or ""


def compute_note_diff(
    note_id: str,
    from_version: int,
    to_version: int,
    db: Session,
) -> NoteVersionDiffResponse:
    """
    Computes a structured, granular semantic diff between two versions of a note.
    """
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found.",
        )

    snap_from = get_snapshot_for_version(note, from_version, db)
    snap_to = get_snapshot_for_version(note, to_version, db)

    sections_from: List[Dict[str, Any]] = snap_from.get("sections", [])
    sections_to: List[Dict[str, Any]] = snap_to.get("sections", [])

    # Index by title and id
    from_by_title = {s.get("title", "").strip().lower(): s for s in sections_from}
    to_by_title = {s.get("title", "").strip().lower(): s for s in sections_to}

    diff_sections: List[SectionDiff] = []
    stats = {
        "sections_added": 0,
        "sections_removed": 0,
        "sections_modified": 0,
        "sections_unchanged": 0,
        "blocks_added": 0,
        "blocks_removed": 0,
        "blocks_modified": 0,
        "blocks_unchanged": 0,
    }

    seen_to_titles = set()

    for s_from in sections_from:
        title_key = s_from.get("title", "").strip().lower()
        if title_key in to_by_title:
            seen_to_titles.add(title_key)
            s_to = to_by_title[title_key]

            # Compare blocks
            blocks_from = s_from.get("blocks", [])
            blocks_to = s_to.get("blocks", [])

            block_diffs: List[BlockDiff] = []
            is_sec_modified = False

            max_len = max(len(blocks_from), len(blocks_to))
            for idx in range(max_len):
                if idx >= len(blocks_from):
                    # Added block
                    b_new = blocks_to[idx]
                    block_diffs.append(
                        BlockDiff(
                            block_index=idx,
                            type=b_new.get("type", "paragraph"),
                            status="added",
                            old_content=None,
                            new_content=_block_content_string(b_new),
                            details=b_new,
                        )
                    )
                    stats["blocks_added"] += 1
                    is_sec_modified = True
                elif idx >= len(blocks_to):
                    # Removed block
                    b_old = blocks_from[idx]
                    block_diffs.append(
                        BlockDiff(
                            block_index=idx,
                            type=b_old.get("type", "paragraph"),
                            status="removed",
                            old_content=_block_content_string(b_old),
                            new_content=None,
                            details=b_old,
                        )
                    )
                    stats["blocks_removed"] += 1
                    is_sec_modified = True
                else:
                    b_old = blocks_from[idx]
                    b_new = blocks_to[idx]
                    old_str = _block_content_string(b_old)
                    new_str = _block_content_string(b_new)

                    if old_str == new_str and b_old.get("type") == b_new.get("type"):
                        block_diffs.append(
                            BlockDiff(
                                block_index=idx,
                                type=b_new.get("type", "paragraph"),
                                status="unchanged",
                                old_content=old_str,
                                new_content=new_str,
                                details=b_new,
                            )
                        )
                        stats["blocks_unchanged"] += 1
                    else:
                        block_diffs.append(
                            BlockDiff(
                                block_index=idx,
                                type=b_new.get("type", "paragraph"),
                                status="modified",
                                old_content=old_str,
                                new_content=new_str,
                                details=b_new,
                            )
                        )
                        stats["blocks_modified"] += 1
                        is_sec_modified = True

            sec_status = "modified" if is_sec_modified else "unchanged"
            if is_sec_modified:
                stats["sections_modified"] += 1
            else:
                stats["sections_unchanged"] += 1

            diff_sections.append(
                SectionDiff(
                    section_id=str(s_to.get("id", s_from.get("id", ""))),
                    title=s_to.get("title", s_from.get("title", "")),
                    status=sec_status,
                    old_section_type=s_from.get("section_type"),
                    new_section_type=s_to.get("section_type"),
                    old_depth=s_from.get("depth"),
                    new_depth=s_to.get("depth"),
                    summary=f"Section '{s_to.get('title')}' was {sec_status}.",
                    block_diffs=block_diffs,
                )
            )
        else:
            # Section removed
            blocks_from = s_from.get("blocks", [])
            b_diffs = [
                BlockDiff(
                    block_index=i,
                    type=b.get("type", "paragraph"),
                    status="removed",
                    old_content=_block_content_string(b),
                    new_content=None,
                    details=b,
                )
                for i, b in enumerate(blocks_from)
            ]
            stats["sections_removed"] += 1
            stats["blocks_removed"] += len(blocks_from)
            diff_sections.append(
                SectionDiff(
                    section_id=str(s_from.get("id", "")),
                    title=s_from.get("title", "Untitled Section"),
                    status="removed",
                    old_section_type=s_from.get("section_type"),
                    new_section_type=None,
                    old_depth=s_from.get("depth"),
                    new_depth=None,
                    summary=f"Section '{s_from.get('title')}' was removed.",
                    block_diffs=b_diffs,
                )
            )

    # Added sections in to_version
    for s_to in sections_to:
        title_key = s_to.get("title", "").strip().lower()
        if title_key not in seen_to_titles:
            blocks_to = s_to.get("blocks", [])
            b_diffs = [
                BlockDiff(
                    block_index=i,
                    type=b.get("type", "paragraph"),
                    status="added",
                    old_content=None,
                    new_content=_block_content_string(b),
                    details=b,
                )
                for i, b in enumerate(blocks_to)
            ]
            stats["sections_added"] += 1
            stats["blocks_added"] += len(blocks_to)
            diff_sections.append(
                SectionDiff(
                    section_id=str(s_to.get("id", "")),
                    title=s_to.get("title", "Untitled Section"),
                    status="added",
                    old_section_type=None,
                    new_section_type=s_to.get("section_type"),
                    old_depth=None,
                    new_depth=s_to.get("depth"),
                    summary=f"Section '{s_to.get('title')}' was newly added.",
                    block_diffs=b_diffs,
                )
            )

    # Human-readable summary
    summary_parts = []
    if stats["sections_added"] > 0:
        summary_parts.append(f"+{stats['sections_added']} section(s) added")
    if stats["sections_modified"] > 0:
        summary_parts.append(f"{stats['sections_modified']} section(s) modified")
    if stats["sections_removed"] > 0:
        summary_parts.append(f"-{stats['sections_removed']} section(s) removed")
    if stats["blocks_added"] > 0:
        summary_parts.append(f"+{stats['blocks_added']} block(s) added")
    if stats["blocks_modified"] > 0:
        summary_parts.append(f"{stats['blocks_modified']} block(s) updated")

    if not summary_parts:
        summary_str = f"No differences detected between Version {from_version} and Version {to_version}."
    else:
        summary_str = f"Changes from Version {from_version} to {to_version}: " + ", ".join(summary_parts) + "."

    return NoteVersionDiffResponse(
        note_id=note.id,
        journey_id=note.journey_id,
        topic=note.topic,
        from_version=from_version,
        to_version=to_version,
        summary=summary_str,
        stats=stats,
        sections=diff_sections,
    )


def restore_note_version(
    note_id: str,
    target_version: int,
    db: Session,
) -> RestoreVersionResponse:
    """
    Restores the living note to match a historical version snapshot,
    incrementing the version number (e.g. v4 restored from v2) to preserve non-destructive audit history.
    """
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found.",
        )

    snapshot = get_snapshot_for_version(note, target_version, db)
    snapshot_sections = snapshot.get("sections", [])

    if not snapshot_sections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Version {target_version} does not contain valid section data to restore.",
        )

    # Delete existing sections
    db.query(NoteSection).filter(NoteSection.note_id == note.id).delete()

    # Re-insert sections from snapshot
    new_sections: List[NoteSection] = []
    for s in snapshot_sections:
        blocks_data = s.get("blocks", [])
        sec = NoteSection(
            note_id=note.id,
            order_index=int(s.get("order_index", 1)),
            title=str(s.get("title", "Untitled Section")),
            section_type=str(s.get("section_type", "concept")),
            depth=str(s.get("depth", "standard")),
            blocks=json.dumps(blocks_data),
        )
        db.add(sec)
        new_sections.append(sec)

    # Increment version
    new_ver = note.version + 1
    note.version = new_ver
    note.summary = snapshot.get("summary", note.summary)

    # Save new revision entry
    revision = NoteRevision(
        note_id=note.id,
        version=new_ver,
        evolution_type="restore_version",
        section_title=None,
        user_prompt=f"Restored from Version {target_version}",
        change_summary=f"Restored note content back to Version {target_version} snapshot ({len(snapshot_sections)} sections).",
        snapshot=serialize_note_snapshot(note, new_sections),
    )
    db.add(revision)

    db.commit()
    db.refresh(note)

    # Build response
    note_resp = get_note_version_response(note.id, new_ver, db)

    return RestoreVersionResponse(
        success=True,
        message=f"Living note successfully restored from Version {target_version} as new Version {new_ver}.",
        restored_from_version=target_version,
        new_version=new_ver,
        note=note_resp,
    )
