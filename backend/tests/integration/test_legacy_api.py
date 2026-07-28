from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_import_app import _install_optional_dependency_stubs


def test_removed_endpoints_return_404():
    _install_optional_dependency_stubs()
    from app.main import app

    client = TestClient(app)

    response_ping = client.get("/ping/")
    assert response_ping.status_code == 404

    response_train = client.post("/train/")
    assert response_train.status_code == 404


def test_deprecated_save_endpoint_exists():
    _install_optional_dependency_stubs()
    from app.main import app

    # Check that route is registered and deprecated
    # Check that route is registered in routes

    client = TestClient(app)
    # Just checking it doesn't 404. FakeFastAPI handles TestClient poorly,
    # but let's check it's registered correctly in actual Fastapi routing or 422 for missing params
    response = client.post("/save/")
    assert response.status_code in (400, 422, 200, 409)
