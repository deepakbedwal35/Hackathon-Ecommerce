from datetime import datetime, timedelta, timezone
from typing import Any
import uuid
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import status
import jwt

from app.core.config import settings
from app.core.errors import AppError

_hasher = PasswordHasher()

# Pre-computed dummy hash to run dummy verification on nonexistent users to eliminate timing side-channels
DUMMY_PASSWORD_HASH = _hasher.hash("dummy_mitigation_password_for_timing_attacks")


def hash_password(password: str) -> str:
    """Hashes a plaintext password using Argon2id."""
    return _hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against an Argon2id hash."""
    try:
        return _hasher.verify(hashed_password, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_dummy_password(password: str) -> bool:
    """Runs a constant-time dummy verification when email does not exist."""
    return verify_password(password, DUMMY_PASSWORD_HASH)


def create_access_token(
    subject: str | uuid.UUID, expires_delta: timedelta | None = None
) -> str:
    """Generates a signed JWT with sub, iat, and exp claims."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    claims: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(claims, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decodes and validates a JWT token using HS256.
    Raises standard 401 INVALID_TOKEN AppError on expired, malformed, or tampered tokens.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            options={"require": ["sub", "iat", "exp"]},
        )
        return payload
    except jwt.PyJWTError as exc:
        raise AppError(
            code="INVALID_TOKEN",
            message="Invalid or expired token",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from exc
