from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.core.db import get_db
from app.main import create_app


def test_health_returns_200(client: TestClient) -> None:
    """Test GET /health returns 200 OK and status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "X-Request-ID" in response.headers


def test_health_db_returns_200(client: TestClient) -> None:
    """Test GET /health/db returns 200 OK when database is accessible."""
    response = client.get("/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "X-Request-ID" in response.headers


def test_health_db_failure_returns_503(client: TestClient) -> None:
    """Test GET /health/db returns 503 in standard error shape on failure."""
    app = create_app()

    def failing_get_db():
        mock_session = MagicMock()
        mock_session.execute.side_effect = Exception("DB Connection refused")
        yield mock_session

    app.dependency_overrides[get_db] = failing_get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/health/db")
        assert response.status_code == 503
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert data["error"]["message"] == "Database connection check failed"
        assert data["error"]["details"] is None
        assert "request_id" in data["error"]
        assert data["error"]["request_id"] != ""
        assert response.headers["X-Request-ID"] == data["error"]["request_id"]


def test_unknown_route_returns_standard_error_shape(client: TestClient) -> None:
    """Test requesting an unknown route returns 404 in standard error shape."""
    response = client.get("/api/v1/nonexistent-route")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert data["error"]["message"] == "Not Found"
    assert data["error"]["details"] is None
    assert "request_id" in data["error"]
    assert data["error"]["request_id"] != ""
    assert response.headers["X-Request-ID"] == data["error"]["request_id"]


def test_validation_error_returns_standard_error_shape_with_request_id(
    client: TestClient,
) -> None:
    """Test validation error returns 422 in standard error shape with request_id."""
    # check_timeout must be an integer >= 1
    response = client.get("/health?check_timeout=invalid_value")
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["message"] == "Request validation failed"
    assert data["error"]["details"] is not None
    assert isinstance(data["error"]["details"], list)
    assert "request_id" in data["error"]
    assert data["error"]["request_id"] != ""
    assert response.headers["X-Request-ID"] == data["error"]["request_id"]


def test_custom_request_id_header_propagated(client: TestClient) -> None:
    """Test incoming X-Request-ID is retained and returned."""
    custom_id = "test-request-id-9999"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id
