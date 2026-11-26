from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, health, refunds, staff, tickets
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware


def create_app() -> FastAPI:
    """
    Application factory initializing configuration, logging, middlewares,
    error handlers, and API routers.
    """
    setup_logging(settings.LOG_LEVEL)

    app = FastAPI(
        title="E-Commerce AI Customer Support Platform API",
        description=(
            "Backend foundation and infrastructure for an E-Commerce AI "
            "Customer Support platform providing automated resolution, "
            "agent assistance, and service health monitoring."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Global middlewares
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Standardized error handling
    register_error_handlers(app)

    # Health check routes (root-level)
    app.include_router(health.router)

    # API v1 router prefix for domain routes
    api_v1_router = APIRouter(prefix="/api/v1")
    api_v1_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
    api_v1_router.include_router(refunds.router, prefix="/refunds", tags=["Refunds"])
    api_v1_router.include_router(staff.router, prefix="/staff", tags=["Staff"])
    api_v1_router.include_router(tickets.router, prefix="/tickets", tags=["Customer Tickets"])
    app.include_router(api_v1_router)

    return app


app = create_app()
