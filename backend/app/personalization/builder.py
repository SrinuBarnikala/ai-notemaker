"""
PersonalizationContextBuilder: Assembles the transient, in-memory PersonalizationContext.
Enforces strict journey ownership validation and provides safe fallbacks for missing/empty learner data.
"""
import json
import logging
from typing import Optional, List, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.models.user_profile import UserProfile
from backend.app.models.assessment import Assessment, AssessmentSubmission
from backend.app.memory.memory_service import get_all_concept_memories
from backend.app.personalization.models import (
    PersonalizationContext,
    LearnerProfileContext,
    TopicKnowledgeContext,
    EmpiricalMasteryContext,
    CrossJourneyPriorContext,
)

logger = logging.getLogger(__name__)


class JourneyNotFoundError(HTTPException):
    def __init__(self, journey_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning journey '{journey_id}' not found.",
        )


class JourneyOwnershipError(HTTPException):
    def __init__(self, journey_id: str, user_id: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User '{user_id}' does not have permission to access learning journey '{journey_id}'.",
        )


def safe_load_str_list(val: Any) -> List[str]:
    """
    Safely deserializes any string, list, or JSON representation into a list of non-empty strings.
    """
    if not val:
        return []
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str:
            return []
        try:
            parsed = json.loads(val_str)
        except Exception:
            import ast
            try:
                parsed = ast.literal_eval(val_str)
            except Exception:
                if val_str.startswith("[") or val_str.startswith("{") or "{" in val_str or "[" in val_str:
                    return []
                elif "," in val_str:
                    parsed = [item.strip() for item in val_str.split(",") if item.strip()]
                else:
                    parsed = [val_str]
    elif isinstance(val, (list, set, tuple)):
        parsed = list(val)
    else:
        return []

    if not isinstance(parsed, list):
        return []

    result: List[str] = []
    for item in parsed:
        if isinstance(item, str) and item.strip():
            cleaned = item.strip()
            if cleaned not in result:
                result.append(cleaned)
        elif isinstance(item, dict) and item.get("name"):
            cleaned = str(item["name"]).strip()
            if cleaned and cleaned not in result:
                result.append(cleaned)
    return result


class PersonalizationContextBuilder:
    """
    Builder responsible for composing the complete PersonalizationContext
    from multiple relational sources on-demand.
    """

    @classmethod
    def build(
        cls,
        journey_id: str,
        db: Session,
        user_id: Optional[str] = None,
        require_auth_if_owned: bool = False,
    ) -> PersonalizationContext:
        """
        Builds the unified PersonalizationContext for a given journey.

        Args:
            journey_id: The UUID of the LearningJourney.
            db: Active SQLAlchemy Session.
            user_id: Optional UUID of the requesting authenticated user.
            require_auth_if_owned: If True and the journey has an owner, raises 401 if user_id is None.

        Raises:
            JourneyNotFoundError: If journey_id does not exist.
            JourneyOwnershipError: If journey belongs to a different user than user_id.
            HTTPException(401): If require_auth_if_owned is True and user_id is missing on owned journey.
        """
        # 1. Fetch Journey & Validate Existence
        journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
        if not journey:
            raise JourneyNotFoundError(journey_id)

        # 2. Strict Journey Ownership Validation
        if user_id is not None:
            if journey.user_id is not None and journey.user_id != user_id:
                logger.warning(
                    "Ownership violation: user %s attempted to access journey %s owned by %s",
                    user_id,
                    journey_id,
                    journey.user_id,
                )
                raise JourneyOwnershipError(journey_id, user_id)
        elif require_auth_if_owned and journey.user_id is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to access this learning journey.",
            )

        effective_user_id = user_id or journey.user_id

        # 3. Assemble Learner Baseline Preferences (UserProfile)
        learner_profile_ctx = cls._build_learner_profile_context(db, effective_user_id)

        # 4. Assemble Topic-Specific Mental Model (KnowledgeProfile + KnowledgeConcept)
        topic_knowledge_ctx = cls._build_topic_knowledge_context(db, journey.id)

        # 5. Assemble Empirical Verification (Assessment + AssessmentSubmission)
        empirical_mastery_ctx = cls._build_empirical_mastery_context(db, journey.id)

        # 6. Assemble Cross-Journey Prior Knowledge (MemoryService, user-scoped)
        cross_journey_ctx = cls._build_cross_journey_context(db, journey.id, effective_user_id)

        # 7. Compose and return PersonalizationContext
        return PersonalizationContext(
            journey_id=journey.id,
            topic=journey.topic,
            journey_status=journey.status,
            user_id=effective_user_id,
            learner_profile=learner_profile_ctx,
            topic_knowledge=topic_knowledge_ctx,
            empirical_mastery=empirical_mastery_ctx,
            cross_journey=cross_journey_ctx,
        )

    @classmethod
    def _build_learner_profile_context(
        cls,
        db: Session,
        user_id: Optional[str],
    ) -> LearnerProfileContext:
        """
        Fetches UserProfile defaults or supplies safe fallback values.
        """
        if not user_id:
            return LearnerProfileContext()

        up = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if not up:
            return LearnerProfileContext()

        return LearnerProfileContext(
            experience_level=up.experience_level or "intermediate",
            preferred_language=up.preferred_language or "python",
            secondary_languages=safe_load_str_list(up.secondary_languages),
            explanation_depth=up.explanation_depth or "standard",
            learning_style=up.learning_style or "code_and_visual",
            target_goals=up.target_goals,
        )

    @classmethod
    def _build_topic_knowledge_context(
        cls,
        db: Session,
        journey_id: str,
    ) -> TopicKnowledgeContext:
        """
        Extracts known concepts, active gaps, and misconceptions from KnowledgeProfile & KnowledgeConcept.
        """
        kp = db.query(KnowledgeProfile).filter(KnowledgeProfile.journey_id == journey_id).first()
        if not kp:
            return TopicKnowledgeContext()

        known: List[str] = []
        partial: List[str] = []
        gaps: List[str] = []

        # Structured concepts
        concepts = db.query(KnowledgeConcept).filter(KnowledgeConcept.profile_id == kp.id).all()
        for c in concepts:
            c_name = c.name.strip() if c.name else ""
            if not c_name:
                continue

            if c.category == "known" or c.level == "strong":
                if c_name not in known:
                    known.append(c_name)
            elif c.category == "partially_known" or c.level == "moderate":
                if c_name not in partial:
                    partial.append(c_name)
            else:
                if c_name not in gaps:
                    gaps.append(c_name)

        # Raw gaps list from profile
        raw_gaps = safe_load_str_list(kp.gaps)
        for g in raw_gaps:
            if g and g not in gaps and g not in known:
                gaps.append(g)

        # Raw misconceptions list from profile
        raw_misc = safe_load_str_list(kp.misconceptions)
        misconceptions = [m for m in raw_misc if m]

        return TopicKnowledgeContext(
            overall_confidence=kp.overall_confidence or "unknown",
            mental_model_summary=kp.summary or "",
            known_concepts=known,
            partially_known_concepts=partial,
            active_gaps=gaps,
            misconceptions=misconceptions,
        )

    @classmethod
    def _build_empirical_mastery_context(
        cls,
        db: Session,
        journey_id: str,
    ) -> EmpiricalMasteryContext:
        """
        Extracts empirically verified mastered concepts and quiz performance.
        """
        assess = db.query(Assessment).filter(Assessment.journey_id == journey_id).first()
        if not assess or not assess.submissions:
            return EmpiricalMasteryContext()

        verified_mastered: List[str] = []
        sorted_subs = sorted(assess.submissions, key=lambda s: s.created_at, reverse=True)

        latest_score: Optional[str] = None
        if sorted_subs:
            latest = sorted_subs[0]
            latest_score = f"{latest.score}/{latest.total}"

        for sub in sorted_subs:
            for m in safe_load_str_list(sub.mastered_concepts):
                if m and m not in verified_mastered:
                    verified_mastered.append(m)

        return EmpiricalMasteryContext(
            verified_mastered_concepts=verified_mastered,
            latest_quiz_score=latest_score,
            total_submissions=len(sorted_subs),
        )

    @classmethod
    def _build_cross_journey_context(
        cls,
        db: Session,
        journey_id: str,
        user_id: Optional[str],
    ) -> CrossJourneyPriorContext:
        """
        Extracts mastered concepts from earlier journeys belonging to this user.
        """
        if not user_id:
            return CrossJourneyPriorContext()

        try:
            # Query user concept memories
            user_memories = get_all_concept_memories(db, user_id=user_id)
            prior_concepts: List[str] = []

            for mem in user_memories:
                if mem.first_encountered_journey_id != journey_id:
                    if mem.current_status in ["mastered", "known"]:
                        if mem.concept_name not in prior_concepts:
                            prior_concepts.append(mem.concept_name)

            prior_count = (
                db.query(LearningJourney)
                .filter(
                    LearningJourney.user_id == user_id,
                    LearningJourney.id != journey_id,
                )
                .count()
            )

            return CrossJourneyPriorContext(
                prior_related_concepts=prior_concepts[:6],
                total_prior_journeys=prior_count,
            )
        except Exception as err:
            logger.warning("Error resolving cross-journey context for user %s: %s", user_id, err)
            return CrossJourneyPriorContext()
