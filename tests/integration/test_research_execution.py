from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from coastmas.persistence.schema import Membership, ResultBundle
from coastmas.sample_bootstrap import seed_project
from coastmas.worker.runtime import WorkflowWorker


def setup_research(engine, actors, storage, authenticated):
    owner, _, _, project = actors
    client, csrf, _, _ = authenticated
    with Session(engine) as session, session.begin():
        seeded = seed_project(session, owner, project, storage, Path("sample-data"))
    client.app.state.registry = seeded.catalog.registry
    client.app.state.artifact_store = storage
    workflow = seeded.workflows["B"]
    scene = seeded.scenes["B"]
    models = sorted({(n.model_id, n.model_version) for n in workflow.nodes})
    assets = sorted({(b.source.id, b.source.version) for b in workflow.input_bindings})
    body = {
        "project_id": project,
        "cases": [
            {
                "id": "fixed-assessment",
                "goal": "可持续性评价：等权综合评价",
                "scene": {"id": scene.id, "version": 1},
                "models": [{"id": i, "version": v} for i, v in models],
                "assets": [{"id": i, "version": v} for i, v in assets],
            }
        ],
        "experiments": ["A", "B", "C"],
        "repetitions": 1,
        "allow_provider": False,
    }
    return client, csrf, seeded, body


def test_research_job_publishes_partial_report_without_fake_external_success(
    engine, actors, storage, authenticated, tmp_path
):
    client, csrf, seeded, body = setup_research(engine, actors, storage, authenticated)
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": "research-fixed"}
    response = client.post("/api/v1/research", json=body, headers=headers)
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    assert client.post("/api/v1/research", json=body, headers=headers).json()["id"] == job_id
    worker = WorkflowWorker(engine, seeded.catalog.registry, storage, work_root=tmp_path)
    worker.run(job_id)
    worker.run(job_id)
    job = client.get("/api/v1/jobs/" + job_id).json()
    assert job["status"] == "SUCCEEDED", job
    report = client.get("/api/v1/research/" + job_id + "/report")
    assert report.status_code == 200, report.text
    data = report.json()
    assert data["report"]["status"] == "PARTIAL"
    assert data["report"]["trials"][0]["observation"]["workflow_valid"] is True
    assert [r["observation"]["status"] for r in data["report"]["trials"]] == [
        "EVALUATED",
        "BLOCKED",
        "BLOCKED",
    ]
    assert data["provider_requests"] == 0
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count()).select_from(ResultBundle).where(ResultBundle.job_id == job_id)
            )
            == 1
        )
    changed = body | {"repetitions": 2}
    assert client.post("/api/v1/research", json=changed, headers=headers).status_code == 409


def test_research_rechecks_current_access_before_worker_runs(
    engine, actors, storage, authenticated, tmp_path
):
    client, csrf, seeded, body = setup_research(engine, actors, storage, authenticated)
    response = client.post(
        "/api/v1/research", json=body, headers={"X-CSRF-Token": csrf, "Idempotency-Key": "revoked"}
    )
    assert response.status_code == 202, response.text
    with Session(engine) as session, session.begin():
        session.get(Membership, (actors[3], actors[0])).role = "VIEWER"
    worker = WorkflowWorker(engine, seeded.catalog.registry, storage, work_root=tmp_path)
    worker.run(response.json()["id"])
    job = client.get("/api/v1/jobs/" + response.json()["id"]).json()
    assert job["status"] == "FAILED"
    assert job["error"]["error_code"] == "AUTHORIZATION_ERROR"
    assert client.get("/api/v1/research/" + job["id"] + "/report").status_code == 409


def test_cancelled_research_retries_same_frozen_evaluation_identity(
    engine, actors, storage, authenticated, tmp_path
):
    client, csrf, seeded, body = setup_research(engine, actors, storage, authenticated)
    response = client.post(
        "/api/v1/research",
        json=body,
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "cancelled-research"},
    )
    assert response.status_code == 202, response.text
    original = response.json()
    cancelled = client.post(
        "/api/v1/jobs/" + original["id"] + "/cancel", headers={"X-CSRF-Token": csrf}
    )
    assert cancelled.status_code == 200
    worker = WorkflowWorker(engine, seeded.catalog.registry, storage, work_root=tmp_path)
    worker.run(original["id"])
    assert client.get("/api/v1/jobs/" + original["id"]).json()["status"] == "CANCELLED"
    retry = client.post(
        "/api/v1/jobs/" + original["id"] + "/retry",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "research-retry"},
    )
    assert retry.status_code == 202, retry.text
    assert retry.json()["manifest"] == original["manifest"]
    worker.run(retry.json()["id"])
    assert client.get("/api/v1/jobs/" + retry.json()["id"]).json()["status"] == "SUCCEEDED"
