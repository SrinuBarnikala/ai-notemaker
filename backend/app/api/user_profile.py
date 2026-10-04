import json
import logging
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.models.user_profile import UserProfile
from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.schemas.user_profile import (
    UserProfileResponse,
    UserProfileUpdate,
    LearnerSettingsResponse,
    LearnerSettingsUpdate,
    ChangePasswordRequest,
)
from backend.app.core.security import verify_password, get_password_hash
from backend.app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


def get_or_create_user_profile(user: User, db: Session) -> UserProfile:
    """
    Retrieve UserProfile or automatically provision a default one if missing (lazy creation).
    """
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not profile:
        email_prefix = user.email.split("@")[0]
        fallback_name = email_prefix.replace(".", " ").replace("-", " ").replace("_", " ").title()
        profile = UserProfile(
            user_id=user.id,
            display_name=fallback_name,
            experience_level="intermediate",
            preferred_language="python",
            secondary_languages="[]",
            explanation_depth="internals",
            learning_style="code_and_visual",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        logger.info("Auto-provisioned default profile for user %s", user.id)
    return profile


def get_user_learning_stats(user_id: str, db: Session) -> Dict[str, Any]:
    """
    Aggregate live knowledge memory metrics scoped strictly to the authenticated user.
    """
    total_journeys = (
        db.query(LearningJourney)
        .filter(LearningJourney.user_id == user_id)
        .count()
    )

    concepts_query = (
        db.query(KnowledgeConcept)
        .join(KnowledgeProfile, KnowledgeConcept.profile_id == KnowledgeProfile.id)
        .join(LearningJourney, KnowledgeProfile.journey_id == LearningJourney.id)
        .filter(LearningJourney.user_id == user_id)
    )

    total_concepts = concepts_query.count()
    mastered_concepts = concepts_query.filter(KnowledgeConcept.level == "strong").count()
    unresolved_gaps = concepts_query.filter(KnowledgeConcept.category == "unknown").count()

    return {
        "total_journeys": total_journeys,
        "total_concepts": total_concepts,
        "mastered_concepts": mastered_concepts,
        "unresolved_gaps": unresolved_gaps,
    }


@router.get("/me", response_model=UserProfileResponse)
def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve authenticated user profile.
    Automatically provisions default profile if none exists.
    """
    profile = get_or_create_user_profile(current_user, db)
    return UserProfileResponse(
        id=profile.id,
        user_id=current_user.id,
        email=current_user.email,
        display_name=profile.display_name,
        avatar_url=profile.avatar_url,
        bio=profile.bio,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.patch("/me", response_model=UserProfileResponse)
def update_my_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update editable identity fields (display_name, bio, avatar_url).
    """
    profile = get_or_create_user_profile(current_user, db)

    if payload.display_name is not None:
        clean_name = payload.display_name.strip()
        profile.display_name = clean_name if clean_name else None

    if payload.bio is not None:
        clean_bio = payload.bio.strip()
        profile.bio = clean_bio if clean_bio else None

    if payload.avatar_url is not None:
        clean_avatar = payload.avatar_url.strip()
        profile.avatar_url = clean_avatar if clean_avatar else None

    db.commit()
    db.refresh(profile)

    logger.info("Updated profile identity for user %s", current_user.id)
    return UserProfileResponse(
        id=profile.id,
        user_id=current_user.id,
        email=current_user.email,
        display_name=profile.display_name,
        avatar_url=profile.avatar_url,
        bio=profile.bio,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get("/me/learning", response_model=LearnerSettingsResponse)
def get_my_learner_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve global learner preferences and live knowledge stats.
    """
    profile = get_or_create_user_profile(current_user, db)
    stats = get_user_learning_stats(current_user.id, db)

    try:
        sec_langs = json.loads(profile.secondary_languages or "[]")
    except Exception:
        sec_langs = []

    return LearnerSettingsResponse(
        experience_level=profile.experience_level,
        preferred_language=profile.preferred_language,
        secondary_languages=sec_langs,
        explanation_depth=profile.explanation_depth,
        learning_style=profile.learning_style,
        target_goals=profile.target_goals,
        stats=stats,
    )


@router.patch("/me/learning", response_model=LearnerSettingsResponse)
def update_my_learner_settings(
    payload: LearnerSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update pedagogical defaults and preferences.
    """
    profile = get_or_create_user_profile(current_user, db)

    if payload.experience_level is not None:
        profile.experience_level = payload.experience_level

    if payload.preferred_language is not None:
        profile.preferred_language = payload.preferred_language

    if payload.secondary_languages is not None:
        profile.secondary_languages = json.dumps(payload.secondary_languages)

    if payload.explanation_depth is not None:
        profile.explanation_depth = payload.explanation_depth

    if payload.learning_style is not None:
        profile.learning_style = payload.learning_style

    if payload.target_goals is not None:
        clean_goals = payload.target_goals.strip()
        profile.target_goals = clean_goals if clean_goals else None

    db.commit()
    db.refresh(profile)

    stats = get_user_learning_stats(current_user.id, db)
    try:
        sec_langs = json.loads(profile.secondary_languages or "[]")
    except Exception:
        sec_langs = []

    logger.info("Updated learner settings for user %s", current_user.id)
    return LearnerSettingsResponse(
        experience_level=profile.experience_level,
        preferred_language=profile.preferred_language,
        secondary_languages=sec_langs,
        explanation_depth=profile.explanation_depth,
        learning_style=profile.learning_style,
        target_goals=profile.target_goals,
        stats=stats,
    )


@router.post("/me/change-password")
def change_my_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Change account password after verifying current credentials.
    """
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    if len(payload.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters long.",
        )

    current_user.hashed_password = get_password_hash(payload.new_password)
    db.commit()

    logger.info("Password successfully rotated for user %s", current_user.id)
    return {"message": "Password updated successfully."}
