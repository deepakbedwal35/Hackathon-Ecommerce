from collections.abc import Callable
import uuid
from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.models.enums import UserRole
from app.models.models import User

# auto_error=False ensures missing or malformed auth headers are intercepted by us
# and formatted into our uniform AppError JSON shape instead of FastAPI's default.
security_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Extracts Bearer token, validates JWT claims, and loads user from DB.
    Never trusts role in token; re-loads user from database by sub on every request.
    """
    if credentials is None or not credentials.credentials:
        raise AppError(
            code="NOT_AUTHENTICATED",
            message="Authentication credentials were not provided",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = credentials.credentials
    payload = decode_access_token(token)

    sub = payload.get("sub")
    if not sub:
        raise AppError(
            code="INVALID_TOKEN",
            message="Invalid or expired token",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        user_uuid = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise AppError(
            code="INVALID_TOKEN",
            message="Invalid or expired token",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from exc

    user = db.scalar(select(User).where(User.id == user_uuid))
    if user is None:
        raise AppError(
            code="INVALID_TOKEN",
            message="Invalid or expired token",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    return user


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    """Dependency factory checking if current user holds one of the specified roles."""

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise AppError(
                code="FORBIDDEN",
                message="You do not have permission to perform this action",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return current_user

    return role_checker


# Role-checking convenience dependencies
require_customer = require_roles(UserRole.CUSTOMER)
require_staff = require_roles(UserRole.AGENT, UserRole.ADMIN)
