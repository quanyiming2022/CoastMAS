"""Shared isolated test workspace, discovered by pytest without re-export imports."""

import pytest
from coastmas_next.app import create_app
from coastmas_next.config import Settings
from coastmas_next.store import Store
from fastapi.testclient import TestClient


@pytest.fixture
def workspace(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/next.db", storage_root=tmp_path / "objects"
    )
    store = Store(settings)
    store.initialize()
    admin = store.create_account("admin@example.test", "safe-password-for-tests", system_admin=True)
    project = store.create_project(admin, "New scientific workspace")
    viewer = store.create_account("viewer@example.test", "safe-password-for-tests")
    store.set_member(admin, project, viewer, "viewer")
    client = TestClient(create_app(settings))
    response = client.post(
        "/api/session", json={"email": "admin@example.test", "password": "safe-password-for-tests"}
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return settings, store, client, project
