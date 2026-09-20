from uuid import uuid4

from sqlalchemy.orm import Session

from coastmas.persistence.schema import Resource
from tests.integration.test_worker import prepare_worker


def setup_run(engine, actors, storage, tmp_path, client):
    def add(inputs, parameters):
        return {"result": [value + parameters["increment"] for value in inputs["height"]]}

    runner, original = prepare_worker(engine, actors, storage, tmp_path, add)
    client.app.state.registry = runner.registry
    client.app.state.artifact_store = storage
    manifest = original.manifest
    request = {
        "workflow_version": manifest["workflow"]["version"],
        "scene_id": manifest["scene"]["id"],
        "scene_version": manifest["scene"]["version"],
        "random_seed": 42,
    }
    return runner, manifest["workflow"]["id"], request


def test_run_api_builds_manifest_and_publishes_real_result(
    authenticated, engine, actors, storage, tmp_path
):
    client, csrf, project, _ = authenticated
    runner, workflow_id, body = setup_run(engine, actors, storage, tmp_path, client)
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": uuid4().hex}
    preflight = client.post(f"/api/v1/workflows/{workflow_id}/validate", headers=headers, json=body)
    assert preflight.status_code == 200, preflight.text
    assert preflight.json()["valid"] is True
    response = client.post(f"/api/v1/workflows/{workflow_id}/run", headers=headers, json=body)
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "QUEUED"
    duplicate = client.post(f"/api/v1/workflows/{workflow_id}/run", headers=headers, json=body)
    assert duplicate.status_code == 202, duplicate.text
    assert duplicate.json()["id"] == job["id"]
    changed = client.post(
        f"/api/v1/workflows/{workflow_id}/run", headers=headers, json={**body, "random_seed": 43}
    )
    assert changed.status_code == 409
    runner.run(job["id"])
    assert client.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "SUCCEEDED"
    results = client.get("/api/v1/results", params={"project_id": project}).json()
    assert len(results) == 1
    result_id = results[0]["id"]
    result = client.get(f"/api/v1/results/{result_id}")
    assert result.status_code == 200, result.text
    assert result.json()["job_id"] == job["id"]
    provenance = client.get(f"/api/v1/results/{result_id}/provenance").json()
    assert provenance["workflow"]["id"] == workflow_id
    assert provenance["random_seed"] == 42
    content = client.get(f"/api/v1/results/{result_id}/content")
    assert content.status_code == 200, content.text
    assert content.json()["outputs"] == {"screen-node.result": [1.5, 2.5]}
    assert content.headers["Cache-Control"] == "no-store"


def test_run_api_blocks_disabled_input_and_supports_cancel_then_explicit_retry(
    authenticated, engine, actors, storage, tmp_path
):
    client, csrf, _, _ = authenticated
    runner, workflow_id, body = setup_run(engine, actors, storage, tmp_path, client)
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": uuid4().hex}
    with Session(engine) as session, session.begin():
        session.get(Resource, workflow_id).enabled = False
    response = client.post(f"/api/v1/workflows/{workflow_id}/run", headers=headers, json=body)
    assert response.status_code == 422
    with Session(engine) as session, session.begin():
        session.get(Resource, workflow_id).enabled = True
    response = client.post(f"/api/v1/workflows/{workflow_id}/run", headers=headers, json=body)
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    cancelled = client.post(f"/api/v1/jobs/{identifier}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    conflict = client.post(f"/api/v1/jobs/{identifier}/retry", headers=headers)
    assert conflict.status_code == 409, conflict.text
    retried = client.post(
        f"/api/v1/jobs/{identifier}/retry",
        headers={
            **headers,
            "Idempotency-Key": uuid4().hex,
        },
    )
    assert retried.status_code == 202, retried.text
    assert retried.json()["id"] != identifier
    runner.run(retried.json()["id"])
    assert client.get(f"/api/v1/jobs/{retried.json()['id']}").json()["status"] == "SUCCEEDED"


def test_run_api_does_not_accept_caller_manifest_or_unknown_runtime(
    authenticated, engine, actors, storage, tmp_path
):
    from coastmas.core.execution import ExecutionRegistry

    client, csrf, _, _ = authenticated
    _, workflow_id, body = setup_run(engine, actors, storage, tmp_path, client)
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": uuid4().hex}
    response = client.post(
        f"/api/v1/workflows/{workflow_id}/run", headers=headers, json={**body, "manifest": {}}
    )
    assert response.status_code == 422
    client.app.state.registry = ExecutionRegistry()
    response = client.post(f"/api/v1/workflows/{workflow_id}/run", headers=headers, json=body)
    assert response.status_code == 422
    assert response.json()["error_code"] == "MODEL_ERROR"


def test_concurrent_api_submissions_share_one_persisted_manifest(
    authenticated, engine, actors, storage, tmp_path
):
    from concurrent.futures import ThreadPoolExecutor

    client, csrf, _, _ = authenticated
    _, workflow_id, body = setup_run(engine, actors, storage, tmp_path, client)
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": uuid4().hex}

    def submit():
        return client.post(f"/api/v1/workflows/{workflow_id}/run", headers=headers, json=body)

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: submit(), range(4)))
    assert [item.status_code for item in responses] == [202] * 4
    assert len({item.json()["id"] for item in responses}) == 1
    assert len({item.json()["manifest"]["timestamp"] for item in responses}) == 1


def test_result_download_checks_bytes_and_current_permission(
    authenticated, engine, actors, storage, tmp_path
):
    from sqlalchemy import delete

    from coastmas.persistence.schema import Membership

    client, csrf, project, user = authenticated
    runner, workflow_id, body = setup_run(engine, actors, storage, tmp_path, client)
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": uuid4().hex}
    response = client.post(f"/api/v1/workflows/{workflow_id}/run", headers=headers, json=body)
    assert response.status_code == 202
    runner.run(response.json()["id"])
    result_id = client.get("/api/v1/results", params={"project_id": project}).json()[0]["id"]
    descriptor = client.get(f"/api/v1/results/{result_id}").json()["manifest"]
    # Deliberately corrupt only this test's private temporary bucket object.
    storage.client.put_object(Bucket=storage.bucket, Key=descriptor["key"], Body=b"{}")
    downloaded = client.get(f"/api/v1/results/{result_id}/content")
    assert downloaded.status_code == 422
    assert downloaded.json()["error_code"] == "CHECKSUM_ERROR"
    with Session(engine) as session, session.begin():
        session.execute(
            delete(Membership).where(Membership.project_id == project, Membership.user_id == user)
        )
    for path in [
        f"/api/v1/results/{result_id}",
        f"/api/v1/results/{result_id}/provenance",
        f"/api/v1/results/{result_id}/content",
    ]:
        assert client.get(path).status_code == 403
