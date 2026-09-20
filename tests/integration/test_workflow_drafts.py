from copy import deepcopy
from uuid import uuid4

from sqlalchemy.orm import Session

from coastmas.core.execution import ExecutionRegistry
from coastmas.persistence.schema import Resource
from tests.integration.test_run_api import setup_run


def test_draft_preflight_checks_unsaved_science_and_never_persists_or_submits(
    authenticated, engine, actors, storage, tmp_path
):
    client, csrf, project, _ = authenticated
    _, identifier, selection = setup_run(engine, actors, storage, tmp_path, client)
    workflow = client.get("/api/v1/workflows/" + identifier).json()["spec"]
    draft_id = "draft-" + uuid4().hex
    workflow = {**workflow, "id": draft_id, "version": 1}
    body = {
        "project_id": project,
        "workflow": workflow,
        "scene": {"id": selection["scene_id"], "version": selection["scene_version"]},
        "random_seed": 42,
    }
    headers = {"X-CSRF-Token": csrf}
    before = client.get("/api/v1/jobs", params={"project_id": project}).json()
    response = client.post("/api/v1/workflow-drafts/validate", headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["valid"] is True
    assert response.json()["bindings"][0]["status"] == "VALIDATED"
    with Session(engine) as session:
        assert session.get(Resource, draft_id) is None
    assert client.get("/api/v1/jobs", params={"project_id": project}).json() == before
    missing = deepcopy(body)
    missing["workflow"]["nodes"][0]["parameters"] = {}
    blocked = client.post("/api/v1/workflow-drafts/validate", headers=headers, json=missing)
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["valid"] is False
    assert any(issue["node_id"] == "screen-node" for issue in blocked.json()["issues"])
    denied = client.post(
        "/api/v1/workflow-drafts/validate",
        headers=headers,
        json={**body, "project_id": str(uuid4())},
    )
    assert denied.status_code == 403


def test_draft_and_saved_preflight_expose_unregistered_runtime_before_run(
    authenticated, engine, actors, storage, tmp_path
):
    client, csrf, project, _ = authenticated
    _, identifier, selection = setup_run(engine, actors, storage, tmp_path, client)
    workflow = client.get("/api/v1/workflows/" + identifier).json()["spec"]
    client.app.state.registry = ExecutionRegistry()
    headers = {"X-CSRF-Token": csrf}
    draft = client.post(
        "/api/v1/workflow-drafts/validate",
        headers=headers,
        json={
            "project_id": project,
            "workflow": workflow,
            "scene": {"id": selection["scene_id"], "version": selection["scene_version"]},
        },
    )
    saved = client.post(
        "/api/v1/workflows/" + identifier + "/validate", headers=headers, json=selection
    )
    for response in (draft, saved):
        assert response.status_code == 200, response.text
        assert response.json()["valid"] is False
        assert any(
            issue["code"] == "MODEL_ERROR" and issue["node_id"] == "screen-node"
            for issue in response.json()["issues"]
        )
