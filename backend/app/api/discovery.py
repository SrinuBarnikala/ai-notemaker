import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
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
from backend.app.discovery.locks import discovery_locks
from backend.app.discovery.state import DISCOVERY_CONCLUDED_STATUSES, load_analysis, load_state
from backend.app.discovery.workflow import (
    DiscoveryProviderError,
    DiscoveryTimeoutError,
    run_initial_discovery,
    run_adaptive_discovery_step,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Journey statuses in which finishing discovery may move the journey to "discovery_completed".
# Any later status (profile, architecture, note) is never moved backwards.
DISCOVERY_ACTIVE_STATUSES = ("created", "discovery")

PROVIDER_UNAVAILABLE_DETAIL = (
    "The AI service could not be reached. Your answer was saved. Please try again in a moment."
)
PROVIDER_TIMEOUT_DETAIL = (
    "The AI service took too long to respond. Your answer was saved. Please try again in a moment."
)


def get_utc_now():
    return datetime.now(timezone.utc)


def _load_analysis(interaction: DiscoveryInteraction) -> Dict[str, Any]:
    return load_analysis(interaction.analysis)


def _all_interactions(db: Session, journey_id: str) -> List[DiscoveryInteraction]:
    return (
        db.query(DiscoveryInteraction)
        .filter(DiscoveryInteraction.journey_id == journey_id)
        .order_by(DiscoveryInteraction.question_index.asc())
        .all()
    )


def _interaction_at(db: Session, journey_id: str, index: int) -> Optional[DiscoveryInteraction]:
    return (
        db.query(DiscoveryInteraction)
        .filter(DiscoveryInteraction.journey_id == journey_id, DiscoveryInteraction.question_index == index)
        .first()
    )


def _answered_count(interactions: List[DiscoveryInteraction]) -> int:
    return sum(1 for i in interactions if i.learner_answer)


def _get_journey_or_404(db: Session, journey_id: str) -> LearningJourney:
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning journey '{journey_id}' not found.",
        )
    return journey


def _question_response(
    journey: LearningJourney,
    interaction: DiscoveryInteraction,
    answered: int,
    settings: Settings,
    quick_assessment: Optional[str] = None,
) -> DiscoveryQuestionResponse:
    return DiscoveryQuestionResponse(
        journey_id=journey.id,
        question_index=interaction.question_index,
        question_text=interaction.question_text,
        concept_target=interaction.concept_target,
        is_finished=False,
        quick_assessment=quick_assessment,
        total_questions_answered=answered,
        max_questions=settings.discovery_max_questions,
        fallback_used=bool(_load_analysis(interaction).get("question_fallback")),
    )


def _finished_response(
    journey: LearningJourney,
    last_index: int,
    answered: int,
    settings: Settings,
    quick_assessment: Optional[str],
) -> DiscoveryQuestionResponse:
    return DiscoveryQuestionResponse(
        journey_id=journey.id,
        question_index=last_index,
        question_text="Discovery completed.",
        concept_target="Complete",
        is_finished=True,
        quick_assessment=quick_assessment,
        total_questions_answered=answered,
        max_questions=settings.discovery_max_questions,
    )


def _provider_error(err: DiscoveryProviderError) -> HTTPException:
    detail = PROVIDER_TIMEOUT_DETAIL if isinstance(err, DiscoveryTimeoutError) else PROVIDER_UNAVAILABLE_DETAIL
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


async def _with_deadline(coro, settings: Settings):
    """Bounds one discovery request, however many nested model calls and retries it makes."""
    limit = settings.discovery_request_timeout_seconds
    try:
        return await asyncio.wait_for(coro, timeout=limit)
    except asyncio.TimeoutError:
        raise DiscoveryTimeoutError(f"Discovery request exceeded its {limit:g}s deadline")


def _insert_interaction(db: Session, interaction: DiscoveryInteraction) -> DiscoveryInteraction:
    """
    Insert (and commit) a new interaction. If another writer already created that question number
    (caught by the unique index), return the existing row instead of failing.
    """
    db.add(interaction)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _interaction_at(db, interaction.journey_id, interaction.question_index)
        if existing is None:
            raise
        logger.warning(
            "Question %s of journey %s already exists; using the existing row",
            interaction.question_index, interaction.journey_id,
        )
        return existing
    db.refresh(interaction)
    return interaction


async def _advance(
    db: Session,
    journey: LearningJourney,
    current: DiscoveryInteraction,
    settings: Settings,
) -> DiscoveryQuestionResponse:
    """
    Process an already-saved answer: update the learner state and either create the next
    question or complete discovery. Must be called while holding the journey's discovery lock.
    Safe to call again if a previous attempt failed.
    """
    interactions = _all_interactions(db, journey.id)
    history = [
        {
            "question_index": i.question_index,
            "question_text": i.question_text,
            "concept_target": i.concept_target,
            "learner_answer": i.learner_answer,
            "quick_assessment": i.quick_assessment,
        }
        for i in interactions
    ]
    previous_state = None
    for item in interactions:
        if item.question_index < current.question_index and item.learner_answer:
            previous_state = load_state(item.analysis) or previous_state

    provider = get_llm_provider(settings)
    try:
        step = await _with_deadline(
            run_adaptive_discovery_step(
                journey_id=journey.id,
                topic=journey.topic,
                interactions=history,
                previous_state=previous_state,
                provider=provider,
                max_questions=settings.discovery_max_questions,
            ),
            settings,
        )
    except DiscoveryProviderError as err:
        db.rollback()
        logger.error("Discovery provider failure for journey %s: %s", journey.id, err)
        raise _provider_error(err)

    analysis = _load_analysis(current)
    analysis.update({
        "state": step["state"].model_dump(),
        "assessment": step["quick_assessment"],
        "ready_to_finish": step["is_finished"],
        "finish_reason": step["finish_reason"],
        "stopped_reason": step["stopped_reason"],
        "reasoning": step["reasoning"],
        "analysis_failed": step["analysis_failed"],
        "next_question_source": step["question_source"],
        "next_question_fallback": step["fallback_used"],
    })
    current.analysis = json.dumps(analysis)
    # Never fabricate an assessment: stays empty when the model gave none.
    current.quick_assessment = step["quick_assessment"]
    answered = _answered_count(interactions)

    if step["is_finished"]:
        # Never move a journey backwards if it has already progressed past discovery.
        if journey.status in DISCOVERY_ACTIVE_STATUSES:
            journey.status = "discovery_completed"
        db.commit()
        return _finished_response(journey, current.question_index, answered, settings, step["quick_assessment"])

    next_index = current.question_index + 1
    next_interaction = _interaction_at(db, journey.id, next_index)
    if next_interaction is None:
        next_interaction = _insert_interaction(db, DiscoveryInteraction(
            journey_id=journey.id,
            question_index=next_index,
            question_text=step["next_question"],
            concept_target=step["next_concept_target"] or "Learning conversation",
            analysis=json.dumps({
                "question_fallback": step["fallback_used"],
                "question_source": step["question_source"],
            }),
        ))
    else:
        db.commit()
    return _question_response(journey, next_interaction, answered, settings, step["quick_assessment"])


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
    Start or resume knowledge discovery for a learning journey. Idempotent: returns the pending
    question, the completed state, or finishes processing an answer that was saved but not yet
    followed up. Requests for the same journey are serialized, so a reload during a slow model
    call waits for the in-flight request and then returns its outcome.
    """
    async with discovery_locks.hold(journey_id):
        journey = _get_journey_or_404(db, journey_id)
        interactions = _all_interactions(db, journey_id)
        answered = _answered_count(interactions)

        # Pending (unanswered) question
        pending = next((i for i in reversed(interactions) if i.learner_answer is None), None)
        if pending:
            return _question_response(journey, pending, answered, settings)

        # Check if discovery already concluded (or the journey has moved on to later stages)
        if journey.status in DISCOVERY_CONCLUDED_STATUSES:
            return _finished_response(
                journey, len(interactions), answered, settings, "Discovery already completed."
            )

        # Last answer was saved but the follow-up step did not finish: resume it
        if interactions:
            logger.info("Resuming discovery for journey %s after interrupted step", journey_id)
            return await _advance(db, journey, interactions[-1], settings)

        # Fresh start: generate the opening question
        provider = get_llm_provider(settings)
        try:
            init_res = await _with_deadline(
                run_initial_discovery(
                    journey_id=journey.id,
                    topic=journey.topic,
                    provider=provider,
                    max_questions=settings.discovery_max_questions,
                ),
                settings,
            )
        except DiscoveryProviderError as err:
            logger.error("Discovery provider failure starting journey %s: %s", journey.id, err)
            raise _provider_error(err)

        interaction = _insert_interaction(db, DiscoveryInteraction(
            journey_id=journey.id,
            question_index=1,
            question_text=init_res["question_text"],
            concept_target=init_res["concept_target"],
            analysis=json.dumps({
                "question_fallback": init_res["fallback_used"],
                "question_source": init_res["question_source"],
            }),
        ))
        if journey.status == "created":
            journey.status = "discovery"
            db.commit()

        return _question_response(journey, interaction, 0, settings)


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
    Submit an answer to the active discovery question, receive the next adaptive question
    (or completion). The answer is persisted before any model call. If `question_index` is sent,
    the answer is accepted only for that question, so a stale submit can never land on a later one.
    """
    async with discovery_locks.hold(journey_id):
        journey = _get_journey_or_404(db, journey_id)

        latest = (
            db.query(DiscoveryInteraction)
            .filter(DiscoveryInteraction.journey_id == journey_id)
            .order_by(DiscoveryInteraction.question_index.desc())
            .first()
        )

        if journey.status == "discovery_completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Discovery for this journey has already concluded.",
            )
        if latest is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No pending question to answer. Start discovery first.",
            )
        if payload.question_index is not None and payload.question_index != latest.question_index:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This question is no longer the active one. Reload the conversation to continue.",
            )
        if latest.learner_answer is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Your previous answer was saved, but the next question is not ready yet. "
                       "Resume the conversation to continue.",
            )

        # Atomically claim the question (also guards against another process answering it).
        claimed = (
            db.query(DiscoveryInteraction)
            .filter(DiscoveryInteraction.id == latest.id, DiscoveryInteraction.learner_answer.is_(None))
            .update(
                {"learner_answer": payload.answer, "answered_at": get_utc_now()},
                synchronize_session=False,
            )
        )
        db.commit()
        if claimed == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This question has already been answered.",
            )
        db.refresh(latest)

        return await _advance(db, journey, latest, settings)


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
    journey = _get_journey_or_404(db, journey_id)
    interactions = _all_interactions(db, journey_id)

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
