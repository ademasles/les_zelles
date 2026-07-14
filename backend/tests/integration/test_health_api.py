"""Health endpoint smoke test."""

from __future__ import annotations

from tests.integration.test_import_app import _install_optional_dependency_stubs


def test_health_endpoint_returns_ok():
    _install_optional_dependency_stubs()

    from app.main import app

    assert app.routes["GET"]["/api/health"]() == {"status": "ok"}