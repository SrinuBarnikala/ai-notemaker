import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


def get_utc_now():
    return datetime.now(timezone.utc)


class LearningJourney(Base):
    """
    Represents a learner's personalized learning journey for a technical topic.
    """
    __tablename__ = "learning_journeys"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    topic = Column(String(500), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="created", index=True)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)

    discovery_interactions = relationship(
        "DiscoveryInteraction",
        back_populates="journey",
        cascade="all, delete-orphan",
        order_by="DiscoveryInteraction.question_index",
    )

    knowledge_profile = relationship(
        "KnowledgeProfile",
        back_populates="journey",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<LearningJourney(id={self.id}, topic={self.topic}, status={self.status})>"


