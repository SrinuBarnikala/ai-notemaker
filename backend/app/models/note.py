import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from backend.app.db.session import Base


def get_utc_now():
    return datetime.now(timezone.utc)


class Note(Base):
    """
    Canonical living technical note persisted as structured data.
    """
    __tablename__ = "notes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    journey_id = Column(
        String(36),
        ForeignKey("learning_journeys.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    topic = Column(String(500), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)

    journey = relationship("LearningJourney", back_populates="note")
    sections = relationship(
        "NoteSection",
        back_populates="note",
        cascade="all, delete-orphan",
        order_by="NoteSection.order_index",
    )
    revisions = relationship(
        "NoteRevision",
        back_populates="note",
        cascade="all, delete-orphan",
        order_by="NoteRevision.version",
    )

    def __repr__(self):
        return f"<Note(id={self.id}, topic={self.topic}, version={self.version})>"


class NoteRevision(Base):
    """
    Historical log of note evolutions, capturing what was requested and changed.
    """
    __tablename__ = "note_revisions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    note_id = Column(
        String(36),
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    evolution_type = Column(String(50), nullable=False)
    section_title = Column(String(300), nullable=True)
    user_prompt = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)

    note = relationship("Note", back_populates="revisions")

    def __repr__(self):
        return f"<NoteRevision(id={self.id}, version={self.version}, type={self.evolution_type})>"



class NoteSection(Base):
    """
    Individual section within a canonical note composed of structured note blocks.
    """
    __tablename__ = "note_sections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    note_id = Column(
        String(36),
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_index = Column(Integer, nullable=False)
    title = Column(String(300), nullable=False)
    section_type = Column(String(50), nullable=False)
    depth = Column(String(50), nullable=False)
    blocks = Column(Text, nullable=False, default="[]")  # JSON string array of structured NoteBlock objects
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)

    note = relationship("Note", back_populates="sections")

    def __repr__(self):
        return f"<NoteSection(id={self.id}, order={self.order_index}, title={self.title})>"
