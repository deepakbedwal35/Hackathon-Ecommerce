from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AppError

router = APIRouter(tags=["Health"])


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check(
    check_timeout: int = Query(
        default=5,
        ge=1,
        description="Optional timeout parameter for health check verification",
    ),
) -> dict[str, str]:
    """
    Liveness probe endpoint. Always returns 200 when service is running.
    Note: Domain services / background checks will be placed in app/services/.
    """
    return {"status": "ok"}


@router.get("/health/db", status_code=status.HTTP_200_OK)
def health_check_db(db: Session = Depends(get_db)) -> dict[str, str]:
    """
    Readiness probe checking database connectivity via SELECT 1.
    Note: Future health-check business logic will be delegated to app/services/health_service.py.
    """
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        raise AppError(
            code="DATABASE_UNAVAILABLE",
            message="Database connection check failed",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=None,
        ) from exc
