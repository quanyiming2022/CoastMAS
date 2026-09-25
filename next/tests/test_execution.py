"""Real durable execution; response success is not sufficient evidence."""

import json

from coastmas_next.worker import Worker


def inspection_task(client, project):
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "Actual dataset", "purpose": "inspect"}
    ).json()
    uploaded = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("observations.csv", b"id,value\n001,0\n002,2\n")},
        data={"task_id": task["id"], "expected_revision": "1"},
    ).json()
    return uploaded["task"], uploaded["asset"]


def test_preflight_enqueue_real_worker_and_complete_download(workspace):
    settings, store, client, project = workspace
    task, asset = inspection_task(client, project)
    response = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "run-one"},
    )
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "queued"
    assert (
        client.post(
            f"/api/tasks/{task['id']}/execute",
            json={"expected_revision": task["revision"], "idempotency_key": "run-one"},
        ).json()["id"]
        == job["id"]
    )
    assert Worker(store).run_once() is True
    complete = client.get(f"/api/jobs/{job['id']}").json()
    assert complete["status"] == "succeeded", complete
    result = client.get(f"/api/jobs/{job['id']}/result").json()
    assert result["data"]["datasets"][0]["sha256"] == asset["sha256"]
    assert result["data"]["datasets"][0]["facts"]["layers"][0]["row_count"] == 2
    download = client.get(f"/api/jobs/{job['id']}/download")
    assert download.status_code == 200
    assert json.loads(download.content)["manifest"]["draft_revision"] == task["revision"]
    assert result["states"]["business_validated"] is False


def test_new_draft_revision_requires_new_idempotency_intent(workspace):
    _, _, client, project = workspace
    task, _ = inspection_task(client, project)
    first = client.post(
        f"/api/tasks/{task['id']}/execute", json={"expected_revision": 2, "idempotency_key": "one"}
    )
    assert first.status_code == 202
    draft = task["draft"]
    draft["title"] = "Changed task"
    client.put(f"/api/tasks/{task['id']}", json={"expected_revision": 2, "draft": draft})
    conflict = client.post(
        f"/api/tasks/{task['id']}/execute", json={"expected_revision": 3, "idempotency_key": "one"}
    )
    assert conflict.status_code == 409


def test_worker_verifies_actual_bytes_and_records_failure(workspace):
    settings, store, client, project = workspace
    task, asset = inspection_task(client, project)
    job = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": 2, "idempotency_key": "tamper"},
    ).json()
    (settings.storage_root / asset["object_key"]).write_bytes(b"changed after validation")
    Worker(store).run_once()
    response = client.get(f"/api/jobs/{job['id']}").json()
    assert response["status"] == "failed"
    assert response["error"]["code"] == "INPUT_INTEGRITY"
    assert client.get(f"/api/jobs/{job['id']}/result").status_code == 409


def test_scientific_missing_unit_blocks_only_dependent_computation(workspace):
    _, _, client, project = workspace
    task, _ = inspection_task(client, project)
    draft = task["draft"]
    draft["purpose"] = "cluster"
    client.put(f"/api/tasks/{task['id']}", json={"expected_revision": 2, "draft": draft})
    preflight = client.get(f"/api/tasks/{task['id']}/preflight").json()
    assert preflight["ready"] is False
    assert any(x["code"] == "UNIT_REQUIRED" for x in preflight["issues"])
    blocked = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": 3, "idempotency_key": "blocked"},
    )
    assert blocked.status_code == 422
    assert client.get(f"/api/tasks/{task['id']}/jobs").json()["total"] == 0
