"""Whole-project task search with typed classification and stable real pagination."""

from coastmas_next.contracts import TaskDraft


def test_two_hundred_tasks_search_sort_page_and_role_isolation(workspace):
    _, store, client, project = workspace
    actor = client.get("/api/session").json()["id"]
    expected = []
    for index in range(205):
        purpose = "assessment" if index % 2 else "inspect"
        record = store.new_task(
            actor,
            project,
            TaskDraft(title=f"海岸任务 {index:03}", purpose=purpose).model_dump(mode="json"),
        )
        expected.append(record)
    url = f"/api/projects/{project}/task-catalog"
    first = client.get(url, params={"sort": "name", "limit": 20})
    assert first.status_code == 200, first.text
    assert first.json()["total"] == 205
    assert [t["draft"]["title"] for t in first.json()["items"]] == [
        f"海岸任务 {i:03}" for i in range(20)
    ]
    last = client.get(url, params={"sort": "name", "limit": 20, "offset": 200}).json()
    assert len(last["items"]) == 5 and last["total"] == 205
    filtered = client.get(url, params={"query": " 199", "purpose": "assessment"}).json()
    assert filtered["total"] == 1 and filtered["items"][0]["draft"]["title"] == "海岸任务 199"
    assert client.get(url, params={"query": "no match"}).json()["total"] == 0
    assert client.get(url, params={"limit": 101}).status_code == 422
    assert client.get(url, params={"purpose": "invented"}).status_code == 422
    other = store.create_account("task-private@example.test", "safe-password-for-tests")
    other_project = store.create_project(other, "private")
    store.new_task(
        other,
        other_project,
        TaskDraft(title="海岸任务 private", purpose="inspect").model_dump(mode="json"),
    )
    assert client.get(url).json()["total"] == 205
    session = client.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    ).json()
    client.headers["X-CSRF-Token"] = session["csrf"]
    assert client.get(url).json()["total"] == 205
    assert client.get(f"/api/projects/{other_project}/task-catalog").status_code == 404
