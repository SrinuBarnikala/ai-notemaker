from datetime import datetime
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, ConfigDict


class FlashcardItem(BaseModel):
    id: str
    concept: str
    front: str
    back: str
    difficulty: Literal["easy", "medium", "hard"] = "medium"

    model_config = ConfigDict(from_attributes=True)


class QuizQuestion(BaseModel):
    id: str
    concept: str
    question: str
    options: List[str]
    correct_index: int
    explanation: str

    model_config = ConfigDict(from_attributes=True)


class AssessmentResponse(BaseModel):
    id: str
    journey_id: str
    note_id: str
    flashcards: List[FlashcardItem]
    quiz_questions: List[QuizQuestion]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QuizSubmissionRequest(BaseModel):
    answers: Dict[str, int]  # question_id -> chosen option index


class QuestionResult(BaseModel):
    question_id: str
    concept: str
    selected_index: int
    correct_index: int
    is_correct: bool
    explanation: str


class QuizSubmissionResult(BaseModel):
    submission_id: str
    score: int
    total: int
    percentage: float
    breakdown: List[QuestionResult]
    mastered_concepts: List[str]
    updated_confidence: str
    message: str
