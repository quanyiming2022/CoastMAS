"""Automatic review must be bounded to saved metadata and have no execution side effects."""

import io

from sqlalchemy import func, select

from coastmas_next.execution import jobs
from coastmas_next.store import tasks


def test_empty_and_known_gaps_never_read_source_or_compute(workspace, monkeypatch):
    _, store, client, project = workspace
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "goal": "comprehensive-assessment", "title": "空研究"},
    ).json()
    initial = client.get("/api/tasks/" + task["id"]).json()

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Metadata review may not invoke formal preflight or scientific computation"
        )

    monkeypatch.setattr("coastmas_next.execution.preflight", forbidden)
    monkeypatch.setattr("rasterio.open", forbidden)
    monkeypatch.setattr("coastmas_next.temporal.compute", forbidden)
    response = client.get(f"/api/tasks/{task['id']}/configuration-review?revision=1")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["task_id"] == task["id"] and report["revision"] == 1
    assert report["scope"] == "saved_metadata" and report["execution_checked"] is False
    assert [p["code"] for p in report["issues"]] == ["DATA_REQUIRED"]
    assert report["issues"][0]["steps"] == ["sources"]
    assert client.get("/api/tasks/" + task["id"]).json() == initial
    with store.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(tasks)) == 1
        assert c.scalar(select(func.count()).select_from(jobs)) == 0


def test_metadata_review_scopes_known_issues_and_rejects_stale_revision(workspace, monkeypatch):
    _, _, client, project = workspace
    asset = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("真实SHA缺口.csv", io.BytesIO(b"id,x\n001,0.4\n"), "text/csv")},
    ).json()["asset"]
    task = client.post(
        "/api/tasks", json={"project_id": project, "purpose": "assessment", "title": "数值"}
    ).json()
    draft = {**task["draft"], "selection": [{"asset_id": asset["id"], "revision": 1}]}
    saved = client.put(
        f"/api/tasks/{task['id']}", json={"expected_revision": 1, "draft": draft}
    ).json()

    def forbidden(*args, **kwargs):
        raise AssertionError("Review read actual rows")

    monkeypatch.setattr("coastmas_next.observations.read_rows", forbidden)
    reply = client.get(f"/api/tasks/{task['id']}/configuration-review?revision={saved['revision']}")
    assert reply.status_code == 200, reply.text
    report = reply.json()
    assert any(
        i["code"] == "METHOD_REQUIRED" and "sources" not in i["steps"] for i in report["issues"]
    )
    assert not any(i["code"] == "LOCATION_REQUIRED" for i in report["issues"])
    assert len({i["id"] for i in report["issues"]}) == len(report["issues"])
    stale = client.get(f"/api/tasks/{task['id']}/configuration-review?revision=1")
    assert stale.status_code == 409 and stale.json()["code"] == "REVIEW_STALE"
    # Data inspection does not require evaluation weights, responses or indicator directions.
    inspect = client.post(
        "/api/tasks", json={"project_id": project, "purpose": "inspect", "title": "查看"}
    ).json()
    client.put(
        f"/api/tasks/{inspect['id']}",
        json={
            "expected_revision": 1,
            "draft": {**inspect["draft"], "selection": draft["selection"]},
        },
    )
    report = client.get(f"/api/tasks/{inspect['id']}/configuration-review?revision=2").json()
    assert report["issues"] == [] and report["execution_checked"] is False


def test_review_permission_failure_does_not_return_cached_private_metadata(workspace):
    _, store, client, project = workspace
    task = client.post(
        "/api/tasks", json={"project_id": project, "purpose": "assessment", "title": "私有"}
    ).json()
    from coastmas_next.store import members

    with store.engine.begin() as c:
        c.execute(members.delete().where(members.c.project_id == project))
    result = client.get(f"/api/tasks/{task['id']}/configuration-review?revision=1")
    assert result.status_code == 404
    assert "私有" not in result.text


def test_no_statement_is_not_reported_as_invalid_scope_after_input_removal(workspace):
    _, _, client, project = workspace
    from coastmas_next.reuse import validate_knowledge

    _, store, _, _ = workspace
    asset = client.post(
        f"/api/projects/{project}/assets", files={"file": ("one.csv", b"id,x\n001,1\n")}
    ).json()["asset"]
    task = client.post(
        "/api/tasks", json={"project_id": project, "purpose": "assessment", "title": "声明适用范围"}
    ).json()
    draft = {
        **task["draft"],
        "selection": [{"asset_id": asset["id"], "revision": 1}],
        "options": {
            "inherited_declarations": {"removed": {}, asset["id"]: {}},
            "declaration_references": {"removed": [], asset["id"]: []},
        },
    }
    actor = client.get("/api/session").json()["id"]
    issues = validate_knowledge(store, actor, project, draft, [asset])
    assert not [issue for issue in issues if issue["code"] == "DECLARATION_CHANGED"]
    saved = client.put(
        f"/api/tasks/{task['id']}", json={"expected_revision": 1, "draft": draft}
    ).json()
    assert "removed" not in saved["draft"]["options"]["declaration_references"]
    assert asset["id"] in saved["draft"]["options"]["inherited_declarations"]
