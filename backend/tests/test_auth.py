from datetime import datetime, timedelta, timezone
import uuid
from fastapi.testclient import TestClient
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.models.enums import UserRole
from app.models.models import AuditEvent, User


def test_register_works_and_hides_password_data(client: TestClient) -> None:
    """Test user registration succeeds, returns 201, role customer, and no password data."""
    payload = {
        "name": "Alice Green",
        "email": "alice@example.com",
        "password": "Password123",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Alice Green"
    assert data["email"] == "alice@example.com"
    assert data["role"] == "customer"
    assert "password" not in data
    assert "password_hash" not in data
    assert "id" in data


def test_register_rejects_role_field_with_422(client: TestClient) -> None:
    """Test sending a role in register is forbidden and raises 422."""
    payload = {
        "name": "Hacker Bob",
        "email": "bob@example.com",
        "password": "Password123",
        "role": "admin",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "request_id" in data["error"]


def test_register_duplicate_email_case_variations_returns_409(
    client: TestClient,
) -> None:
    """Test duplicate registration with case variations yields 409 EMAIL_TAKEN."""
    client.post(
        "/api/v1/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "Password123"},
    )

    # Attempt with uppercase
    response = client.post(
        "/api/v1/auth/register",
        json={"name": "Alice 2", "email": "ALICE@EXAMPLE.COM", "password": "Password123"},
    )
    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "EMAIL_TAKEN"
    assert "request_id" in data["error"]


def test_register_weak_password_returns_422_standard_shape(
    client: TestClient,
) -> None:
    """Test passwords failing length, letter, or digit rules yield 422."""
    # Too short (<8)
    res_short = client.post(
        "/api/v1/auth/register",
        json={"name": "Short", "email": "short@example.com", "password": "Pass1"},
    )
    assert res_short.status_code == 422
    assert res_short.json()["error"]["code"] == "VALIDATION_ERROR"

    # No number
    res_no_num = client.post(
        "/api/v1/auth/register",
        json={"name": "NoNum", "email": "nonum@example.com", "password": "PasswordOnly"},
    )
    assert res_no_num.status_code == 422

    # No letters
    res_no_let = client.post(
        "/api/v1/auth/register",
        json={"name": "NoLet", "email": "nolet@example.com", "password": "1234567890"},
    )
    assert res_no_let.status_code == 422


def test_login_success_and_me(client: TestClient) -> None:
    """Test successful login returns a JWT bearer token that grants access to /me."""
    client.post(
        "/api/v1/auth/register",
        json={"name": "User Me", "email": "me@example.com", "password": "ValidPassword1"},
    )

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "me@example.com", "password": "ValidPassword1"},
    )
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["user"]["email"] == "me@example.com"

    token = token_data["access_token"]

    # Access /me
    me_res = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "me@example.com"
    assert me_res.json()["name"] == "User Me"


def test_wrong_password_and_unknown_email_identical_response(
    client: TestClient,
) -> None:
    """Test wrong password vs unknown email return identical 401 status and error shape."""
    client.post(
        "/api/v1/auth/register",
        json={"name": "Known User", "email": "known@example.com", "password": "CorrectPassword1"},
    )

    # 1. Known user, wrong password
    res_wrong_pw = client.post(
        "/api/v1/auth/login",
        json={"email": "known@example.com", "password": "WrongPassword2"},
    )
    assert res_wrong_pw.status_code == 401

    # 2. Unknown email
    res_unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.com", "password": "SomePassword1"},
    )
    assert res_unknown.status_code == 401

    # Both must match code, message, details
    err_wrong_pw = res_wrong_pw.json()["error"]
    err_unknown = res_unknown.json()["error"]
    assert err_wrong_pw["code"] == "INVALID_CREDENTIALS"
    assert err_unknown["code"] == "INVALID_CREDENTIALS"
    assert err_wrong_pw["message"] == err_unknown["message"]
    assert err_wrong_pw["details"] == err_unknown["details"]


def test_missing_auth_header_returns_401(client: TestClient) -> None:
    """Test calling /me with no Authorization header returns standard 401."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "NOT_AUTHENTICATED"
    assert "request_id" in data["error"]


def test_expired_and_tampered_token(client: TestClient) -> None:
    """Test expired or forged tokens return standard 401 INVALID_TOKEN."""
    # Expired token
    now = datetime.now(timezone.utc)
    expired_claims = {
        "sub": str(uuid.uuid4()),
        "iat": int((now - timedelta(hours=2)).timestamp()),
        "exp": int((now - timedelta(hours=1)).timestamp()),
    }
    expired_token = jwt.encode(expired_claims, settings.JWT_SECRET, algorithm="HS256")

    res_exp = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert res_exp.status_code == 401
    assert res_exp.json()["error"]["code"] == "INVALID_TOKEN"

    # Tampered token (signed with different secret)
    tampered_token = jwt.encode(
        {"sub": str(uuid.uuid4()), "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=1)).timestamp())},
        "wrong-secret-key-32-chars-long-here-abc",
        algorithm="HS256",
    )
    res_tamp = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_token}"}
    )
    assert res_tamp.status_code == 401
    assert res_tamp.json()["error"]["code"] == "INVALID_TOKEN"


def test_token_for_deleted_user_returns_401(
    client: TestClient, db_session: Session
) -> None:
    """Test that a token corresponding to a deleted database user is rejected with 401."""
    reg = client.post(
        "/api/v1/auth/register",
        json={"name": "Ephemeral", "email": "ephemeral@example.com", "password": "Password123"},
    )
    user_id = reg.json()["id"]

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "ephemeral@example.com", "password": "Password123"},
    )
    token = login.json()["access_token"]

    # Delete user from DB
    user = db_session.get(User, uuid.UUID(user_id))
    assert user is not None
    db_session.delete(user)
    db_session.commit()

    # Now /me with this token must fail with 401
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "INVALID_TOKEN"


def test_rate_limiter_blocks_on_sixth_failed_attempt(client: TestClient) -> None:
    """Test 5 failed login attempts are allowed, 6th returns 429 with Retry-After header."""
    for _ in range(5):
        res = client.post(
            "/api/v1/auth/login",
            json={"email": "target@example.com", "password": "WrongPassword1"},
        )
        assert res.status_code == 401

    # 6th attempt within window
    res_blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "target@example.com", "password": "WrongPassword1"},
    )
    assert res_blocked.status_code == 429
    assert res_blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in res_blocked.headers


def test_rate_limiter_blocks_on_register_after_repeated_failures(
    client: TestClient,
) -> None:
    """Test 5 failed registration attempts are allowed, 6th returns 429 with Retry-After header."""
    # Register an account first so subsequent attempts trigger conflict
    client.post(
        "/api/v1/auth/register",
        json={"name": "Taken", "email": "taken@example.com", "password": "Password123"},
    )

    for _ in range(5):
        res = client.post(
            "/api/v1/auth/register",
            json={"name": "Attacker", "email": "taken@example.com", "password": "Password123"},
        )
        assert res.status_code == 409

    # 6th attempt within window
    res_blocked = client.post(
        "/api/v1/auth/register",
        json={"name": "Attacker", "email": "taken@example.com", "password": "Password123"},
    )
    assert res_blocked.status_code == 429
    assert res_blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in res_blocked.headers


def test_audit_events_created_without_raw_credentials(
    client: TestClient, db_session: Session
) -> None:
    """Test audit events are logged for register, login, and logout without raw passwords or emails."""
    # Register
    client.post(
        "/api/v1/auth/register",
        json={"name": "Audit Tester", "email": "audit@example.com", "password": "SecretPassword1"},
    )

    # Failed login
    client.post(
        "/api/v1/auth/login",
        json={"email": "audit@example.com", "password": "IncorrectPassword1"},
    )

    # Successful login
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "audit@example.com", "password": "SecretPassword1"},
    )
    token = login_res.json()["access_token"]

    # Logout
    logout_res = client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert logout_res.status_code == 204

    # Query audit events
    events = db_session.scalars(select(AuditEvent).order_by(AuditEvent.created_at)).all()
    event_types = [e.event_type for e in events]
    assert "user_registered" in event_types
    assert "login_failed" in event_types
    assert "login_success" in event_types
    assert "user_logout" in event_types

    # Ensure no raw password or raw email is present anywhere in audit event metadata
    for ev in events:
        meta_str = str(ev.audit_metadata).lower()
        assert "secretpassword1" not in meta_str
        assert "incorrectpassword1" not in meta_str
        assert "audit@example.com" not in meta_str
        if "email_hash" in ev.audit_metadata:
            assert len(ev.audit_metadata["email_hash"]) == 64  # valid SHA-256 hex string
