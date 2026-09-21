import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from backend.app.db.session import Base


def get_utc_now():
    return datetime.now(timezone.utc)


class NoteArchitecture(Base):
    """
    Personalized structural blueprint for a learner's technical note,
    tailored around their specific knowledge profile, gaps, and misconceptions.
    """
    __tablename__ = "note_architectures"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    journey_id = Column(
        String(36),
        ForeignKey("learning_journeys.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    topic = Column(String(500), nullable=False)
    learning_goal = Column(Text, nullable=False, default="Master core mechanics and practical architecture")
    summary_rationale = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)

    journey = relationship("LearningJourney", back_populates="note_architecture")
    sections = relationship(
        "NoteArchitectureSection",
        back_populates="architecture",
        cascade="all, delete-orphan",
        order_by="NoteArchitectureSection.order_index",
    )

    def __repr__(self):
        return f"<NoteArchitecture(id={self.id}, topic={self.topic}, sections_count={len(self.sections)})>"


class NoteArchitectureSection(Base):
    """
    Individual section blueprint within a personalized note architecture.
    """
    __tablename__ = "note_architecture_sections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    architecture_id = Column(
        String(36),
        ForeignKey("note_architectures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_index = Column(Integer, nullable=False)
    title = Column(String(300), nullable=False)
    section_type = Column(String(50), nullable=False)  # mental_model, deep_dive, bridge, code_walkthrough, pitfall_warning
    depth = Column(String(50), nullable=False)  # brief, standard, deep
    target_concepts = Column(Text, nullable=False, default="[]")  # JSON string list
    rationale = Column(Text, nullable=False)  # Personalization reason
    needs_code = Column(Boolean, default=False, nullable=False)
    needs_visual = Column(Boolean, default=False, nullable=False)
    visual_type = Column(String(100), nullable=True)  # architecture_diagram, flowchart, comparison_table

    architecture = relationship("NoteArchitecture", back_populates="sections")

    def __repr__(self):
        return f"<NoteArchitectureSection(order={self.order_index}, title={self.title}, depth={self.depth})>"
