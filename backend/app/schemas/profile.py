from datetime import datetime
from typing import Any, Dict, List, Optional, Literal
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
    # "unknown": not assessed. "developing": written by the quiz-scoring stage (assessment/generator.py).
    overall_confidence: Literal["beginner", "intermediate", "advanced", "mixed", "developing", "unknown"]
    summary: str
    concepts: List[ConceptItem]
    misconceptions: List[str]
    gaps: List[str]
    # Per-topic discovery results (intention, depth, preferences, evidence, unresolved); None for legacy profiles
    learner_context: Optional[Dict[str, Any]] = None
    # True when the model could not synthesize this profile and a non-inferential fallback was stored
    synthesis_fallback: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
