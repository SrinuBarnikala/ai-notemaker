from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict

DEFAULT_MAX_QUESTIONS = 10


class DiscoveryAnswerRequest(BaseModel):
    # Optional guard: when sent, the answer is only accepted for this group (question_index)
    question_index: Optional[int] = Field(None, ge=1)
    answer: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="The learner's single combined free-text reply to the whole question group.",
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
    question_index: int  # the position of this group in the conversation
    # The group: a short statement of why the questions are being asked, and zero to five peer questions.
    # Both are empty/None for the completion message. Legacy groups have no motive.
    motive: Optional[str] = None
    questions: List[str] = Field(default_factory=list)
    # Readable flattened text of the group, for clients that only know a single text field
    question_text: str
    concept_target: str
    # Dimension ids the motive serves (for example "learning_approach")
    targets: List[str] = Field(default_factory=list)
    is_finished: bool
    quick_assessment: Optional[str] = None
    # Individual questions: each costs one unit of the budget, motives are free
    total_questions_answered: int = 0
    questions_asked: int = 0
    questions_remaining: int = DEFAULT_MAX_QUESTIONS
    # Safety limit on individual questions, not a target; the conversation usually ends sooner
    max_questions: int = DEFAULT_MAX_QUESTIONS
    # True when this group is generic because the model could not supply a valid one
    fallback_used: bool = False
    # True for a group written before motives existed (shown without one)
    legacy: bool = False


class DiscoveryInteractionItem(BaseModel):
    id: str
    question_index: int
    motive: Optional[str] = None
    questions: List[str] = Field(default_factory=list)
    question_text: str
    concept_target: str
    targets: List[str] = Field(default_factory=list)
    legacy: bool = False
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
    questions_asked: int = 0
    max_questions: int = DEFAULT_MAX_QUESTIONS
