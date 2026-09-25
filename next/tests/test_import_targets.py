"""Import target survives route changes and uncertain attachment responses."""

import hashlib


def test_import_target_recovery_conflict_and_idempotence(workspace):
    _, _, client, project = workspace
    a = client.post(
        "/api/tasks",
        json={"project_id": project, "goal": "comprehensive-assessment", "title": "目标A"},
    ).json()
    b = client.post(
        "/api/tasks",
        json={"project_id": project, "goal": "comprehensive-assessment", "title": "目标B"},
    ).json()
    target = client.post(
        f"/api/tasks/{a['id']}/import-targets",
        json={"expected_revision": 1, "idempotency_key": "import-a"},
    )
    assert target.status_code == 201, target.text
    target = target.json()
    raw = b"id,x\n1,0.5\n"
    upload = client.post(
        f"/api/projects/{project}/uploads",
        json={"name": "x.csv", "size": len(raw), "idempotency_key": "bytes-a"},
    ).json()
    linked = client.post(
        f"/api/import-targets/{target['id']}/resources", json={"kind": "upload", "id": upload["id"]}
    )
    assert linked.status_code == 200, linked.text
    client.post(
        f"/api/uploads/{upload['id']}/parts/0",
        files={"file": ("part", raw)},
        data={"sha256": hashlib.sha256(raw).hexdigest()},
    )
    ready = client.post(f"/api/uploads/{upload['id']}/complete")
    assert ready.status_code == 200, ready.text
    asset = ready.json()["asset"]
    draft = {**a["draft"], "title": "目标A修改了配置"}
    client.put("/api/tasks/" + a["id"], json={"expected_revision": 1, "draft": draft})
    done = client.post(f"/api/import-targets/{target['id']}/bind", json={"asset_id": asset["id"]})
    assert done.status_code == 200, done.text
    assert (
        done.json()["status"] == "not_attached" and done.json()["error"]["code"] == "DRAFT_CONFLICT"
    )
    restored = client.get(f"/api/tasks/{a['id']}/import-targets").json()[0]
    assert restored["entries"][0]["asset_id"] == asset["id"]
    assert client.get("/api/tasks/" + b["id"]).json() == b
    confirmed = client.post(
        f"/api/import-targets/{target['id']}/bind",
        json={"asset_id": asset["id"], "reviewed_revision": 2},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "attached"
    assert (
        client.post(
            f"/api/import-targets/{target['id']}/bind", json={"asset_id": asset["id"]}
        ).json()
        == confirmed.json()
    )
    assert len(client.get("/api/tasks/" + a["id"]).json()["draft"]["selection"]) == 1
    assert client.get("/api/tasks/" + b["id"]).json() == b


def test_target_cannot_attach_unrelated_or_cross_project_bytes(workspace):
    _, store, client, project = workspace
    a = client.post(
        "/api/tasks",
        json={"project_id": project, "goal": "comprehensive-assessment", "title": "目标"},
    ).json()
    target = client.post(
        f"/api/tasks/{a['id']}/import-targets",
        json={"expected_revision": 1, "idempotency_key": "a"},
    ).json()
    asset = client.post(
        f"/api/projects/{project}/assets", files={"file": ("else.csv", b"id,x\n1,1\n")}
    ).json()["asset"]
    assert (
        client.post(
            f"/api/import-targets/{target['id']}/bind", json={"asset_id": asset["id"]}
        ).status_code
        == 409
    )
    admin = client.get("/api/session").json()["id"]
    other = store.create_project(admin, "Other")
    upload = client.post(
        f"/api/projects/{other}/uploads",
        json={"name": "other.csv", "size": 8, "idempotency_key": "other"},
    ).json()
    assert (
        client.post(
            f"/api/import-targets/{target['id']}/resources",
            json={"kind": "upload", "id": upload["id"]},
        ).status_code
        == 404
    )
    viewer = client.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    ).json()
    client.headers["X-CSRF-Token"] = viewer["csrf"]
    assert client.get(f"/api/tasks/{a['id']}/import-targets").status_code == 403
