"""OGC-shaped subset executes the same frozen science; never claims full conformance."""

import json
from pathlib import Path

import pytest
import yaml
from coastmas_next.app import create_app
from coastmas_next.worker import Worker
from fastapi.testclient import TestClient
from jsonschema import Draft7Validator, FormatChecker
from referencing import Registry, Resource

ROOT = "/api/ogc/1.0"
SCHEMAS = Path(__file__).parent / "fixtures" / "ogc-processes-1.0"
BASE = "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/"


def validate(name, instance):
    registry = Registry()
    for path in SCHEMAS.glob("*.yaml"):
        value = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            **yaml.safe_load(path.read_text()),
        }
        registry = registry.with_resource(BASE + path.name, Resource.from_contents(value))
    Draft7Validator(
        {"$ref": BASE + name}, registry=registry, format_checker=FormatChecker()
    ).validate(instance)


def ready(client, project):
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Actual OGC entities", "purpose": "entities"},
    ).json()
    content = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "001",
                "properties": {"value": 0},
                "geometry": {"type": "Point", "coordinates": [110, 23]},
            }
        ],
    }
    reply = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("units.geojson", json.dumps(content).encode())},
        data={"task_id": task["id"], "expected_revision": 1},
    )
    assert reply.status_code == 201, reply.text
    return reply.json()["task"]


def body(task):
    return {
        "inputs": {
            "task": {
                "value": {"id": task["id"], "revision": task["revision"]},
                "mediaType": "application/json",
            }
        },
        "response": "document",
        "outputs": {
            "result": {"transmissionMode": "reference", "format": {"mediaType": "application/json"}}
        },
    }


def test_discovery_official_schemas_and_actual_native_equivalence(workspace):
    _, store, client, project = workspace
    landing = client.get(ROOT + "/").json()
    validate("landingPage.yaml", landing)
    conformance = client.get(ROOT + "/conformance").json()
    validate("confClasses.yaml", conformance)
    assert conformance["conformsTo"] == []  # full Core ATS is not falsely claimed
    assert landing["profile"]["status"] == "implemented_subset"
    listing = client.get(ROOT + "/processes?limit=2").json()
    validate("processList.yaml", listing)
    assert len(listing["processes"]) == 2
    assert any(link["rel"] == "next" for link in listing["links"])
    description = client.get(ROOT + "/processes/entities").json()
    validate("process.yaml", description)
    assert description["jobControlOptions"] == ["async-execute"]
    task = ready(client, project)
    payload = body(task)
    validate("execute.yaml", payload)
    response = client.post(
        ROOT + "/processes/entities/execution", json=payload, headers={"Prefer": "respond-async"}
    )
    assert response.status_code == 201, response.text
    validate("statusInfo.yaml", response.json())
    assert response.json()["status"] == "accepted"
    location = response.headers["Location"]
    assert client.get(location).json()["jobID"] == response.json()["jobID"]
    assert (
        client.post(ROOT + "/processes/entities/execution", json=payload).json()["jobID"]
        == response.json()["jobID"]
    )
    assert client.get(location + "/results").status_code == 404
    assert Worker(store).run_once()
    done = client.get(location).json()
    validate("statusInfo.yaml", done)
    assert done["status"] == "successful"
    result = client.get(location + "/results").json()
    validate("results.yaml", result)
    actual = client.get(result["result"]["href"]).json()
    native = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "native-equivalent"},
    ).json()
    assert Worker(store).run_once()
    reference = client.get(f"/api/jobs/{native['id']}/result").json()
    assert actual["data"] == reference["data"]
    assert actual["manifest"] == reference["manifest"]
    assert actual["data"]["features"][0]["properties"]["value"] == 0
    listing = client.get(ROOT + "/jobs?limit=1").json()
    validate("jobList.yaml", listing)
    assert len(listing["jobs"]) == 1
    assert any(link["rel"] == "next" for link in listing["links"])
    assert client.delete(location).status_code == 409  # immutable completed result retained


def test_permission_preflight_failure_and_real_cancellation(workspace):
    settings, store, client, project = workspace
    task = ready(client, project)
    viewer = TestClient(create_app(settings))
    login = viewer.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    ).json()
    viewer.headers["X-CSRF-Token"] = login["csrf"]
    assert viewer.post(ROOT + "/processes/entities/execution", json=body(task)).status_code == 403
    response = client.post(ROOT + "/processes/entities/execution", json=body(task))
    location = response.headers["Location"]
    assert viewer.delete(location).status_code == 403
    assert client.delete(location).json()["status"] == "dismissed"
    assert not Worker(store).run_once()
    assert client.get(location + "/results").status_code == 410
    # A second actual job fails when its frozen input bytes change.
    rerun = client.post(
        ROOT + "/processes/entities/execution",
        json=body(task),
        headers={"Idempotency-Key": "integrity-failure"},
    )
    source = client.get(f"/api/tasks/{task['id']}").json()["draft"]["selection"][0]["asset_id"]
    asset = client.get(f"/api/assets/{source}").json()
    (settings.storage_root / asset["object_key"]).write_bytes(b"tampered isolated fixture")
    assert Worker(store).run_once()
    failed = client.get(rerun.headers["Location"]).json()
    assert failed["status"] == "failed"
    failure = client.get(rerun.headers["Location"] + "/results")
    assert failure.status_code == 500
    validate("exception.yaml", failure.json())
    assert failure.json()["type"].endswith("INPUT_INTEGRITY")
    # Other projects and anonymous sessions never leak jobs.
    outsider = store.create_account("outside@example.test", "outside-safe-password")
    store.create_project(outsider, "Unrelated isolated project")
    other = TestClient(create_app(settings))
    other.post(
        "/api/session", json={"email": "outside@example.test", "password": "outside-safe-password"}
    )
    assert other.get(ROOT + "/jobs").json()["jobs"] == []
    assert other.get(location).status_code == 404
    assert TestClient(create_app(settings)).get(ROOT + "/processes").status_code == 401


@pytest.mark.parametrize(
    "change",
    [
        {"subscriber": {"successUri": "http://127.0.0.1/private"}},
        {"response": "raw"},
        {"outputs": {"result": {"transmissionMode": "value"}}},
        {"inputs": {"task": {"href": "http://127.0.0.1/private"}, "revision": 1}},
        {"inputs": {"task": {"value": {"id": "missing", "revision": True}}}},
    ],
)
def test_unimplemented_extensions_rejected_before_job_creation(workspace, change):
    _, _, client, project = workspace
    task = ready(client, project)
    reply = client.post(ROOT + "/processes/entities/execution", json={**body(task), **change})
    assert reply.status_code == 400, reply.text
    validate("exception.yaml", reply.json())
    assert client.get(f"/api/tasks/{task['id']}/jobs").json()["total"] == 0


def test_preflight_and_process_version_do_not_bypass_native_contract(workspace):
    _, _, client, project = workspace
    task = ready(client, project)
    assert client.post(ROOT + "/processes/assessment/execution", json=body(task)).status_code == 400
    assert client.get("/api/ogc/2.0/processes").status_code == 404
    assert client.get(ROOT + "/processes/workflow").status_code == 404
    assert client.get(ROOT + "/processes?unknown=1").status_code == 400
    empty = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Missing actual sources", "purpose": "entities"},
    ).json()
    blocked = client.post(ROOT + "/processes/entities/execution", json=body(empty))
    assert blocked.status_code == 422
    assert blocked.json()["type"].endswith("PREFLIGHT_BLOCKED")
    assert client.get(f"/api/tasks/{empty['id']}/jobs").json()["total"] == 0


def test_running_cancel_waits_for_worker_and_completion_race_preserves_result(
    workspace, monkeypatch
):
    import threading

    from coastmas_next.execution import Execution

    _, store, client, project = workspace
    task = ready(client, project)
    worker = Worker(store, lease_seconds=0.06)
    entered, release = threading.Event(), threading.Event()
    compute = worker.compute

    def bounded_compute(manifest, cancelled, artifact_dir=None):
        entered.set()
        assert release.wait(5)
        return compute(manifest, cancelled, artifact_dir)

    monkeypatch.setattr(worker, "compute", bounded_compute)
    response = client.post(ROOT + "/processes/entities/execution", json=body(task))
    thread = threading.Thread(target=worker.run_once)
    thread.start()
    try:
        assert entered.wait(5)
        cancelled = client.delete(response.headers["Location"])
        assert cancelled.status_code == 202
        assert cancelled.json()["status"] == "running"
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert client.get(response.headers["Location"]).json()["status"] == "dismissed"
    assert client.get(response.headers["Location"] + "/results").status_code == 410
    second = client.post(
        ROOT + "/processes/entities/execution", json=body(task), headers={"Idempotency-Key": "race"}
    )
    cancel = Execution.cancel

    def finish_before_cancel(self, actor, job_id):
        Worker(store).run_once()
        return cancel(self, actor, job_id)

    monkeypatch.setattr(Execution, "cancel", finish_before_cancel)
    assert client.delete(second.headers["Location"]).status_code == 409
    assert client.get(second.headers["Location"] + "/results").status_code == 200
