"""Personal layer ordering and run lookup never change science or history."""

from coastmas_next.worker import Worker
from test_spatial_results import prepare


def test_layer_preferences_are_bound_to_run_and_do_not_mutate_inputs(workspace, tmp_path):
    _, store, client, _ = workspace
    task, _, _ = prepare(workspace, tmp_path)
    job = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "layers"},
    ).json()
    assert Worker(store).run_once()
    frozen = client.get(f"/api/jobs/{job['id']}/result").content
    url = f"/api/jobs/{job['id']}/view-state"
    state = {
        "legend_visible": True,
        "artifact_id": "0",
        "layers": [{"artifact_id": "0", "visible": False, "opacity": 0.4}],
    }
    saved = client.put(url, json={"expected_revision": 0, "state": state})
    assert saved.status_code == 200, saved.text
    assert client.get(url).json()["state"]["layers"] == state["layers"]
    assert client.get(url).json()["state"]["legend_visible"] is True
    bad = {**state, "layers": [{"artifact_id": "99", "visible": True, "opacity": 1}]}
    assert client.put(url, json={"expected_revision": 1, "state": bad}).status_code == 422
    assert (
        client.put(
            url, json={"expected_revision": 1, "state": {**state, "layers": state["layers"] * 2}}
        ).status_code
        == 422
    )
    assert client.put(url, json={"expected_revision": 0, "state": state}).status_code == 409
    assert client.get(f"/api/jobs/{job['id']}/result").content == frozen
    assert client.get(f"/api/tasks/{task['id']}").json() == task


def test_run_lookup_paginates_filters_and_rechecks_project_permission(workspace, tmp_path):
    _, store, client, _ = workspace
    task, _, _ = prepare(workspace, tmp_path)
    jobs = [
        client.post(
            f"/api/tasks/{task['id']}/execute",
            json={"expected_revision": task["revision"], "idempotency_key": f"page-{i}"},
        ).json()
        for i in range(3)
    ]
    assert Worker(store).run_once()
    url = f"/api/tasks/{task['id']}/jobs"
    assert client.get(url + "?status=succeeded").json()["total"] == 1
    assert client.get(url + "?status=queued").json()["total"] == 2
    assert client.get(url + "?query=" + jobs[1]["id"][:12]).json()["total"] == 1
    first = client.get(url + "?limit=2").json()
    second = client.get(url + "?limit=2&offset=2").json()
    assert first["total"] == second["total"] == 3
    assert len({row["id"] for row in first["items"] + second["items"]}) == 3

    # Revocation is checked again on both personal views and paged history.
    from coastmas_next.app import create_app
    from fastapi.testclient import TestClient

    settings, _, _, project = workspace
    actor = client.get("/api/session").json()["id"]
    member = store.create_account("panel-member@example.test", "safe-password-for-tests")
    store.set_member(actor, project, member, "viewer")
    other = TestClient(create_app(settings))
    session = other.post(
        "/api/session",
        json={"email": "panel-member@example.test", "password": "safe-password-for-tests"},
    ).json()
    other.headers["X-CSRF-Token"] = session["csrf"]
    assert other.get(url).status_code == 200
    assert client.delete(f"/api/projects/{project}/members/{member}").status_code == 200
    assert other.get(url + "?limit=2").status_code == 404
    assert other.get(f"/api/jobs/{jobs[0]['id']}/view-state").status_code == 404
    assert (
        other.put(
            f"/api/jobs/{jobs[0]['id']}/view-state",
            json={"expected_revision": 0, "state": {"layers": []}},
        ).status_code
        == 404
    )
