from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from coastmas.core.contracts import RunManifest
from coastmas.persistence.resources import create_resource
from coastmas.persistence.schema import Job, ResourceDependency
from tests.factories import scene
from tests.integration.test_run_api import setup_run
from tests.unit.test_geography import entity_payload


def test_scene_draft_coverage_and_saved_references_enforce_project_and_version(
    authenticated, engine
):
    client, csrf, project, _ = authenticated
    headers = {"X-CSRF-Token": csrf}
    entity = {**entity_payload(), "id": "entity-" + uuid4().hex}
    assert (
        client.post(
            "/api/v1/entities", headers=headers, json={"project_id": project, "spec": entity}
        ).status_code
        == 201
    )
    spec = scene(
        id="scene-" + uuid4().hex,
        study_area=entity["geometry"],
        data_policy={"study_area_crs": entity["crs"]},
        entity_references=[{"id": entity["id"], "version": 1}],
    ).model_dump(mode="json")
    response = client.post(
        "/api/v1/scene-drafts/inspect", headers=headers, json={"project_id": project, "scene": spec}
    )
    assert response.status_code == 200, response.text
    assert response.json()["entity_coverage"][0]["status"] == "COVERED"
    assert client.get("/api/v1/scenes/" + spec["id"]).status_code == 404
    created = client.post(
        "/api/v1/scenes", headers=headers, json={"project_id": project, "spec": spec}
    )
    assert created.status_code == 201, created.text
    with Session(engine) as session:
        reference = session.scalar(
            select(ResourceDependency).where(ResourceDependency.source_id == spec["id"])
        )
        assert reference.target_id == entity["id"]
        assert reference.target_version == 1
    unavailable = deepcopy(spec)
    unavailable["id"] = "scene-" + uuid4().hex
    unavailable["entity_references"][0]["version"] = 99
    invalid = client.post(
        "/api/v1/scenes", headers=headers, json={"project_id": project, "spec": unavailable}
    )
    assert invalid.status_code == 409, invalid.text
    denied = client.post(
        "/api/v1/scene-drafts/inspect",
        headers=headers,
        json={"project_id": str(uuid4()), "scene": spec},
    )
    assert denied.status_code == 403


def test_worker_accepts_verified_legacy_scene_with_absent_optional_reference_fields(
    authenticated, engine, actors, storage, tmp_path
):
    client, csrf, project, user = authenticated
    runner, workflow_id, selection = setup_run(engine, actors, storage, tmp_path, client)
    legacy = client.get("/api/v1/scenes/" + selection["scene_id"]).json()["spec"]
    legacy["id"] = "legacy-" + uuid4().hex
    legacy.pop("entity_references", None)
    legacy.pop("data_references", None)
    with Session(engine) as session, session.begin():
        create_resource(
            session,
            user_id=user,
            project_id=project,
            kind="scene",
            identifier=legacy["id"],
            name=legacy["name"],
            spec=legacy,
        )
    response = client.post(
        "/api/v1/workflows/" + workflow_id + "/run",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": uuid4().hex},
        json={**selection, "scene_id": legacy["id"]},
    )
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    with Session(engine) as session:
        job = session.get(Job, identifier)
        runner._verify_manifest(session, job, RunManifest.model_validate(job.manifest))
    runner.run(identifier)
    assert client.get("/api/v1/jobs/" + identifier).json()["status"] == "SUCCEEDED"


def test_scene_entity_revocation_is_checked_at_submission_and_worker(
    authenticated, engine, actors, storage, tmp_path
):
    from coastmas.persistence.schema import Resource

    client, csrf, project, _ = authenticated
    runner, workflow_id, selection = setup_run(engine, actors, storage, tmp_path, client)
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": uuid4().hex}
    original = client.get("/api/v1/scenes/" + selection["scene_id"]).json()["spec"]
    entity = {
        **entity_payload(),
        "id": "selected-" + uuid4().hex,
        "crs": "EPSG:32650",
        "geometry": original["study_area"],
    }
    assert (
        client.post(
            "/api/v1/entities", headers=headers, json={"project_id": project, "spec": entity}
        ).status_code
        == 201
    )
    changed = {
        **original,
        "version": 2,
        "data_policy": {"study_area_crs": "EPSG:32650"},
        "entity_references": [{"id": entity["id"], "version": 1}],
    }
    assert (
        client.put(
            "/api/v1/scenes/" + original["id"],
            headers=headers,
            json={"expected_version": 1, "spec": changed},
        ).status_code
        == 200
    )
    selection["scene_version"] = 2
    response = client.post(
        "/api/v1/workflows/" + workflow_id + "/run", headers=headers, json=selection
    )
    assert response.status_code == 202, response.text
    with Session(engine) as session, session.begin():
        session.get(Resource, entity["id"]).enabled = False
    rejected = client.post(
        "/api/v1/workflows/" + workflow_id + "/validate", headers=headers, json=selection
    )
    assert rejected.status_code == 403, rejected.text
    runner.run(response.json()["id"])
    assert client.get("/api/v1/jobs/" + response.json()["id"]).json()["status"] == "FAILED"
