import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from backend.app.db.session import Base


def get_utc_now():
    return datetime.now(timezone.utc)


class KnowledgeProfile(Base):
    """
    Synthesized knowledge profile representing a learner's mental model,
    categorized concepts, misconceptions, and knowledge gaps.
    """
    __tablename__ = "knowledge_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    journey_id = Column(
        String(36),
        ForeignKey("learning_journeys.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    overall_confidence = Column(String(50), nullable=False, default="intermediate")
    summary = Column(Text, nullable=False)
    misconceptions = Column(Text, nullable=False, default="[]")  # JSON string list
    gaps = Column(Text, nullable=False, default="[]")  # JSON string list
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)

    journey = relationship("LearningJourney", back_populates="knowledge_profile")
    concepts = relationship(
        "KnowledgeConcept",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="KnowledgeConcept.name",
    )

    def __repr__(self):
        return (
            f"<KnowledgeProfile(id={self.id}, journey_id={self.journey_id}, "
            f"confidence={self.overall_confidence})>"
        )


class KnowledgeConcept(Base):
    """
    Specific technical concept mapped in the learner's knowledge profile.
    """
    __tablename__ = "knowledge_concepts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(
        String(36),
        ForeignKey("knowledge_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(200), nullable=False)
    level = Column(String(50), nullable=False)  # 'strong', 'moderate', 'weak', 'unknown'
    category = Column(String(50), nullable=False)  # 'known', 'partially_known', 'unknown'
    notes = Column(Text, nullable=True)

    profile = relationship("KnowledgeProfile", back_populates="concepts")

    def __repr__(self):
        return f"<KnowledgeConcept(name={self.name}, level={self.level}, category={self.category})>"
