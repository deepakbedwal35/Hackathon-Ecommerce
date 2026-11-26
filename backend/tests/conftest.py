import os
from pathlib import Path
import uuid
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from alembic import command
from alembic.config import Config

from app.core.rate_limit import clear_all_rate_limits

# Ensure backend root is on sys.path
backend_path = Path(__file__).resolve().parents[1]
if str(backend_path) not in os.sys.path:
    os.sys.path.insert(0, str(backend_path))

# Test database URL (support_test on the Docker Postgres)
TEST_DB_NAME = "support_test"
POSTGRES_BASE_URL = os.getenv(
    "POSTGRES_BASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432"
)
TEST_DATABASE_URL = f"{POSTGRES_BASE_URL}/{TEST_DB_NAME}"

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET"] = "test-secret-key-at-least-32-chars-long"
os.environ["LLM_API_KEY"] = "test-dummy-api-key"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["CORS_ORIGINS"] = "http://localhost:3000,http://localhost:5173"


@pytest.fixture(scope="session")
def setup_test_postgres():
    """Ensures support_test database exists and has latest migrations applied."""
    admin_engine = create_engine(
        f"{POSTGRES_BASE_URL}/postgres",
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname = '{TEST_DB_NAME}'")
        ).scalar()
        if not exists:
            conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    admin_engine.dispose()

    # Run Alembic migrations on support_test
    alembic_cfg_path = backend_path / "alembic.ini"
    alembic_cfg = Config(str(alembic_cfg_path))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    alembic_cfg.set_main_option("script_location", str(backend_path / "alembic"))
    command.upgrade(alembic_cfg, "head")

    test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db_session(setup_test_postgres):
    """Provides a clean database session per test with truncation and rate-limit reset."""
    clear_all_rate_limits()
    engine = setup_test_postgres
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE audit_events, escalations, ticket_notes, messages, "
                "refunds, tickets, order_items, orders, users CASCADE;"
            )
        )

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session: Session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seeded_db(db_session: Session) -> Session:
    """Pre-seeds the test database with standard seed data."""
    from scripts.seed import seed_database
    seed_database(reset=True, session=db_session)
    return db_session


@pytest.fixture
def client(setup_test_postgres, db_session):
    """FastAPI TestClient wired to the test database session with test-only routes."""
    from app.core.db import get_db
    from app.core.deps import get_current_user, require_staff
    from app.main import create_app
    from app.models.models import User
    from app.services.access import get_order_for_user, get_ticket_for_user

    app = create_app()

    # Test-only routes registered exclusively in test harness
    @app.get("/test/order/{order_id}")
    def test_get_order(
        order_id: uuid.UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        order = get_order_for_user(db, current_user, order_id)
        return {"id": str(order.id), "total_amount": str(order.total_amount)}

    @app.get("/test/ticket/{ticket_id}")
    def test_get_ticket(
        ticket_id: uuid.UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        ticket = get_ticket_for_user(db, current_user, ticket_id)
        return {"id": str(ticket.id), "subject": ticket.subject}

    @app.get("/test/staff-only")
    def test_staff_only(current_user: User = Depends(require_staff)):
        return {"status": "ok", "role": current_user.role.value}

    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
