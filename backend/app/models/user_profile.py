import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from backend.app.db.session import Base


def get_utc_now():
    return datetime.now(timezone.utc)


class UserProfile(Base):
    """
    Companion profile storing human identity and baseline pedagogical preferences
    for an authenticated learner.
    """
    __tablename__ = "user_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Public Account Identity
    display_name = Column(String(100), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    bio = Column(String(255), nullable=True)

    # Global Learner Preferences & Defaults
    experience_level = Column(String(50), nullable=False, default="intermediate")
    preferred_language = Column(String(50), nullable=False, default="python")
    secondary_languages = Column(Text, nullable=False, default="[]")  # JSON string list
    explanation_depth = Column(String(50), nullable=False, default="internals")
    learning_style = Column(String(50), nullable=False, default="code_and_visual")
    target_goals = Column(String(500), nullable=True)

    # Audit Timestamps
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)

    user = relationship("User", back_populates="profile")

    def __repr__(self):
        return f"<UserProfile(id={self.id}, user_id={self.user_id}, name={self.display_name})>"
