import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from backend.app.db.session import Base


def get_utc_now():
    return datetime.now(timezone.utc)


class Assessment(Base):
    """
    Personalized active recall assessment (flashcards and scenario quiz)
    tied to a learning journey and living note.
    """
    __tablename__ = "assessments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    journey_id = Column(
        String(36),
        ForeignKey("learning_journeys.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    note_id = Column(
        String(36),
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    flashcards = Column(Text, nullable=False, default="[]")  # JSON string of FlashcardItem
    quiz_questions = Column(Text, nullable=False, default="[]")  # JSON string of QuizQuestion
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)

    journey = relationship("LearningJourney")
    note = relationship("Note")
    submissions = relationship(
        "AssessmentSubmission",
        back_populates="assessment",
        cascade="all, delete-orphan",
        order_by="AssessmentSubmission.created_at.desc()",
    )

    def __repr__(self):
        return f"<Assessment(id={self.id}, journey_id={self.journey_id})>"


class AssessmentSubmission(Base):
    """
    Submission record of a learner completing a technical mastery quiz.
    """
    __tablename__ = "assessment_submissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = Column(
        String(36),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score = Column(Integer, nullable=False)
    total = Column(Integer, nullable=False)
    answers = Column(Text, nullable=False, default="{}")  # JSON mapping question_id -> chosen_index
    mastered_concepts = Column(Text, nullable=False, default="[]")  # JSON list of concept names
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)

    assessment = relationship("Assessment", back_populates="submissions")

    def __repr__(self):
        return f"<AssessmentSubmission(id={self.id}, score={self.score}/{self.total})>"
