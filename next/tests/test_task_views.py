"""Task display is actor-private and cannot mutate task science or selection."""

from coastmas_next.store import Store
from test_geospatial_view import upload


def test_task_view_is_persistent_private_and_independent_from_science(workspace, tmp_path):
    settings, store, client, project = workspace
    asset = upload(workspace, tmp_path)
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "Display only", "purpose": "inspect"}
    ).json()
    url = f"/api/tasks/{task['id']}"
    task = client.post(
        url + "/sources", json={"expected_revision": 1, "assets": [asset["id"]]}
    ).json()
    before = task["draft"]
    assert client.get(url + "/assets").json()[0]["id"] == asset["id"]
    assert client.get(url + "/view-state").json()["revision"] == 0
    state = {
        "asset_id": asset["id"],
        "band": 1,
        "camera": {"longitude": 110, "latitude": 23, "zoom": 10},
        "visible": False,
        "opacity": 0.4,
    }
    saved = client.put(url + "/view-state", json={"expected_revision": 0, "state": state})
    assert saved.status_code == 200, saved.text
    assert saved.json()["state"] == state
    Store(settings).initialize()
    assert client.get(url + "/view-state").json() == saved.json()
    assert client.get(url).json()["draft"] == before
    assert client.get(url).json()["revision"] == task["revision"]
    assert client.get(f"/api/projects/{project}/view-state").json()["state"] is None
    assert (
        client.put(
            url + "/view-state", json={"expected_revision": 0, "state": {**state, "opacity": 0.5}}
        ).status_code
        == 409
    )
    other = upload(workspace, tmp_path, name="not-selected.tif")
    assert (
        client.put(
            url + "/view-state",
            json={"expected_revision": 1, "state": {**state, "asset_id": other["id"]}},
        ).status_code
        == 422
    )
    session = client.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    ).json()
    client.headers["X-CSRF-Token"] = session["csrf"]
    assert client.get(url + "/view-state").json()["revision"] == 0
    assert (
        client.put(url + "/view-state", json={"expected_revision": 0, "state": state}).status_code
        == 200
    )
    assert (
        client.put(url, json={"expected_revision": task["revision"], "draft": before}).status_code
        == 403
    )
    assert client.get(url).json()["draft"] == before
    outsider = store.create_account("outside-task@example.test", "safe-password-for-tests")
    store.create_project(outsider, "Unrelated")
    session = client.post(
        "/api/session",
        json={"email": "outside-task@example.test", "password": "safe-password-for-tests"},
    ).json()
    client.headers["X-CSRF-Token"] = session["csrf"]
    assert client.get(url + "/view-state").status_code == 404
    assert client.get(url + "/assets").status_code == 404
    assert (
        client.put(url + "/view-state", json={"expected_revision": 0, "state": state}).status_code
        == 404
    )
