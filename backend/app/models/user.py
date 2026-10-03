import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


def get_utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    """
    Represents an authenticated user/learner.
    """
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)

    journeys = relationship(
        "LearningJourney",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(LearningJourney.created_at)",
    )

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"
