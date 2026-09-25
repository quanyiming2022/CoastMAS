from sqlalchemy import select

from coastmas_next.store import audit


def test_settings_are_global_and_audit_uses_one_ledger(workspace):
    _, store, client, project = workspace
    response = client.get("/api/system/settings")
    assert response.status_code == 200, response.text
    assert response.json()["runtime"]["chunk_bytes"] > 0
    assert "password" not in response.text and "database_url" not in response.text
    global_events = client.get("/api/management/audit").json()
    scoped = client.get("/api/management/audit", params={"project": project}).json()
    assert scoped["items"]
    ids = {i["id"] for i in global_events["items"]}
    assert all(i["id"] in ids for i in scoped["items"])
    created = next(i for i in scoped["items"] if i["action"] == "create_project")
    assert created["target_name"] == "New scientific workspace"
    assert created["action_label"] == "创建项目"
    with store.engine.connect() as c:
        assert (
            c.execute(select(audit).where(audit.c.id == created["id"])).mappings().one()["target"]
            == project
        )
    client.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    )
    assert client.get("/api/system/settings").status_code == 403
    assert client.get("/api/management/audit").status_code == 403
    assert client.get("/api/management/audit", params={"project": project}).status_code == 403


def test_member_candidates_can_find_beyond_fifty_without_internal_ids(workspace):
    _, store, client, project = workspace
    for n in range(52):
        store.create_account(f"person-{n:03}@example.test", "safe-password-for-tests")
    listed = client.get(f"/api/projects/{project}/member-candidates").json()
    assert len(listed) == 50
    found = client.get(
        f"/api/projects/{project}/member-candidates", params={"search": "person-051"}
    ).json()
    assert len(found) == 1 and found[0]["email"] == "person-051@example.test"
