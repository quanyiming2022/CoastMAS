from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from coastmas.persistence.resources import create_resource
from coastmas.runtime_bootstrap import BuiltinRuntimeRegistry
from tests.factories import scene
from tests.unit.test_temporal_adaptation import request as temporal_request


def test_temporal_preparation_freezes_versions_and_preserves_original_scene(
    authenticated, engine, storage
):
    client, csrf, project, user = authenticated
    client.app.state.artifact_store = storage
    client.app.state.registry = BuiltinRuntimeRegistry(Path("sample-data"))
    original = scene(id=str(uuid4()))
    with Session(engine) as session, session.begin():
        create_resource(
            session,
            user_id=user,
            project_id=project,
            kind="scene",
            identifier=original.id,
            name=original.name,
            spec=original.model_dump(mode="json"),
        )
    body = {
        "project_id": project,
        "name": "SYNTHETIC verification only",
        "scene": {"id": original.id, "version": 1},
        "source": "Hand calculated fixture",
        "license": "CC0",
        "request": temporal_request().model_dump(mode="json"),
        "idempotency_key": str(uuid4()),
    }
    headers = {"X-CSRF-Token": csrf}
    response = client.post("/api/v1/adaptations/temporal", json=body, headers=headers)
    assert response.status_code == 201, response.text
    frozen = response.json()
    assert client.post("/api/v1/adaptations/temporal", json=body, headers=headers).json() == frozen
    assert (
        client.post(
            "/api/v1/adaptations/temporal", json={**body, "name": "changed"}, headers=headers
        ).status_code
        == 409
    )
    assert client.get("/api/v1/scenes/" + original.id).json()["spec"] == original.model_dump(
        mode="json"
    )
    derived = client.get("/api/v1/scenes/" + frozen["scene"]["id"]).json()["spec"]
    assert derived["time_range"]["start"] == "2025-01-01T00:00:00Z"
    assert derived["data_references"] == [frozen["data"]]
    data = client.get("/api/v1/data-assets/" + frozen["data"]["id"]).json()["spec"]
    assert data["quality"]["temporal_method"] == "mean"
    selection = {"workflow_version": 1, "scene_id": frozen["scene"]["id"], "scene_version": 1}
    checked = client.post(
        "/api/v1/workflows/" + frozen["workflow"]["id"] + "/validate",
        json=selection,
        headers=headers,
    )
    assert checked.status_code == 200 and checked.json()["valid"], checked.text
    missing = {**body, "scene": {"id": str(uuid4()), "version": 1}, "idempotency_key": str(uuid4())}
    assert (
        client.post("/api/v1/adaptations/temporal", json=missing, headers=headers).status_code
        == 403
    )
    forbidden = {**body, "project_id": str(uuid4()), "idempotency_key": str(uuid4())}
    assert (
        client.post("/api/v1/adaptations/temporal", json=forbidden, headers=headers).status_code
        == 403
    )
    invalid = {
        **body,
        "request": {**body["request"], "method": "sum"},
        "idempotency_key": str(uuid4()),
    }
    assert (
        client.post("/api/v1/adaptations/temporal", json=invalid, headers=headers).status_code
        == 422
    )
