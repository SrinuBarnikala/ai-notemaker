import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.journey import LearningJourney
from backend.app.models.user import User
from backend.app.schemas.journey import JourneyCreate, JourneyResponse, JourneyListResponse
from backend.app.api.deps import get_optional_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=JourneyResponse, status_code=status.HTTP_201_CREATED)
def create_journey(
    journey_in: JourneyCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Topic Intake: Create a new personalized technical learning journey.
    Associates the journey with the authenticated user if logged in.
    """
    journey = LearningJourney(
        topic=journey_in.topic,
        status="created",
        user_id=current_user.id if current_user else None,
    )
    db.add(journey)
    db.commit()
    db.refresh(journey)
    logger.info(
        "Created learning journey %s for topic: %s (user: %s)",
        journey.id,
        journey.topic,
        current_user.id if current_user else "anonymous",
    )
    return journey


@router.get("/{journey_id}", response_model=JourneyResponse)
def get_journey(
    journey_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Retrieve a learning journey by its unique ID.
    Enforces user-ownership and safely claims legacy unassigned journeys.
    """
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning journey with ID '{journey_id}' not found.",
        )

    # Ownership and privacy guard:
    if current_user:
        if journey.user_id is not None and journey.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this learning journey.",
            )
        # Safely adopt legacy anonymous journey to active user
        if journey.user_id is None:
            journey.user_id = current_user.id
            db.add(journey)
            db.commit()
            db.refresh(journey)
            logger.info("Legacy journey %s adopted by user %s", journey.id, current_user.id)
    elif journey.user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access this learning journey.",
        )

    return journey


@router.get("", response_model=JourneyListResponse)
def list_journeys(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    List learning journeys ordered by most recent first.
    Strictly scoped to the authenticated user.
    """
    query = db.query(LearningJourney)
    if current_user:
        query = query.filter(LearningJourney.user_id == current_user.id)
    else:
        query = query.filter(LearningJourney.user_id.is_(None))

    total = query.count()
    journeys = (
        query
        .order_by(LearningJourney.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return JourneyListResponse(journeys=journeys, total=total)

