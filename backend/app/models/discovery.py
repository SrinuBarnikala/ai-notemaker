import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from backend.app.db.session import Base


def get_utc_now():
    return datetime.now(timezone.utc)


class DiscoveryInteraction(Base):
    """
    Represents a single discovery question-and-answer interaction within a learning journey.
    """
    __tablename__ = "discovery_interactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    journey_id = Column(
        String(36),
        ForeignKey("learning_journeys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_index = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    concept_target = Column(String(200), nullable=False)
    learner_answer = Column(Text, nullable=True)
    quick_assessment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    answered_at = Column(DateTime(timezone=True), nullable=True)

    journey = relationship("LearningJourney", back_populates="discovery_interactions")

    def __repr__(self):
        return (
            f"<DiscoveryInteraction(id={self.id}, journey_id={self.journey_id}, "
            f"q_index={self.question_index}, target={self.concept_target})>"
        )
