"""Catalog lifecycle never removes identity, membership or research evidence."""

from coastmas_next.store import members
from sqlalchemy import func, select


def test_user_project_edits_and_frozen_batch_restore(workspace):
    _, store, client, project = workspace
    rows = []
    for i in range(27):
        r = client.post(
            "/api/accounts",
            json={"email": f"catalog-{i:03}@example.test", "password": "safe-password-for-tests"},
        )
        assert r.status_code == 201
        rows.append(r.json())
    url = "/api/management/catalog/users"
    listing = client.get(url, params={"query": "catalog-", "offset": 25, "limit": 25}).json()
    assert listing["total"] == 27 and len(listing["items"]) == 2
    target = listing["items"][0]
    changed = client.patch(
        url + "/" + target["id"],
        json={"expected_revision": 0, "changes": {"email": "renamed-user@example.test"}},
    )
    assert changed.status_code == 200, changed.text
    assert (
        client.patch(
            url + "/" + target["id"],
            json={"expected_revision": 0, "changes": {"email": "stale@example.test"}},
        ).status_code
        == 409
    )
    with store.engine.connect() as c:
        assert (
            c.scalar(
                select(func.count())
                .select_from(members)
                .where(members.c.account_id == target["id"])
            )
            == 0
        )
    plan = client.post(
        url + "/selections", json={"query": {"query": "catalog-"}, "action": "recycle"}
    )
    assert plan.status_code == 201, plan.text
    frozen = plan.json()
    assert frozen["count"] == 26
    client.post(
        "/api/accounts",
        json={"email": "catalog-new@example.test", "password": "safe-password-for-tests"},
    )
    result = client.post("/api/management/selections/" + frozen["id"] + "/apply").json()
    assert result["succeeded"] == 26
    assert client.get(url, params={"query": "catalog-", "state": "active"}).json()["total"] == 1
    assert client.get(url, params={"state": "recycled"}).json()["total"] == 26
    restore = client.post(
        url + "/selections", json={"ids": [rows[0]["id"]], "action": "restore"}
    ).json()
    assert (
        client.post("/api/management/selections/" + restore["id"] + "/apply").json()["succeeded"]
        == 1
    )
    projects = "/api/management/catalog/projects"
    assert client.get(projects, params={"query": "test"}).status_code == 200
    changed = client.patch(
        projects + "/" + project,
        json={
            "expected_revision": 0,
            "changes": {"name": "改名海岸项目", "classification": "沿海研究"},
        },
    )
    assert changed.status_code == 200, changed.text
    assert (
        client.get(projects, params={"classification": "沿海研究"}).json()["items"][0]["name"]
        == "改名海岸项目"
    )


def test_last_admin_and_project_permissions_are_server_enforced(workspace):
    _, store, client, project = workspace
    actor = client.get("/api/session").json()["id"]
    response = client.patch(
        "/api/management/catalog/users/" + actor,
        json={"expected_revision": 0, "changes": {"system_admin": False}},
    )
    assert response.status_code == 409, response.text
    outside = store.create_account("outsider-catalog@example.test", "safe-password-for-tests")
    other = store.create_project(outside, "Hidden science")
    # A system administrator may manage the project record, not read its science.
    assert any(
        r["id"] == other for r in client.get("/api/management/catalog/projects").json()["items"]
    )
    assert client.get(f"/api/projects/{other}/catalog").status_code == 404
    session = client.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    ).json()
    client.headers["X-CSRF-Token"] = session["csrf"]
    assert client.get("/api/management/catalog/users").status_code == 403
    assert (
        client.patch(
            "/api/management/catalog/projects/" + project,
            json={"expected_revision": 0, "changes": {"name": "bad"}},
        ).status_code
        == 403
    )
    assert client.get("/api/management/catalog/tasks", params={"project": other}).status_code == 404


def test_task_recycle_refuses_running_job_and_copies_without_old_results(workspace):
    _, store, client, project = workspace
    from coastmas_next.execution import jobs
    from coastmas_next.store import identifier
    from sqlalchemy import insert

    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "A", "purpose": "inspect"}
    ).json()
    url = "/api/management/catalog/tasks"
    clone = client.post(url + "/" + task["id"] + "/copy").json()
    assert clone["id"] != task["id"] and clone["draft"]["title"].startswith("A")
    with store.engine.begin() as c:
        c.execute(
            insert(jobs).values(
                id=identifier(),
                task_id=task["id"],
                project_id=project,
                actor=client.get("/api/session").json()["id"],
                idempotency_key="busy",
                fingerprint="fixture",
                status="running",
                manifest={},
                created=1,
                lease_until=99999999999,
                cancel_requested=False,
            )
        )
    plan = client.post(
        url + "/selections",
        params={"project": project},
        json={"ids": [task["id"], clone["id"]], "action": "recycle"},
    ).json()
    result = client.post("/api/management/selections/" + plan["id"] + "/apply").json()
    assert result["succeeded"] == 1 and result["failed"] == 1
    assert (
        client.get(url, params={"project": project, "state": "recycled"}).json()["items"][0]["id"]
        == clone["id"]
    )


def test_recycled_project_blocks_new_science_but_restore_preserves_records(workspace):
    _, store, client, project = workspace
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "保留研究", "purpose": "inspect"}
    ).json()
    base = "/api/management/catalog/projects"
    plan = client.post(base + "/selections", json={"ids": [project], "action": "recycle"}).json()
    assert (
        client.post("/api/management/selections/" + plan["id"] + "/apply").json()["succeeded"] == 1
    )
    assert client.get("/api/tasks/" + task["id"]).status_code == 200
    blocked = client.post(
        "/api/tasks", json={"project_id": project, "title": "不应写入", "purpose": "inspect"}
    )
    assert blocked.status_code == 409, blocked.text
    restored = client.post(
        base + "/selections", json={"ids": [project], "action": "restore"}
    ).json()
    assert (
        client.post("/api/management/selections/" + restored["id"] + "/apply").json()["succeeded"]
        == 1
    )
    assert client.get("/api/tasks/" + task["id"]).json() == task
    assert (
        client.post(
            "/api/tasks", json={"project_id": project, "title": "恢复后研究", "purpose": "inspect"}
        ).status_code
        == 201
    )


def test_member_removal_revokes_project_access_preserves_account_and_last_manager(workspace):
    _, store, client, project = workspace
    actor = client.get("/api/session").json()["id"]
    member = store.create_account("remove-member@example.test", "safe-password-for-tests")
    store.set_member(actor, project, member, "analyst")
    url = f"/api/projects/{project}/members/"
    removed = client.delete(url + member)
    assert removed.status_code == 200, removed.text
    assert client.delete(url + actor).status_code == 409
    assert (
        client.get("/api/management/catalog/users", params={"query": "remove-member"}).json()[
            "items"
        ][0]["active"]
        is True
    )
    session = client.post(
        "/api/session",
        json={"email": "remove-member@example.test", "password": "safe-password-for-tests"},
    ).json()
    client.headers["X-CSRF-Token"] = session["csrf"]
    assert client.get(f"/api/projects/{project}/catalog").status_code == 404
    assert client.delete(url + actor).status_code == 404
