from datetime import datetime
from typing import List
from pydantic import BaseModel, Field, field_validator, ConfigDict


class JourneyCreate(BaseModel):
    topic: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="The technical topic or question to learn (e.g. 'How does RAG work internally?')"
    )

    @field_validator("topic")
    @classmethod
    def validate_topic_not_empty(cls, v: str) -> str:
        trimmed = v.strip()
        if len(trimmed) < 2:
            raise ValueError("Topic must contain at least 2 non-whitespace characters.")
        return trimmed


class JourneyResponse(BaseModel):
    id: str
    topic: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JourneyListResponse(BaseModel):
    journeys: List[JourneyResponse]
    total: int
