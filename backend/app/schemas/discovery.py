from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class DiscoveryAnswerRequest(BaseModel):
    answer: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="The learner's response or explanation for the question."
    )

    @field_validator("answer")
    @classmethod
    def validate_answer_not_blank(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Answer cannot be empty or purely whitespace.")
        return trimmed


class DiscoveryQuestionResponse(BaseModel):
    journey_id: str
    question_index: int
    question_text: str
    concept_target: str
    is_finished: bool
    quick_assessment: Optional[str] = None
    total_questions_answered: int = 0


class DiscoveryInteractionItem(BaseModel):
    id: str
    question_index: int
    question_text: str
    concept_target: str
    learner_answer: Optional[str] = None
    quick_assessment: Optional[str] = None
    created_at: datetime
    answered_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DiscoveryHistoryResponse(BaseModel):
    journey_id: str
    topic: str
    status: str
    interactions: List[DiscoveryInteractionItem]
    is_finished: bool
