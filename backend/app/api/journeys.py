import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.journey import LearningJourney
from backend.app.schemas.journey import JourneyCreate, JourneyResponse, JourneyListResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=JourneyResponse, status_code=status.HTTP_201_CREATED)
def create_journey(
    journey_in: JourneyCreate,
    db: Session = Depends(get_db),
):
    """
    Topic Intake: Create a new personalized technical learning journey.
    """
    journey = LearningJourney(
        topic=journey_in.topic,
        status="created",
    )
    db.add(journey)
    db.commit()
    db.refresh(journey)
    logger.info("Created learning journey %s for topic: %s", journey.id, journey.topic)
    return journey


@router.get("/{journey_id}", response_model=JourneyResponse)
def get_journey(
    journey_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve a learning journey by its unique ID.
    """
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning journey with ID '{journey_id}' not found.",
        )
    return journey


@router.get("", response_model=JourneyListResponse)
def list_journeys(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List learning journeys ordered by most recent first.
    """
    total = db.query(LearningJourney).count()
    journeys = (
        db.query(LearningJourney)
        .order_by(LearningJourney.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return JourneyListResponse(journeys=journeys, total=total)
