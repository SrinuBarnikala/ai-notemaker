from datetime import datetime
from typing import List, Optional, Literal, Dict, Any, Union
from pydantic import BaseModel, ConfigDict



class SectionBlueprint(BaseModel):
    order_index: int
    title: str
    section_type: str  # e.g. mental_model, deep_dive, bridge, code_walkthrough, pitfall_warning
    depth: Literal["brief", "standard", "deep"]
    target_concepts: List[str]
    rationale: str
    needs_code: bool = False
    needs_visual: bool = False
    visual_type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class GenerateArchitectureRequest(BaseModel):
    learning_goal: Optional[str] = "Master internal mechanics and practical architecture"


class NoteArchitectureResponse(BaseModel):
    id: str
    journey_id: str
    topic: str
    learning_goal: str
    summary_rationale: str
    sections: List[SectionBlueprint]
    generation_status: Optional[str] = "llm_success"
    generation_details: Optional[Union[str, Dict[str, Any]]] = None
    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

