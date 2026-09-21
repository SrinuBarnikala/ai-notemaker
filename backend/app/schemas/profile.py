from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, ConfigDict


class ConceptItem(BaseModel):
    name: str
    level: Literal["strong", "moderate", "weak", "unknown"]
    category: Literal["known", "partially_known", "unknown"]
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class KnowledgeProfileResponse(BaseModel):
    id: str
    journey_id: str
    topic: str
    overall_confidence: Literal["beginner", "intermediate", "advanced", "mixed"]
    summary: str
    concepts: List[ConceptItem]
    misconceptions: List[str]
    gaps: List[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
