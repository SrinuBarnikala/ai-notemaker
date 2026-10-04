"""
Authentication Endpoints: Login, Current User, Logout & Registration Foundation.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.models.user_profile import UserProfile
from backend.app.schemas.auth import (
    UserLogin,
    UserRegister,
    UserResponse,
    TokenResponse,
)
from backend.app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    set_auth_cookie,
    clear_auth_cookie,
)
from backend.app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(
    credentials: UserLogin,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Authenticate user with email and password.
    Returns JWT access token and sets secure HttpOnly session cookie.
    Generic error message prevents email account enumeration.
    """
    email = credentials.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()

    # Generic authentication failure message
    invalid_err = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not user:
        # Dummy verification to mitigate timing attacks
        verify_password("dummy-password", "$argon2id$v=19$m=65536,t=3,p=4$dummy$dummy")
        raise invalid_err

    if not verify_password(credentials.password, user.hashed_password):
        raise invalid_err

    # Generate session access token
    access_token = create_access_token(subject=user.id)

    # Set secure HttpOnly cookie for same-origin browsing
    set_auth_cookie(response, access_token)

    logger.info("User logged in successfully: %s (%s)", user.id, user.email)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user),
):
    """
    Return authenticated user profile.
    NEVER returns password or hashed credentials.
    """
    return UserResponse.model_validate(current_user)


@router.post("/logout")
def logout(
    response: Response,
):
    """
    Invalidate session by clearing the HttpOnly authentication cookie.
    """
    clear_auth_cookie(response)
    return {"message": "Logged out successfully."}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    user_in: UserRegister,
    db: Session = Depends(get_db),
):
    """
    Backend foundation for user registration (Future Register Page step).
    Validates email format, minimum password complexity, and hashes with Argon2id.
    """
    email = user_in.email.strip().lower()
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    hashed_pw = get_password_hash(user_in.password)
    new_user = User(
        email=email,
        hashed_password=hashed_pw,
    )
    db.add(new_user)
    db.flush()

    email_prefix = email.split("@")[0]
    fallback_name = email_prefix.replace(".", " ").replace("-", " ").replace("_", " ").title()
    new_profile = UserProfile(
        user_id=new_user.id,
        display_name=fallback_name,
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_user)

    logger.info("New user registered: %s (%s)", new_user.id, new_user.email)
    return UserResponse.model_validate(new_user)
