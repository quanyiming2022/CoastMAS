"""Administration uses real authorization and protects active project ownership."""

from coastmas_next.store import accounts, members
from sqlalchemy import select


def test_admin_account_project_membership_and_viewer_denials(workspace):
    _, store, client, project = workspace
    created = client.post(
        "/api/accounts",
        json={
            "email": "analyst.new@example.test",
            "password": "new-user-password-123",
            "system_admin": False,
        },
    )
    assert created.status_code == 201, created.text
    user = created.json()
    assert "password_hash" not in user
    new_project = client.post("/api/projects", json={"name": "Second isolated project"})
    assert new_project.status_code == 201, new_project.text
    other = new_project.json()["id"]
    response = client.put(f"/api/projects/{other}/members/{user['id']}", json={"role": "analyst"})
    assert response.status_code == 200, response.text
    owner = client.get("/api/session").json()["id"]
    assert (
        client.put(f"/api/projects/{other}/members/{owner}", json={"role": "viewer"}).status_code
        == 409
    )
    login = client.post(
        "/api/session",
        json={"email": "analyst.new@example.test", "password": "new-user-password-123"},
    ).json()
    client.headers["X-CSRF-Token"] = login["csrf"]
    assert [p["id"] for p in client.get("/api/projects").json()] == [other]
    assert client.get("/api/accounts").status_code == 403
    assert client.get(f"/api/projects/{project}/members").status_code == 404
    assert (
        client.put(
            f"/api/projects/{other}/members/{user['id']}", json={"role": "manager"}
        ).status_code
        == 403
    )
    assert client.get(f"/api/projects/{other}/audit").status_code == 403
    assert client.post("/api/projects", json={"name": "Denied"}).status_code == 403
    assert (
        client.post(
            "/api/accounts",
            json={
                "email": "no@example.test",
                "password": "safe-password-123",
                "system_admin": True,
            },
        ).status_code
        == 403
    )
    with store.engine.connect() as c:
        assert c.scalar(select(accounts.c.system_admin).where(accounts.c.id == user["id"])) is False
        assert (
            c.scalar(
                select(members.c.role).where(
                    members.c.account_id == user["id"], members.c.project_id == other
                )
            )
            == "analyst"
        )


def test_disable_revokes_sessions_and_queued_work_but_never_disables_last_manager(workspace):
    _, store, client, project = workspace
    actor = client.get("/api/session").json()["id"]
    user = store.create_account("temporary@example.test", "temporary-password-123")
    store.set_member(actor, project, user, "analyst")
    token, _ = store.sign_in("temporary@example.test", "temporary-password-123")
    login = client.post(
        "/api/session",
        json={"email": "temporary@example.test", "password": "temporary-password-123"},
    ).json()
    client.headers["X-CSRF-Token"] = login["csrf"]
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Queued before disable", "purpose": "inspect"},
    ).json()
    uploaded = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("queued.csv", b"id,v\n1,2\n")},
        data={"task_id": task["id"], "expected_revision": "1"},
    ).json()
    run = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={
            "expected_revision": uploaded["task"]["revision"],
            "idempotency_key": "before-disabled",
        },
    )
    assert run.status_code == 202, run.text
    login = client.post(
        "/api/session", json={"email": "admin@example.test", "password": "safe-password-for-tests"}
    ).json()
    client.headers["X-CSRF-Token"] = login["csrf"]
    response = client.put(f"/api/accounts/{user}/state", json={"active": False})
    assert response.status_code == 200, response.text
    from coastmas_next.worker import Worker

    assert Worker(store).run_once()
    job = client.get(f"/api/jobs/{run.json()['id']}").json()
    assert job["status"] == "failed"
    assert job["error"]["code"] == "PROJECT_UNAVAILABLE"
    import pytest
    from coastmas_next.store import Problem

    with pytest.raises(Problem):
        store.authenticate(token)
    with store.engine.connect() as c:
        with pytest.raises(Problem):
            store.permission(c, user, project, write=True)
    assert client.put(f"/api/accounts/{actor}/state", json={"active": False}).status_code == 409
