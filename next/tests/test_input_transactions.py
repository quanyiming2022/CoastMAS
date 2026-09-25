import copy

from sqlalchemy import func, select

from coastmas_next.store import revisions


def create_task(client, project, title="新研究"):
    response = client.post(
        "/api/tasks", json={"project_id": project, "title": title, "purpose": "assessment"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, project, name="observed.csv"):
    response = client.post(
        f"/api/projects/{project}/assets", files={"file": (name, b"id,v\n001,2\n")}
    )
    assert response.status_code == 201, response.text
    return response.json()["asset"]


def lifecycle(client, kind, record_id, action):
    plan = client.post(
        f"/api/management/catalog/{kind}/selections", json={"ids": [record_id], "action": action}
    )
    assert plan.status_code == 201, plan.text
    result = client.post("/api/management/selections/" + plan.json()["id"] + "/apply")
    assert result.json()["succeeded"] == 1, result.text


def attach(client, task, assets, key="intent", revision=None):
    return client.post(
        f"/api/tasks/{task['id']}/inputs:attach",
        json={
            "expected_revision": revision or task["revision"],
            "idempotency_key": key,
            "inputs": [{"asset_id": a["id"], "revision": a["revision"]} for a in assets],
        },
    )


def test_recycled_task_does_not_lock_active_project(workspace):
    _, _, client, project = workspace
    old = create_task(client, project, "已回收研究")
    lifecycle(client, "tasks", old["id"], "recycle")
    fresh = create_task(client, project)
    asset = upload(client, project)
    denied = attach(client, old, [asset])
    assert denied.status_code == 409
    assert denied.json()["code"] == "TASK_RECYCLED"
    assert denied.json()["details"]["object"]["id"] == old["id"]
    assert attach(client, fresh, [asset]).status_code == 200
    lifecycle(client, "projects", project, "archive")
    blocked = client.post(
        "/api/tasks", json={"project_id": project, "title": "blocked", "purpose": "assessment"}
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "PROJECT_READ_ONLY"


def test_attach_replay_preserves_mapping_and_durable_revision(workspace):
    _, store, client, project = workspace
    task = create_task(client, project)
    asset = upload(client, project)
    response = attach(client, task, [asset])
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["items"][0]["status"] == "added"
    assert first["task"]["revision"] == 2
    assert attach(client, task, [asset]).json() == first
    edited = copy.deepcopy(first["task"])
    edited["draft"]["mapping"][0]["role"] = "identity"
    saved = client.put(
        f"/api/tasks/{task['id']}", json={"expected_revision": 2, "draft": edited["draft"]}
    ).json()
    replay = attach(client, task, [asset]).json()
    assert replay == first
    duplicate = attach(client, saved, [asset], key="another").json()
    assert duplicate["items"][0]["status"] == "already_present"
    assert duplicate["task"]["revision"] == 3
    assert duplicate["task"]["draft"]["mapping"][0]["role"] == "identity"
    assert client.get(f"/api/tasks/{task['id']}").json() == saved
    with store.engine.connect() as c:
        assert (
            c.scalar(
                select(func.count()).select_from(revisions).where(revisions.c.task_id == task["id"])
            )
            == 3
        )


def test_partial_attachment_and_conflict_explain_actual_changes(workspace):
    _, _, client, project = workspace
    task = create_task(client, project)
    a = upload(client, project)
    b = upload(client, project, "second.csv")
    plan = client.post(
        f"/api/projects/{project}/catalog/operations",
        json={"action": "recycle", "selection": {"ids": [a["id"]]}},
    ).json()
    assert (
        client.post(f"/api/projects/{project}/catalog/operations/{plan['id']}/apply").status_code
        == 200
    )
    response = attach(client, task, [a, b])
    assert response.status_code == 200, response.text
    result = response.json()
    assert [r["status"] for r in result["items"]] == ["rejected", "added"]
    assert result["items"][0]["code"] == "ASSET_UNAVAILABLE"
    assert [r["asset_id"] for r in result["task"]["draft"]["selection"]] == [b["id"]]
    conflicting = attach(client, task, [b], key="stale")
    assert conflicting.status_code == 409
    details = conflicting.json()["details"]
    assert details["current_revision"] == 2
    assert any(c["field"] == "selection" for c in details["changes"])
    assert attach(client, task, [b], key="intent").status_code == 409  # same key, changed payload


def test_fixed_asset_version_and_cross_project_access(workspace):
    _, store, client, project = workspace
    task = create_task(client, project)
    a = upload(client, project)
    wrong = attach(client, task, [{**a, "revision": 9}])
    assert wrong.status_code == 200
    assert wrong.json()["items"][0]["code"] == "ASSET_VERSION_CHANGED"
    assert wrong.json()["task"]["revision"] == 1
    outsider = store.create_account(
        "outsider@example.test", "safe-password-for-tests", system_admin=True
    )
    other = store.create_project(outsider, "Unrelated")
    client.post(
        "/api/session",
        json={"email": "outsider@example.test", "password": "safe-password-for-tests"},
    )
    client.headers["X-CSRF-Token"] = client.get("/api/session").json()["csrf"]
    denied = attach(client, task, [a])
    assert denied.status_code == 404
    assert denied.json()["code"] == "PROJECT_UNAVAILABLE"
    assert client.get(f"/api/projects/{other}/catalog").status_code == 200
