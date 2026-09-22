import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.config import Settings, get_settings
from backend.app.db.session import get_db
from backend.app.models.assessment import Assessment
from backend.app.schemas.assessment import (
    AssessmentResponse,
    FlashcardItem,
    QuizQuestion,
    QuizSubmissionRequest,
    QuizSubmissionResult,
)
from backend.app.assessment.generator import (
    generate_assessment_for_journey,
    evaluate_quiz_submission,
)

router = APIRouter()


@router.post(
    "/journeys/{journey_id}/assessment/generate",
    response_model=AssessmentResponse,
    status_code=status.HTTP_200_OK,
    tags=["Active Recall Assessment"],
)
async def generate_assessment(
    journey_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Generate personalized flashcards and scenario quiz for a learning journey.
    """
    return await generate_assessment_for_journey(
        journey_id=journey_id,
        db=db,
        settings=settings,
    )


@router.get(
    "/journeys/{journey_id}/assessment",
    response_model=AssessmentResponse,
    status_code=status.HTTP_200_OK,
    tags=["Active Recall Assessment"],
)
def get_assessment(
    journey_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve existing active recall flashcards and quiz questions for a journey.
    """
    assessment = db.query(Assessment).filter(Assessment.journey_id == journey_id).first()
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment for journey '{journey_id}' has not been generated yet.",
        )

    flashcards_raw = json.loads(assessment.flashcards or "[]")
    quiz_raw = json.loads(assessment.quiz_questions or "[]")

    return AssessmentResponse(
        id=assessment.id,
        journey_id=assessment.journey_id,
        note_id=assessment.note_id,
        flashcards=[FlashcardItem(**f) for f in flashcards_raw],
        quiz_questions=[QuizQuestion(**q) for q in quiz_raw],
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


@router.post(
    "/journeys/{journey_id}/assessment/submit",
    response_model=QuizSubmissionResult,
    status_code=status.HTTP_200_OK,
    tags=["Active Recall Assessment"],
)
def submit_quiz(
    journey_id: str,
    request: QuizSubmissionRequest,
    db: Session = Depends(get_db),
):
    """
    Submit answers to the technical quiz, calculate mastery score,
    and automatically promote mastered concepts in the KnowledgeProfile.
    """
    return evaluate_quiz_submission(
        journey_id=journey_id,
        request=request,
        db=db,
    )
