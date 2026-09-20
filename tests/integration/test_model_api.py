from uuid import uuid4

from tests.factories import model


def test_model_import_export_copy_history_and_archive(authenticated):
    client, csrf, project, user = authenticated
    headers = {"X-CSRF-Token": csrf}
    original = model(id=uuid4().hex)
    response = client.post(
        "/api/v1/models/import",
        headers=headers,
        json={"project_id": project, "format": "json", "content": original.model_dump_json()},
    )
    assert response.status_code == 201, response.text
    identifier = response.json()["resource_id"]
    assert response.json()["spec"]["validation_status"] == "UNVALIDATED"
    assert response.json()["spec"]["execution_status"] == "NOT_EXECUTABLE"
    exported = client.get(f"/api/v1/models/{identifier}/export", params={"format": "yaml"})
    assert exported.status_code == 200
    assert "scientific_domain:" in exported.text
    clone = client.post(
        f"/api/v1/models/{identifier}/copy", headers=headers, json={"name": "Copy model"}
    )
    assert clone.status_code == 201, clone.text
    assert clone.json()["resource_id"] != identifier
    response = client.post(
        f"/api/v1/models/{identifier}/enabled",
        headers=headers,
        json={"expected_version": 1, "enabled": False},
    )
    assert response.status_code == 200, response.text
    history = client.get(f"/api/v1/models/{identifier}/versions")
    assert [item["version"] for item in history.json()] == [1, 2]
    assert (
        client.get(f"/api/v1/models/{identifier}", params={"version": 1}).json()["spec"]["enabled"]
        is True
    )
    removed = client.delete(f"/api/v1/models/{identifier}", headers=headers)
    assert removed.status_code == 204, removed.text
    listed = client.get("/api/v1/models", params={"project_id": project}).json()
    assert identifier not in {item["id"] for item in listed}
    assert client.get(f"/api/v1/models/{identifier}", params={"version": 1}).status_code == 200


def test_metadata_create_cannot_self_certify_execution(authenticated):
    client, csrf, project, _ = authenticated
    response = client.post(
        "/api/v1/models",
        headers={"X-CSRF-Token": csrf},
        json={"project_id": project, "spec": model(id=uuid4().hex).model_dump(mode="json")},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "MODEL_REGISTRATION_REQUIRED"


def test_model_decomposition_is_available_without_executing_upload(authenticated):
    client, csrf, _, _ = authenticated
    response = client.post(
        "/api/v1/models/decompose",
        headers={"X-CSRF-Token": csrf},
        json={"kind": "python", "name": "example", "source": "def compute(x):\n    return x*2"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["executable"] is False
    assert response.json()["components"][0]["id"] == "compute"


def test_model_search_filters_literal_names_and_current_enable_state(authenticated):
    client, csrf, project, _ = authenticated
    headers = {"X-CSRF-Token": csrf}
    identifiers = []
    for name, capability, enabled in [
        ("coast_100%", "screen", True),
        ("coastX100other", "screen", False),
        ("coast_100% other", "assess", True),
    ]:
        source = model(id=uuid4().hex, name=name, capabilities=[capability], enabled=enabled)
        response = client.post(
            "/api/v1/models/import",
            headers=headers,
            json={"project_id": project, "format": "json", "content": source.model_dump_json()},
        )
        assert response.status_code == 201, response.text
        identifiers.append(source.id)
    response = client.get(
        "/api/v1/models/search",
        params={
            "project_id": project,
            "q": "coast_100%",
            "capability": "screen",
            "enabled": True,
        },
    )
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()] == identifiers[:1]
    assert response.headers["X-Total-Count"] == "1"
    response = client.get(
        "/api/v1/models/search",
        params={
            "project_id": project,
            "enabled": False,
        },
    )
    assert [item["id"] for item in response.json()] == identifiers[1:2]
    response = client.post(
        f"/api/v1/models/{identifiers[0]}/enabled",
        headers=headers,
        json={"expected_version": 1, "enabled": False},
    )
    assert response.status_code == 200, response.text
    response = client.get(
        "/api/v1/models/search",
        params={
            "project_id": project,
            "capability": "screen",
            "enabled": True,
        },
    )
    assert response.json() == []


def test_matching_endpoint_uses_registered_versions_and_rejects_unvalidated_models(authenticated):
    from tests.factories import scene

    client, csrf, project, _ = authenticated
    headers = {"X-CSRF-Token": csrf}
    source = model(id=uuid4().hex)
    imported = client.post(
        "/api/v1/models/import",
        headers=headers,
        json={
            "project_id": project,
            "format": "json",
            "content": source.model_dump_json(),
        },
    )
    assert imported.status_code == 201, imported.text
    context = scene(id=uuid4().hex)
    created = client.post(
        "/api/v1/scenes",
        headers=headers,
        json={
            "project_id": project,
            "spec": context.model_dump(mode="json"),
        },
    )
    assert created.status_code == 201, created.text
    response = client.post(
        "/api/v1/models/match",
        headers=headers,
        json={
            "project_id": project,
            "scene_id": context.id,
            "scene_version": 1,
            "capability": "screen",
            "parameters": {"increment": 0.5},
            "preferences": {source.id: 1},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["ranked"] == []
    rejection = response.json()["rejected"][0]
    assert rejection["model_id"] == source.id
    assert rejection["score"] is None
    assert "MODEL_UNVALIDATED" in {item["code"] for item in rejection["issues"]}
    response = client.post(
        "/api/v1/models/match",
        headers=headers,
        json={
            "project_id": uuid4().hex,
            "scene_id": context.id,
            "scene_version": 1,
            "capability": "screen",
            "parameters": {},
        },
    )
    assert response.status_code == 403
