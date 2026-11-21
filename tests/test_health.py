"""Tests for application health check endpoint."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check() -> None:
    """Test that GET /health returns HTTP 200 and expected response structure."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "app" in data
    assert "environment" in data


def test_cors_allows_configured_origin_and_preflight() -> None:
    """Configured frontend dev origins receive CORS headers on GET and OPTIONS preflight."""
    origin = "http://localhost:3000"

    get_resp = client.get("/health", headers={"Origin": origin})
    assert get_resp.status_code == 200
    assert get_resp.headers.get("access-control-allow-origin") == origin

    preflight_resp = client.options(
        "/api/v1/companies/AAPL/score",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight_resp.status_code == 200
    assert preflight_resp.headers.get("access-control-allow-origin") == origin


def test_cors_blocks_unconfigured_origin() -> None:
    """Origins not in CORS_ALLOW_ORIGINS do not receive allow-origin headers."""
    resp = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers
