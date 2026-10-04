from datetime import datetime
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class UserProfileResponse(BaseModel):
    """
    Public and safe user identity read model.
    """
    id: str
    user_id: str
    email: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserProfileUpdate(BaseModel):
    """
    Payload for updating user public identity.
    """
    display_name: Optional[str] = Field(None, max_length=100, description="Display name / full name")
    bio: Optional[str] = Field(None, max_length=255, description="Short technical bio or role")
    avatar_url: Optional[str] = Field(None, max_length=500, description="Avatar image URL")


class LearnerSettingsResponse(BaseModel):
    """
    Learner preferences and live knowledge overview statistics.
    """
    experience_level: str
    preferred_language: str
    secondary_languages: List[str] = Field(default_factory=list)
    explanation_depth: str
    learning_style: str
    target_goals: Optional[str] = None
    stats: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class LearnerSettingsUpdate(BaseModel):
    """
    Payload for updating pedagogical defaults and preferences.
    """
    experience_level: Optional[Literal["beginner", "intermediate", "senior", "staff"]] = None
    preferred_language: Optional[Literal["python", "typescript", "rust", "go", "cpp"]] = None
    secondary_languages: Optional[List[str]] = None
    explanation_depth: Optional[Literal["intuitive", "internals", "mechanics"]] = None
    learning_style: Optional[Literal["visual_first", "code_first", "code_and_visual", "text_first"]] = None
    target_goals: Optional[str] = Field(None, max_length=500)


class ChangePasswordRequest(BaseModel):
    """
    Payload for changing an authenticated user's password.
    """
    current_password: str = Field(..., min_length=1, description="Current account password")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password with at least 8 characters")
