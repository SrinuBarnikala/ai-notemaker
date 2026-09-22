from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from backend.app.schemas.note import NoteBlock


class VisualPlanItem(BaseModel):
    section_id: str
    section_title: str
    needs_visual: bool = True
    visual_type: Optional[str] = "flowchart"  # e.g. flowchart, sequence, architecture, concept_map
    title: Optional[str] = None
    diagram_spec: Optional[str] = None
    caption: Optional[str] = None
    rationale: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class VisualPlanResponse(BaseModel):
    journey_id: str
    note_id: str
    visuals: List[VisualPlanItem]
    total_diagrams: int

    model_config = ConfigDict(from_attributes=True)


class GenerateSectionVisualRequest(BaseModel):
    visual_type: Optional[str] = "flowchart"  # flowchart, sequence, architecture, concept_map, state_machine
    custom_prompt: Optional[str] = None
    title: Optional[str] = None


class SectionVisualResponse(BaseModel):
    journey_id: str
    section_id: str
    section_title: str
    diagram_block: NoteBlock

    model_config = ConfigDict(from_attributes=True)
