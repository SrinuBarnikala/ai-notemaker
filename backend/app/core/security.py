"""
Authentication & Security Utilities: Password Hashing, JWT Tokens & Cookie Management.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash, Argon2Error
from fastapi import Response

from backend.app.config import get_settings

# Argon2id password hasher instance
_password_hasher = PasswordHasher()


def get_password_hash(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHash, Argon2Error, Exception):
        return False



def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a signed JWT access token for user subject."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": now,
    }
    if extra_claims:
        to_encode.update(extra_claims)

    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a signed JWT access token."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except (jwt.PyJWTError, Exception):
        return None


def set_auth_cookie(response: Response, token: str, max_age: Optional[int] = None) -> None:
    """
    Set HttpOnly, SameSite cookie with token for secure same-origin authentication.
    """
    settings = get_settings()
    if max_age is None:
        max_age = settings.jwt_access_token_expire_minutes * 60
    is_secure = (settings.app_env.lower() == "production")
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        max_age=max_age,
        expires=max_age,
        samesite=settings.auth_cookie_samesite,
        secure=is_secure,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    """Clear the authentication cookie upon logout."""
    settings = get_settings()
    is_secure = (settings.app_env.lower() == "production")
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        httponly=True,
        samesite=settings.auth_cookie_samesite,
        secure=is_secure,
    )
