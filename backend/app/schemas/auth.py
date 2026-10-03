"""
Pydantic schemas for Authentication: Login, Registration foundation, and User profile.
"""
import re
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ConfigDict

# Standard RFC 5322 compatible email pattern
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")



class UserLogin(BaseModel):
    """Payload for user login."""
    email: str = Field(..., min_length=3, max_length=255, description="User email address")
    password: str = Field(..., min_length=1, description="Account password")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not clean or not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email format.")
        return clean


class UserRegister(BaseModel):
    """
    Payload for user registration (Backend foundation for future Register step).
    """
    email: str = Field(..., min_length=3, max_length=255, description="User email address")
    password: str = Field(..., min_length=8, max_length=128, description="Account password with at least 8 characters")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not clean or not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email format.")
        return clean


class UserResponse(BaseModel):
    """
    Safe public user profile.
    NEVER includes password, hashed_password, or internal security fields.
    """
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    created_at: datetime



class TokenResponse(BaseModel):
    """Access token payload returned upon successful authentication."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
