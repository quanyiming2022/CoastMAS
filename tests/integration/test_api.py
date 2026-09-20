from uuid import uuid4

from fastapi.testclient import TestClient

from coastmas.app.api import create_app


def test_authentication_and_csrf_are_required(engine, authenticated):
    client, csrf, project, user = authenticated
    with TestClient(create_app(engine)) as anonymous:
        assert anonymous.get("/api/v1/scenes", params={"project_id": project}).status_code == 401
    response = client.post("/api/v1/scenes", json={"project_id": project, "spec": {}})
    assert response.status_code == 403
    assert response.json()["error_code"] == "CSRF_ERROR"


def test_scene_api_persists_version_and_rejects_project_escape(authenticated):
    client, csrf, project, user = authenticated
    identifier = str(uuid4())
    spec = {
        "id": identifier,
        "name": "API scenario",
        "version": 1,
        "management_goal": "screen",
        "study_area": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        "entity_types": ["management_unit"],
        "time_range": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
        "scenario_conditions": {"vertical_datum": "demo"},
        "constraints": [],
        "required_outputs": ["inundation"],
        "data_policy": {},
        "quality_requirements": {},
    }
    response = client.post(
        "/api/v1/scenes", headers={"X-CSRF-Token": csrf}, json={"project_id": project, "spec": spec}
    )
    assert response.status_code == 201, response.text
    fetched = client.get(f"/api/v1/scenes/{identifier}")
    assert fetched.status_code == 200
    assert fetched.json()["spec"]["management_goal"] == "screen"
    changed = dict(spec, name="Updated", version=2)
    response = client.put(
        f"/api/v1/scenes/{identifier}",
        headers={"X-CSRF-Token": csrf},
        json={"expected_version": 1, "spec": changed},
    )
    assert response.status_code == 200
    assert (
        client.get(f"/api/v1/scenes/{identifier}", params={"version": 1}).json()["spec"]["name"]
        == "API scenario"
    )
    assert client.get("/api/v1/scenes", params={"project_id": str(uuid4())}).status_code == 403


def test_logout_revokes_cookie_and_errors_do_not_echo_password(authenticated):
    client, csrf, project, user = authenticated
    response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 204
    assert client.get("/api/v1/scenes", params={"project_id": project}).status_code == 401
    secret = "DO_NOT_ECHO_THIS_PASSWORD"
    response = client.post(
        "/api/v1/auth/login", json={"email": "unknown@test.invalid", "password": secret}
    )
    assert response.status_code == 401
    assert secret not in response.text
