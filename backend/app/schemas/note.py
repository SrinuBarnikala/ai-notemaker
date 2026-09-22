from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
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

    model_config = ConfigDict(from_attributes=True)


class NoteRevisionData(BaseModel):
    id: str
    version: int
    evolution_type: str
    section_title: Optional[str] = None
    user_prompt: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NoteResponse(BaseModel):
    id: str
    journey_id: str
    topic: str
    version: int
    summary: str
    sections: List[NoteSectionData]
    revisions: List[NoteRevisionData] = []
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

