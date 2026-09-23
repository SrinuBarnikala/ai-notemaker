from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict


class CopilotMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: Optional[str] = None


class CopilotPinCandidate(BaseModel):
    block_type: Literal["example", "definition", "warning", "paragraph", "code"] = "paragraph"
    title: Optional[str] = None
    term: Optional[str] = None
    content: str
    code: Optional[str] = None
    language: Optional[str] = None


class CopilotQueryRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=1500)
    section_id: Optional[str] = None
    selected_text: Optional[str] = None
    history: List[CopilotMessage] = Field(default_factory=list)


class CopilotQueryResponse(BaseModel):
    journey_id: str
    section_id: Optional[str] = None
    section_title: Optional[str] = None
    question: str
    answer: str
    suggested_followups: List[str] = Field(default_factory=list)
    pin_candidate: Optional[CopilotPinCandidate] = None

    model_config = ConfigDict(from_attributes=True)


class PinAnswerRequest(BaseModel):
    section_id: str
    block_type: Literal["example", "definition", "warning", "paragraph", "code"] = "paragraph"
    title: Optional[str] = None
    term: Optional[str] = None
    content: str = Field(..., min_length=2)
    code: Optional[str] = None
    language: Optional[str] = None


class PinAnswerResponse(BaseModel):
    success: bool
    journey_id: str
    note_id: str
    note_version: int
    section_id: str
    section_title: str
    message: str

    model_config = ConfigDict(from_attributes=True)
