from datetime import datetime, timezone
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.config import Settings, get_settings
from backend.app.db.session import get_db
from backend.app.models.journey import LearningJourney
from backend.app.models.discovery import DiscoveryInteraction
from backend.app.schemas.discovery import (
    DiscoveryAnswerRequest,
    DiscoveryQuestionResponse,
    DiscoveryHistoryResponse,
    DiscoveryInteractionItem,
)
from backend.app.providers.factory import get_llm_provider
from backend.app.discovery.workflow import run_initial_discovery, run_adaptive_discovery_step

logger = logging.getLogger(__name__)

router = APIRouter()


def get_utc_now():
    return datetime.now(timezone.utc)


@router.post(
    "/{journey_id}/discovery/start",
    response_model=DiscoveryQuestionResponse,
    status_code=status.HTTP_200_OK,
)
async def start_discovery(
    journey_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Initiate knowledge discovery for a learning journey. Generates Question #1.
    """
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning journey '{journey_id}' not found.",
        )

    # Check if there is already an unanswered question for this journey
    existing_unanswered = (
        db.query(DiscoveryInteraction)
        .filter(
            DiscoveryInteraction.journey_id == journey_id,
            DiscoveryInteraction.learner_answer == None,
        )
        .first()
    )
    if existing_unanswered:
        return DiscoveryQuestionResponse(
            journey_id=journey.id,
            question_index=existing_unanswered.question_index,
            question_text=existing_unanswered.question_text,
            concept_target=existing_unanswered.concept_target,
            is_finished=False,
            quick_assessment=None,
            total_questions_answered=existing_unanswered.question_index - 1,
        )

    # Check if discovery already concluded
    if journey.status == "discovery_completed":
        total = db.query(DiscoveryInteraction).filter(DiscoveryInteraction.journey_id == journey_id).count()
        return DiscoveryQuestionResponse(
            journey_id=journey.id,
            question_index=total,
            question_text="Discovery completed.",
            concept_target="Complete",
            is_finished=True,
            quick_assessment="Discovery already completed.",
            total_questions_answered=total,
        )

    # Run LangGraph discovery agent to generate initial question
    provider = get_llm_provider(settings)
    init_res = await run_initial_discovery(
        journey_id=journey.id,
        topic=journey.topic,
        provider=provider,
        max_questions=4,
    )

    interaction = DiscoveryInteraction(
        journey_id=journey.id,
        question_index=1,
        question_text=init_res["question_text"],
        concept_target=init_res["concept_target"],
    )
    db.add(interaction)
    journey.status = "discovery"
    db.commit()
    db.refresh(interaction)

    return DiscoveryQuestionResponse(
        journey_id=journey.id,
        question_index=1,
        question_text=interaction.question_text,
        concept_target=interaction.concept_target,
        is_finished=False,
        quick_assessment=None,
        total_questions_answered=0,
    )


@router.post(
    "/{journey_id}/discovery/answer",
    response_model=DiscoveryQuestionResponse,
    status_code=status.HTTP_200_OK,
)
async def submit_discovery_answer(
    journey_id: str,
    payload: DiscoveryAnswerRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Submit answer to the active discovery question, receive assessment and next adaptive question.
    """
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning journey '{journey_id}' not found.",
        )

    # Find the current unanswered question
    current_interaction = (
        db.query(DiscoveryInteraction)
        .filter(
            DiscoveryInteraction.journey_id == journey_id,
            DiscoveryInteraction.learner_answer == None,
        )
        .order_by(DiscoveryInteraction.question_index.desc())
        .first()
    )

    if not current_interaction:
        if journey.status == "discovery_completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Discovery for this journey has already concluded.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending question to answer. Start discovery first.",
        )

    # Save learner answer
    current_interaction.learner_answer = payload.answer
    current_interaction.answered_at = get_utc_now()

    # Load all interactions history up to now
    all_interactions = (
        db.query(DiscoveryInteraction)
        .filter(DiscoveryInteraction.journey_id == journey_id)
        .order_by(DiscoveryInteraction.question_index.asc())
        .all()
    )
    history_dicts = [
        {
            "question_index": item.question_index,
            "question_text": item.question_text,
            "concept_target": item.concept_target,
            "learner_answer": item.learner_answer,
            "quick_assessment": item.quick_assessment,
        }
        for item in all_interactions
    ]

    # Run LangGraph adaptive step
    provider = get_llm_provider(settings)
    step_res = await run_adaptive_discovery_step(
        journey_id=journey.id,
        topic=journey.topic,
        interactions=history_dicts,
        current_question_index=current_interaction.question_index,
        latest_question=current_interaction.question_text,
        latest_concept_target=current_interaction.concept_target,
        latest_answer=payload.answer,
        provider=provider,
        max_questions=4,
    )

    current_interaction.quick_assessment = step_res["quick_assessment"]

    if step_res["is_finished"] or not step_res.get("next_question"):
        journey.status = "discovery_completed"
        db.commit()
        return DiscoveryQuestionResponse(
            journey_id=journey.id,
            question_index=current_interaction.question_index,
            question_text="Discovery completed.",
            concept_target="Complete",
            is_finished=True,
            quick_assessment=step_res["quick_assessment"],
            total_questions_answered=current_interaction.question_index,
        )

    # Create next adaptive question
    next_index = current_interaction.question_index + 1
    next_interaction = DiscoveryInteraction(
        journey_id=journey.id,
        question_index=next_index,
        question_text=step_res["next_question"],
        concept_target=step_res["next_concept_target"] or "Technical Concept",
    )
    db.add(next_interaction)
    db.commit()
    db.refresh(next_interaction)

    return DiscoveryQuestionResponse(
        journey_id=journey.id,
        question_index=next_index,
        question_text=next_interaction.question_text,
        concept_target=next_interaction.concept_target,
        is_finished=False,
        quick_assessment=step_res["quick_assessment"],
        total_questions_answered=current_interaction.question_index,
    )


@router.get(
    "/{journey_id}/discovery",
    response_model=DiscoveryHistoryResponse,
)
def get_discovery_history(
    journey_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve full discovery questions, answers, and assessments for a journey.
    """
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning journey '{journey_id}' not found.",
        )

    interactions = (
        db.query(DiscoveryInteraction)
        .filter(DiscoveryInteraction.journey_id == journey_id)
        .order_by(DiscoveryInteraction.question_index.asc())
        .all()
    )

    items = [
        DiscoveryInteractionItem(
            id=i.id,
            question_index=i.question_index,
            question_text=i.question_text,
            concept_target=i.concept_target,
            learner_answer=i.learner_answer,
            quick_assessment=i.quick_assessment,
            created_at=i.created_at,
            answered_at=i.answered_at,
        )
        for i in interactions
    ]

    return DiscoveryHistoryResponse(
        journey_id=journey.id,
        topic=journey.topic,
        status=journey.status,
        interactions=items,
        is_finished=(journey.status == "discovery_completed"),
    )
