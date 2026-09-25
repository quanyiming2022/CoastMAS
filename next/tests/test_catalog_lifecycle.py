"""Catalog operations change metadata, never original bytes or frozen science."""

from coastmas_next.execution import Execution
from coastmas_next.store import Store
from coastmas_next.worker import Worker


def asset(client, project, name="original.csv"):
    r = client.post(f"/api/projects/{project}/assets", files={"file": (name, b"id,v\n001,0\n")})
    assert r.status_code == 201
    return r.json()["asset"]


def plan(client, project, action, ids=None, query=None):
    r = client.post(
        f"/api/projects/{project}/catalog/operations",
        json={
            "action": action,
            "selection": {"ids": ids} if ids is not None else {"query": query, "excluded_ids": []},
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def apply(client, project, preview):
    return client.post(f"/api/projects/{project}/catalog/operations/{preview['id']}/apply")


def test_edit_conflict_search_and_recycle_restore_keep_bytes_and_identity(workspace):
    settings, _, client, project = workspace
    a = asset(client, project)
    body = {
        "expected_revision": 0,
        "display_name": "潮间带原始观测",
        "description": "2022资料",
        "tags": ["海岸"],
    }
    r = client.patch(f"/api/assets/{a['id']}/metadata", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["revision"] == 1
    assert client.patch(f"/api/assets/{a['id']}/metadata", json=body).status_code == 409
    for query in ["潮间带", "original.csv", "海岸"]:
        listing = client.get(f"/api/projects/{project}/catalog", params={"query": query}).json()
        assert listing["total"] == 1
        assert listing["items"][0]["name"] == "original.csv"
        assert listing["items"][0]["display_name"] == "潮间带原始观测"
    before = client.get(f"/api/assets/{a['id']}").json()
    preview = plan(client, project, "recycle", [a["id"]])
    assert preview["total"] == 1
    result = apply(client, project, preview)
    assert result.status_code == 200, result.text
    assert result.json()["items"][0]["status"] == "applied"
    assert apply(client, project, preview).json() == result.json()
    assert client.get(f"/api/projects/{project}/catalog").json()["total"] == 0
    assert client.get(f"/api/projects/{project}/catalog?state=recycled").json()["total"] == 1
    assert client.get(f"/api/assets/{a['id']}/download").content == b"id,v\n001,0\n"
    Store(settings).initialize()
    restored = apply(client, project, plan(client, project, "restore", [a["id"]]))
    assert restored.json()["items"][0]["status"] == "applied"
    after = client.get(f"/api/assets/{a['id']}").json()
    assert (before["sha256"], before["revision"], before["facts"]) == (
        after["sha256"],
        after["revision"],
        after["facts"],
    )
    assert client.get(f"/api/projects/{project}/catalog").json()["total"] == 1


def test_whole_query_selection_is_frozen_with_partial_conflict_results(workspace):
    _, _, client, project = workspace
    selected = [asset(client, project, f"coast-{i}.csv") for i in range(23)]
    preview = plan(
        client, project, "recycle", query={"query": "coast", "sort": "name", "state": "active"}
    )
    assert preview["total"] == 23
    newer = asset(client, project, "coast-new.csv")
    changed = selected[0]
    assert (
        client.patch(
            f"/api/assets/{changed['id']}/metadata",
            json={"expected_revision": 0, "display_name": "changed", "description": "", "tags": []},
        ).status_code
        == 200
    )
    result = apply(client, project, preview).json()
    assert sum(i["status"] == "applied" for i in result["items"]) == 22
    assert (
        next(i for i in result["items"] if i["id"] == changed["id"])["code"] == "METADATA_CONFLICT"
    )
    left = client.get(f"/api/projects/{project}/catalog").json()["items"]
    assert {i["id"] for i in left} == {changed["id"], newer["id"]}


def test_active_run_blocks_recycle_and_recycled_input_blocks_new_execution(workspace):
    _, store, client, project = workspace
    a = asset(client, project)
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "history", "purpose": "inspect"}
    ).json()
    client.post(
        f"/api/tasks/{task['id']}/sources", json={"expected_revision": 1, "assets": [a["id"]]}
    )
    preview = plan(client, project, "recycle", [a["id"]])
    job = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": 2, "idempotency_key": "first"},
    ).json()
    blocked = apply(client, project, preview).json()
    assert blocked["items"][0]["code"] == "RESOURCE_IN_USE"
    assert Worker(store).run_once()
    assert (
        Execution(store).read_job(client.get("/api/session").json()["id"], job["id"])["status"]
        == "succeeded"
    )
    assert (
        apply(client, project, plan(client, project, "recycle", [a["id"]])).json()["items"][0][
            "status"
        ]
        == "applied"
    )
    assert (
        client.post(
            f"/api/tasks/{task['id']}/execute",
            json={"expected_revision": 2, "idempotency_key": "second"},
        ).status_code
        == 409
    )
    assert client.get(f"/api/jobs/{job['id']}/result").status_code == 200


def test_lifecycle_permissions_and_plan_ownership_are_rechecked(workspace):
    _, store, client, project = workspace
    a = asset(client, project)
    preview = plan(client, project, "recycle", [a["id"]])
    login = client.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    ).json()
    client.headers["X-CSRF-Token"] = login["csrf"]
    assert (
        client.patch(
            f"/api/assets/{a['id']}/metadata",
            json={"expected_revision": 0, "display_name": "bad", "description": "", "tags": []},
        ).status_code
        == 403
    )
    assert apply(client, project, preview).status_code in {403, 404}
    admin = store.create_account("other@example.test", "safe-password-for-tests")
    other = store.create_project(admin, "other")
    login = client.post(
        "/api/session", json={"email": "other@example.test", "password": "safe-password-for-tests"}
    ).json()
    client.headers["X-CSRF-Token"] = login["csrf"]
    assert (
        client.post(
            f"/api/projects/{other}/catalog/operations",
            json={"action": "recycle", "selection": {"ids": [a["id"]]}},
        ).status_code
        == 404
    )
