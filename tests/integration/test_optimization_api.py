"""Optimization configuration persists real input, runs a worker and publishes actual output."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from coastmas.domain.optimization_catalog import optimization_catalog
from coastmas.persistence.resources import create_resource
from coastmas.persistence.schema import ResourceDependency
from coastmas.worker.runtime import WorkflowWorker
from tests.factories import scene
from tests.unit.test_optimization_frame import optimization_input


def test_optimization_saved_inputs_workflow_worker_and_idempotent_results(
    authenticated, engine, storage, tmp_path
):
    client, csrf, project, user = authenticated
    catalog = optimization_catalog(project)
    client.app.state.registry = catalog.registry
    client.app.state.artifact_store = storage
    selected = scene(id=str(uuid4()))
    with Session(engine) as session, session.begin():
        for kind, spec in [("model", catalog.models[0]), ("scene", selected)]:
            create_resource(
                session,
                user_id=user,
                project_id=project,
                kind=kind,
                identifier=spec.id,
                name=spec.name,
                spec=spec.model_dump(mode="json"),
            )
    headers = {"X-CSRF-Token": csrf}
    body = {
        "project_id": project,
        "name": "SYNTHETIC optimization record",
        "scene": {"id": selected.id, "version": 1},
        "frame": optimization_input(),
        "time_limit": 5,
        "idempotency_key": str(uuid4()),
    }
    response = client.post("/api/v1/optimizations", headers=headers, json=body)
    assert response.status_code == 201, response.text
    record = response.json()["spec"]
    base = "/api/v1/optimizations/" + record["id"]
    assert record["source_scene"] == body["scene"]
    assert record["scene"]["id"] != selected.id
    assert (
        client.post("/api/v1/optimizations", headers=headers, json=body).json() == response.json()
    )
    assert (
        client.post(
            "/api/v1/optimizations", headers=headers, json={**body, "time_limit": 6}
        ).status_code
        == 409
    )
    original = client.get("/api/v1/scenes/" + selected.id).json()["spec"]
    assert original == selected.model_dump(mode="json")
    assert client.get(base + "/input").json()["units"][0]["benefit"] == 1000000
    downloaded = client.get("/api/v1/data-assets/" + record["data"]["id"] + "/download")
    assert downloaded.status_code == 200
    assert downloaded.json()["candidates"] == optimization_input()
    selection = {
        "workflow_version": 1,
        "scene_id": record["scene"]["id"],
        "scene_version": 1,
        "random_seed": 42,
    }
    validation = client.post(
        "/api/v1/workflows/" + record["workflow"]["id"] + "/validate",
        headers=headers,
        json=selection,
    )
    assert validation.status_code == 200 and validation.json()["valid"], validation.text
    run_headers = {**headers, "Idempotency-Key": str(uuid4())}
    queued = client.post(
        base + "/run", headers=run_headers, json={"optimization_version": 1, "random_seed": 42}
    )
    assert queued.status_code == 202, queued.text
    job = queued.json()["id"]
    assert (
        client.post(
            base + "/run", headers=run_headers, json={"optimization_version": 1, "random_seed": 42}
        ).json()["id"]
        == job
    )
    WorkflowWorker(engine, catalog.registry, storage, work_root=tmp_path).run(job)
    runs = client.get(base + "/runs").json()
    assert runs[0]["job"]["status"] == "SUCCEEDED", runs
    result = client.get("/api/v1/results/" + runs[0]["result_id"] + "/content").json()
    assert result["outputs"]["optimize.allocation"]["selected"] == ["b"]
    assert result["outputs"]["optimize.allocation"]["totals"]["area"] == 20000
    assert result["run_manifest"]["scene"]["id"] == record["scene"]["id"]
    assert result["result_view"]["binding_status"] == "UNBOUND"
    with Session(engine) as session:
        dependencies = session.scalars(
            select(ResourceDependency).where(ResourceDependency.source_id == record["id"])
        ).all()
        assert {item.target_id for item in dependencies} == {
            record[key]["id"] for key in ("data", "scene", "source_scene", "workflow")
        }
    archived = client.delete("/api/v1/scenes/" + selected.id, headers=headers)
    assert archived.status_code == 409

    unused = scene(id=str(uuid4()))
    created = client.post(
        "/api/v1/scenes",
        headers=headers,
        json={"project_id": project, "spec": unused.model_dump(mode="json")},
    )
    assert created.status_code == 201
    assert client.delete("/api/v1/scenes/" + unused.id, headers=headers).status_code == 204
    assert client.delete("/api/v1/scenes/" + unused.id, headers=headers).status_code == 204
