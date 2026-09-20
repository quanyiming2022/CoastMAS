from pathlib import Path

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from coastmas.persistence.schema import Resource
from coastmas.sample_bootstrap import seed_project
from coastmas.worker.runtime import WorkflowWorker


def test_seed_is_repeatable_preserves_user_state_and_three_scenes_run(
    engine,
    actors,
    storage,
    authenticated,
    tmp_path,
):
    owner, _, _, project = actors
    client, csrf, _, _ = authenticated
    with Session(engine) as session, session.begin():
        seeded = seed_project(session, owner, project, storage, Path("sample-data"))
        count = session.scalar(select(func.count()).select_from(Resource))
    with Session(engine) as session, session.begin():
        again = seed_project(session, owner, project, storage, Path("sample-data"))
        assert len(again.catalog.models) == 8
        assert len(again.scenes) == len(again.workflows) == 3
        assert session.scalar(select(func.count()).select_from(Resource)) == count
    client.app.state.registry = seeded.catalog.registry
    client.app.state.artifact_store = storage
    worker = WorkflowWorker(engine, seeded.catalog.registry, storage, work_root=tmp_path)
    for label, workflow in seeded.workflows.items():
        scene = seeded.scenes[label]
        response = client.post(
            "/api/v1/workflows/" + workflow.id + "/run",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": "seed-" + label},
            json={
                "workflow_version": 1,
                "scene_id": scene.id,
                "scene_version": 1,
            },
        )
        assert response.status_code == 202, response.text
        worker.run(response.json()["id"])
        assert client.get("/api/v1/jobs/" + response.json()["id"]).json()["status"] == "SUCCEEDED"
    results = client.get("/api/v1/results", params={"project_id": project}).json()
    assert len(results) == 3
    contents = [
        client.get("/api/v1/results/" + item["id"] + "/content").json()["outputs"]
        for item in results
    ]
    coastal = next(item for item in contents if "statistics.statistics" in item)
    assert coastal["statistics.statistics"]["estimated_affected_population"] == 320
    assert coastal["statistics.statistics"]["inundated_area_m2"] == 80000
    temporal = next(item for item in contents if "change.change" in item)
    np.testing.assert_allclose(temporal["change.change"]["trend"], [0.1] * 4, rtol=0, atol=1e-12)
    with Session(engine) as session, session.begin():
        record = session.get(Resource, seeded.scenes["B"].id)
        record.enabled = False
    with Session(engine) as session, session.begin():
        seed_project(session, owner, project, storage, Path("sample-data"))
        assert session.get(Resource, seeded.scenes["B"].id).enabled is False


def test_initial_account_is_idempotent_and_never_resets_password(engine):
    from uuid import uuid4

    from coastmas.persistence.auth import HASHER
    from coastmas.persistence.schema import User
    from coastmas.runtime_bootstrap import initialize_account

    email = uuid4().hex + "@bootstrap.test.invalid"
    with Session(engine) as session, session.begin():
        owner, project = initialize_account(session, email, "initial-test-password", str(uuid4()))
    with Session(engine) as session, session.begin():
        repeated, same_project = initialize_account(
            session, email, "different-test-password", project
        )
        assert (repeated, same_project) == (owner, project)
        assert HASHER.verify(session.get(User, owner).password_hash, "initial-test-password")
