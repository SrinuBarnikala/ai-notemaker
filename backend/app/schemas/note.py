from datetime import datetime
from typing import List, Optional, Dict, Any, Literal, Union
from pydantic import BaseModel, ConfigDict



class NoteBlock(BaseModel):
    type: Literal["paragraph", "definition", "example", "code", "warning", "comparison", "diagram"]
    content: Optional[str] = None
    term: Optional[str] = None  # for definition
    language: Optional[str] = None  # for code
    code: Optional[str] = None  # for code
    title: Optional[str] = None  # for warning / example / diagram
    caption: Optional[str] = None  # for diagram
    diagram_spec: Optional[str] = None  # for diagram
    diagram_type: Optional[str] = None  # e.g. flowchart, sequence, architecture, concept_map
    visual_description: Optional[str] = None  # semantic explanation of visual flow
    items: Optional[List[Dict[str, Any]]] = None  # for comparison tables
    runnable: Optional[bool] = False  # for code
    expected_output: Optional[str] = None  # for code
    complexity: Optional[str] = None  # for code (e.g. Time: O(N) | Space: O(1))
    test_cases: Optional[List[Dict[str, Any]]] = None  # for code

    model_config = ConfigDict(from_attributes=True)


class NoteSectionData(BaseModel):
    id: str
    order_index: int
    title: str
    section_type: str
    depth: str
    blocks: List[NoteBlock]
    generation_status: Optional[str] = "llm_success"
    generation_details: Optional[Union[str, Dict[str, Any]]] = None

    model_config = ConfigDict(from_attributes=True)




class NoteRevisionData(BaseModel):
    id: str
    version: int
    evolution_type: str
    section_title: Optional[str] = None
    user_prompt: str
    change_summary: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NoteVersionItem(BaseModel):
    version: int
    evolution_type: str
    section_title: Optional[str] = None
    user_prompt: str
    change_summary: Optional[str] = None
    created_at: datetime
    total_sections: int = 0
    is_current: bool = False

    model_config = ConfigDict(from_attributes=True)


class NoteVersionsListResponse(BaseModel):
    note_id: str
    journey_id: str
    topic: str
    current_version: int
    total_versions: int
    versions: List[NoteVersionItem]

    model_config = ConfigDict(from_attributes=True)


class BlockDiff(BaseModel):
    block_index: int
    type: str
    status: Literal["added", "removed", "modified", "unchanged"]
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class SectionDiff(BaseModel):
    section_id: str
    title: str
    status: Literal["added", "removed", "modified", "unchanged"]
    old_section_type: Optional[str] = None
    new_section_type: Optional[str] = None
    old_depth: Optional[str] = None
    new_depth: Optional[str] = None
    summary: Optional[str] = None
    block_diffs: List[BlockDiff] = []

    model_config = ConfigDict(from_attributes=True)


class NoteVersionDiffResponse(BaseModel):
    note_id: str
    journey_id: str
    topic: str
    from_version: int
    to_version: int
    summary: str
    stats: Dict[str, int]
    sections: List[SectionDiff]

    model_config = ConfigDict(from_attributes=True)


class RestoreVersionResponse(BaseModel):
    success: bool
    message: str
    restored_from_version: int
    new_version: int
    note: "NoteResponse"

    model_config = ConfigDict(from_attributes=True)


class NoteResponse(BaseModel):
    id: str
    journey_id: str
    topic: str
    version: int
    summary: str
    sections: List[NoteSectionData]
    revisions: List[NoteRevisionData] = []
    generation_status: Optional[str] = "llm_success"
    generation_details: Optional[Union[str, Dict[str, Any]]] = None
    created_at: datetime
    updated_at: datetime


    model_config = ConfigDict(from_attributes=True)



class GenerateNoteRequest(BaseModel):
    style_preference: Optional[str] = "rigorous_technical"


class EvolveNoteRequest(BaseModel):
    evolution_type: Literal[
        "expand_section",
        "add_code",
        "clarify",
        "custom_prompt",
        "add_section",
    ] = "custom_prompt"
    section_id: Optional[str] = None
    user_prompt: str

