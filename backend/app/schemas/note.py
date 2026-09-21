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
    items: Optional[List[Dict[str, Any]]] = None  # for comparison tables

    model_config = ConfigDict(from_attributes=True)


class NoteSectionData(BaseModel):
    id: str
    order_index: int
    title: str
    section_type: str
    depth: str
    blocks: List[NoteBlock]

    model_config = ConfigDict(from_attributes=True)


class NoteResponse(BaseModel):
    id: str
    journey_id: str
    topic: str
    version: int
    summary: str
    sections: List[NoteSectionData]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GenerateNoteRequest(BaseModel):
    style_preference: Optional[str] = "rigorous_technical"
