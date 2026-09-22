from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from backend.app.schemas.note import NoteBlock


class CodePlanItem(BaseModel):
    section_id: str
    section_title: str
    needs_code: bool
    language: str = "python"
    purpose: str = "Demonstrate core mechanics and algorithmic execution"
    code: str
    runnable: bool = True
    expected_output: Optional[str] = None
    complexity: Optional[str] = None  # e.g. "Time: O(N) | Space: O(1)"
    test_cases: Optional[List[Dict[str, Any]]] = None

    model_config = ConfigDict(from_attributes=True)


class CodePlanResponse(BaseModel):
    journey_id: str
    note_id: str
    code_items: List[CodePlanItem]
    total_code_blocks: int

    model_config = ConfigDict(from_attributes=True)


class GenerateSectionCodeRequest(BaseModel):
    language: Optional[str] = "python"
    purpose: Optional[str] = None
    include_tests: bool = True
    custom_prompt: Optional[str] = None


class SectionCodeResponse(BaseModel):
    journey_id: str
    section_id: str
    section_title: str
    code_block: NoteBlock

    model_config = ConfigDict(from_attributes=True)
