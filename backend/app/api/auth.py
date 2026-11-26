import hashlib
import uuid
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session
import structlog

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import AppError, get_request_id
from app.core.rate_limit import check_rate_limit, record_failure, reset_failures
from app.core.security import create_access_token, hash_password, verify_dummy_password, verify_password
from app.models.enums import ActorType, UserRole
from app.models.models import AuditEvent, User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead

logger = structlog.get_logger("auth")

router = APIRouter()


def _hash_email(email: str) -> str:
    """Computes a SHA-256 hash of a normalized email for credential-safe audit logs."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _get_client_ip(request: Request) -> str:
    """Resolves client IP, supporting forward headers if configured."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def _role_to_actor_type(role: UserRole) -> ActorType:
    if role == UserRole.CUSTOMER:
        return ActorType.CUSTOMER
    return ActorType.STAFF


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register new customer account",
)
def register(
    request: Request,
    payload: RegisterRequest,
    db: Session = Depends(get_db),
) -> UserRead:
    """
    Public registration endpoint. Always creates accounts with role=customer.
    Extra fields (e.g. role overrides) are forbidden by schema validation.
    """
    client_ip = _get_client_ip(request)
    request_id = get_request_id(request)
    normalized_email = payload.email.strip().lower()

    # Check for existing email case-insensitively
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing:
        record_failure(client_ip, normalized_email)
        raise AppError(
            code="EMAIL_TAKEN",
            message="An account with this email address already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )

    # Always create role=customer
    new_user = User(
        name=payload.name.strip(),
        email=normalized_email,
        password_hash=hash_password(payload.password),
        role=UserRole.CUSTOMER,
    )
    db.add(new_user)
    db.flush()

    # Append-only audit record storing email hash only (never raw email or password)
    audit = AuditEvent(
        actor_id=new_user.id,
        actor_type=ActorType.CUSTOMER,
        event_type="user_registered",
        entity_type="user",
        entity_id=new_user.id,
        audit_metadata={"email_hash": _hash_email(normalized_email)},
        request_id=request_id,
    )
    db.add(audit)
    db.commit()
    db.refresh(new_user)

    logger.info("user_registered", user_id=str(new_user.id), request_id=request_id)
    return UserRead.model_validate(new_user)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive access token",
)
def login(
    request: Request,
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    Authenticates user credentials and issues an HS256 JWT access token.
    Wrong email and wrong password return the identical 401 response and run
    dummy hash checks on missing emails to mitigate timing side-channels.
    """
    client_ip = _get_client_ip(request)
    request_id = get_request_id(request)
    normalized_email = payload.email.strip().lower()

    # Rate limiting: max 5 failed attempts per minute per (IP + email)
    check_rate_limit(client_ip, normalized_email)

    user = db.scalar(select(User).where(User.email == normalized_email))

    if user is None:
        # Constant-time dummy verification so response duration does not leak account existence
        verify_dummy_password(payload.password)
        record_failure(client_ip, normalized_email)

        # Audit failure with email hash
        audit_failed = AuditEvent(
            actor_id=None,
            actor_type=ActorType.SYSTEM,
            event_type="login_failed",
            entity_type="auth",
            entity_id=uuid.uuid4(),
            audit_metadata={
                "email_hash": _hash_email(normalized_email),
                "reason": "invalid_credentials",
            },
            request_id=request_id,
        )
        db.add(audit_failed)
        db.commit()

        logger.warning("login_failed", request_id=request_id)
        raise AppError(
            code="INVALID_CREDENTIALS",
            message="Invalid email or password.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if not verify_password(payload.password, user.password_hash):
        record_failure(client_ip, normalized_email)

        audit_failed = AuditEvent(
            actor_id=user.id,
            actor_type=_role_to_actor_type(user.role),
            event_type="login_failed",
            entity_type="auth",
            entity_id=user.id,
            audit_metadata={
                "email_hash": _hash_email(normalized_email),
                "reason": "invalid_credentials",
            },
            request_id=request_id,
        )
        db.add(audit_failed)
        db.commit()

        logger.warning("login_failed", user_id=str(user.id), request_id=request_id)
        raise AppError(
            code="INVALID_CREDENTIALS",
            message="Invalid email or password.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # Success: clear failed attempts
    reset_failures(client_ip, normalized_email)

    access_token = create_access_token(subject=str(user.id))

    audit_success = AuditEvent(
        actor_id=user.id,
        actor_type=_role_to_actor_type(user.role),
        event_type="login_success",
        entity_type="user",
        entity_id=user.id,
        audit_metadata={"email_hash": _hash_email(normalized_email)},
        request_id=request_id,
    )
    db.add(audit_success)
    db.commit()

    logger.info("login_success", user_id=str(user.id), request_id=request_id)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
def get_me(current_user: User = Depends(get_current_user)) -> UserRead:
    """Returns the authenticated user loaded fresh from the database on each request."""
    return UserRead.model_validate(current_user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout current session",
)
def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """
    Stateless JWT logout. The server records the logout audit event and logs it.
    The client application must discard the stored JWT access token locally.
    """
    request_id = get_request_id(request)

    audit_logout = AuditEvent(
        actor_id=current_user.id,
        actor_type=_role_to_actor_type(current_user.role),
        event_type="user_logout",
        entity_type="user",
        entity_id=current_user.id,
        audit_metadata={},
        request_id=request_id,
    )
    db.add(audit_logout)
    db.commit()

    logger.info("user_logout", user_id=str(current_user.id), request_id=request_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
