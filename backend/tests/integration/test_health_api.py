"""Health endpoint smoke test."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_import_app import _install_optional_dependency_stubs


def test_health_endpoint_returns_ok():
    _install_optional_dependency_stubs()

    from app.main import app

    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
