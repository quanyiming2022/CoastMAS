"""Independent research state, intentional method application and nested processing."""

from coastmas_next.store import tasks
from sqlalchemy import func, select
from test_geospatial_view import upload


def new_task(client, project, title="A", purpose="inspect"):
    response = client.post(
        "/api/tasks", json={"project_id": project, "title": title, "purpose": purpose}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_workspace_context_is_private_persistent_and_browsing_never_binds(workspace, tmp_path):
    settings, store, client, project = workspace
    task = new_task(client, project)
    asset = upload(workspace, tmp_path)
    url = f"/api/projects/{project}/workspace-state"
    assert client.get(url).status_code == 200
    state = {
        "active_task_id": task["id"],
        "inspected_asset_id": asset["id"],
        "viewed_job_id": None,
        "panel": "data",
        "central_view": "map",
        "drawer": "open",
    }
    response = client.put(url, json={"expected_revision": 0, "state": state})
    assert response.status_code == 200, response.text
    assert client.get("/api/tasks/" + task["id"]).json() == task
    assert client.get(url).json()["state"]["active_task_id"] == task["id"]
    assert client.put(url, json={"expected_revision": 0, "state": state}).status_code == 409
    session = client.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    ).json()
    client.headers["X-CSRF-Token"] = session["csrf"]
    assert client.get(url).json()["state"] is None
    assert client.put(url, json={"expected_revision": 0, "state": state}).status_code == 200
    other = store.create_account("context-other@example.test", "safe-password-for-tests")
    other_project = store.create_project(other, "Other")
    foreign = store.new_task(other, other_project, task["draft"])
    assert (
        client.put(
            url, json={"expected_revision": 1, "state": {**state, "active_task_id": foreign["id"]}}
        ).status_code
        == 404
    )


def test_method_application_explicit_fixed_and_conflict_safe(workspace):
    _, store, client, project = workspace
    from coastmas_next.reuse import TemplateSpec, write_draft_template

    with store.engine.begin() as c:
        actor = client.get("/api/session").json()["id"]
        template = write_draft_template(
            c,
            actor,
            project,
            TemplateSpec(
                purpose="method",
                title="明确权重方法",
                basis="独立工程夹具，不作业务依据",
                profiles=["csv"],
                configuration={
                    "task": "assessment",
                    "method": "weighted",
                    "indicators": [
                        {
                            "concept": "vegetation",
                            "unit": "1",
                            "lower": 0,
                            "upper": 1,
                            "positive": True,
                            "weight": 1,
                        }
                    ],
                },
            ),
            {},
            True,
        )
    task = new_task(client, project, purpose="assessment")
    # Reading a method directory is not an application action.
    client.get(f"/api/projects/{project}/templates")
    assert client.get("/api/tasks/" + task["id"]).json() == task
    body = {
        "expected_revision": 1,
        "method_id": template["id"],
        "method_revision": template["revision"],
    }
    response = client.post(f"/api/tasks/{task['id']}/apply-method", json=body)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["draft"]["method_id"] == template["id"]
    assert saved["draft"]["options"]["method_revision"] == template["revision"]
    assert len(saved["draft"]["options"]["processing_plan"]) == 8
    assert saved["draft"]["options"]["indicator_requirements"][0]["concept"] == "vegetation"
    assert client.post(f"/api/tasks/{task['id']}/apply-method", json=body).status_code == 409
    assert client.get("/api/tasks/" + task["id"]).json() == saved


def test_processing_node_keeps_parent_draft_and_top_level_task_count(workspace, tmp_path):
    _, store, client, project = workspace
    from coastmas_next.worker import Worker

    asset = upload(workspace, tmp_path)
    task = new_task(client, project, purpose="assessment")
    task = client.post(
        f"/api/tasks/{task['id']}/sources", json={"expected_revision": 1, "assets": [asset["id"]]}
    ).json()
    url = f"/api/tasks/{task['id']}/processing-nodes"
    response = client.post(
        url,
        json={
            "expected_revision": task["revision"],
            "operator": "valid_mask",
            "asset_id": asset["id"],
            "band": 1,
            "idempotency_key": "mask-node",
        },
    )
    assert response.status_code == 201, response.text
    node = response.json()
    assert (
        client.post(
            url,
            json={
                "expected_revision": task["revision"],
                "operator": "valid_mask",
                "asset_id": asset["id"],
                "band": 1,
                "idempotency_key": "mask-node",
            },
        ).json()["id"]
        == node["id"]
    )
    job = client.post(
        f"/api/processing-nodes/{node['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "mask-run"},
    )
    assert job.status_code == 202, job.text
    Worker(store).run_once()
    record = client.get("/api/jobs/" + job.json()["id"]).json()
    assert record["status"] == "succeeded", record
    assert client.get("/api/tasks/" + task["id"]).json() == task
    with store.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(tasks)) == 1
    result = client.get("/api/jobs/" + job.json()["id"] + "/descriptor").json()
    assert result["primary"] is not None
