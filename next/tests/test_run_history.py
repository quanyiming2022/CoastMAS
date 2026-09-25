"""Paged immutable run history keeps full result retrieval and permission boundaries."""

from coastmas_next.worker import Worker
from test_execution import inspection_task


def test_run_history_pages_actual_total_and_keeps_old_result(workspace):
    _, store, client, project = workspace
    task, _ = inspection_task(client, project)
    ids = []
    for index in range(27):
        response = client.post(
            f"/api/tasks/{task['id']}/execute",
            json={"expected_revision": task["revision"], "idempotency_key": f"history-{index}"},
        )
        assert response.status_code == 202
        ids.append(response.json()["id"])
    assert Worker(store).run_once()
    first = client.get(f"/api/tasks/{task['id']}/jobs?limit=25&offset=0").json()
    second = client.get(f"/api/tasks/{task['id']}/jobs?limit=25&offset=25").json()
    assert first["total"] == second["total"] == 27
    assert len(first["items"]) == 25 and len(second["items"]) == 2
    assert {item["id"] for page in [first, second] for item in page["items"]} == set(ids)
    assert all(
        "manifest" not in item and item["draft_revision"] == task["revision"]
        for item in first["items"]
    )
    old = client.get(f"/api/jobs/{ids[0]}/result")
    assert old.status_code == 200
    assert old.json()["data"]["datasets"][0]["facts"]["layers"][0]["row_count"] == 2
    assert client.get(f"/api/tasks/{task['id']}/jobs?limit=0").status_code == 422


def test_viewer_reads_run_history_but_cannot_cancel(workspace):
    _, _, client, project = workspace
    task, _ = inspection_task(client, project)
    job = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "viewer"},
    ).json()
    login = client.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    )
    client.headers["X-CSRF-Token"] = login.json()["csrf"]
    assert client.get(f"/api/tasks/{task['id']}/jobs").json()["total"] == 1
    assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 403
