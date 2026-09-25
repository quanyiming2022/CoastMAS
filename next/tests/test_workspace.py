"""New contracts: durable drafts, optimistic concurrency and project authorization."""

import pytest
from coastmas_next.app import create_app
from coastmas_next.config import Settings
from fastapi.testclient import TestClient


def test_server_acknowledged_draft_survives_new_process_and_browser(workspace):
    settings, _, client, project = workspace
    saved = client.post(
        "/api/tasks", json={"project_id": project, "title": "2022 shoreline", "purpose": "cluster"}
    )
    assert saved.status_code == 201, saved.text
    task = saved.json()
    changed = client.put(
        f"/api/tasks/{task['id']}",
        json={
            "expected_revision": 1,
            "draft": {
                "title": "Known input preserved",
                "purpose": "cluster",
                "selection": [],
                "mapping": [],
                "options": {},
            },
        },
    )
    assert changed.status_code == 200, changed.text
    browser = TestClient(create_app(settings))
    login = browser.post(
        "/api/session", json={"email": "admin@example.test", "password": "safe-password-for-tests"}
    )
    assert login.status_code == 200
    restored = browser.get(f"/api/tasks/{task['id']}").json()
    assert restored["draft"]["title"] == "Known input preserved"
    assert restored["revision"] == 2
    assert len(browser.get(f"/api/tasks/{task['id']}/history").json()) == 2


def test_conflicting_save_cannot_replace_newer_draft(workspace):
    _, _, client, project = workspace
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "A", "purpose": "inspect"}
    ).json()
    patch = {"expected_revision": 1, "draft": {"title": "B", "purpose": "inspect"}}
    assert client.put(f"/api/tasks/{task['id']}", json=patch).status_code == 200
    patch["draft"]["title"] = "stale overwrite"
    conflict = client.put(f"/api/tasks/{task['id']}", json=patch)
    assert conflict.status_code == 409
    assert client.get(f"/api/tasks/{task['id']}").json()["draft"]["title"] == "B"


def test_project_boundaries_and_csrf_are_enforced(workspace):
    settings, store, client, project = workspace
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "Secret", "purpose": "inspect"}
    ).json()
    other = TestClient(create_app(settings))
    login = other.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    ).json()
    other.headers["X-CSRF-Token"] = login["csrf"]
    assert other.get(f"/api/tasks/{task['id']}").status_code == 200
    assert (
        other.put(
            f"/api/tasks/{task['id']}",
            json={"expected_revision": 1, "draft": {"title": "bad", "purpose": "inspect"}},
        ).status_code
        == 403
    )
    outsider = store.create_account("outside@example.test", "safe-password-for-tests")
    outside_project = store.create_project(outsider, "Outside")
    assert client.get(f"/api/projects/{outside_project}/tasks").status_code == 404
    del client.headers["X-CSRF-Token"]
    assert (
        client.post(
            "/api/tasks", json={"project_id": project, "title": "No CSRF", "purpose": "inspect"}
        ).status_code
        == 403
    )


def test_secret_fields_and_unbounded_values_do_not_enter_draft(workspace):
    _, _, client, project = workspace
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "A", "purpose": "inspect"}
    ).json()
    bad = {
        "expected_revision": 1,
        "draft": {
            "title": "A",
            "purpose": "inspect",
            "options": {"credentials": {"password": "do not persist"}},
        },
    }
    assert client.put(f"/api/tasks/{task['id']}", json=bad).status_code == 422
    assert client.get(f"/api/tasks/{task['id']}").json()["revision"] == 1


def test_legacy_database_name_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="coastmas_next_"):
        Settings(database_url="postgresql+psycopg://localhost/coastmas", storage_root=tmp_path)
