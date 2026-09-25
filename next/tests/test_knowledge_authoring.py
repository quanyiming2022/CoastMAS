"""Source declarations are server drafts, hash-scoped and scientifically partial."""


def test_publish_source_statement_is_atomic_and_preserves_manual_model_roles(workspace):
    _, _, client, project = workspace
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Source statement", "purpose": "regression"},
    ).json()
    incoming = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("data.csv", b"id,v\n1,2\n")},
        data={"task_id": task["id"], "expected_revision": "1"},
    ).json()
    task = incoming["task"]
    asset = incoming["asset"]
    task["draft"]["mapping"][1].update(role="response", unit="m")
    task["draft"]["options"]["source_statement"] = {
        "basis": "User supplied statement",
        "source_description": "Open website",
        "license_statement": "Noncommercial use only",
        "observed_year": 2022,
    }
    saved = client.put(
        f"/api/tasks/{task['id']}",
        json={"expected_revision": task["revision"], "draft": task["draft"]},
    ).json()
    response = client.post(
        f"/api/tasks/{task['id']}/publish-statement",
        json={"expected_revision": saved["revision"], "approve": True},
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["task"]["draft"]["mapping"][1]["role"] == "response"
    assert result["task"]["draft"]["mapping"][1]["unit"] == "m"
    assert result["task"]["draft"]["mapping"][1]["concept"] is None
    assert result["template"]["spec"]["scope"]["asset_sha256"] == [asset["sha256"]]
    assert (
        result["task"]["draft"]["options"]["inherited_declarations"][asset["id"]]["observed_year"]
        == 2022
    )
    assert asset["facts"]["observed_period"] is None
    repeated = client.post(
        f"/api/tasks/{task['id']}/publish-statement",
        json={"expected_revision": saved["revision"], "approve": True},
    )
    assert repeated.status_code == 201
    assert repeated.json()["template"]["id"] == result["template"]["id"]
    current = result["task"]
    current["draft"]["options"]["source_statement"]["source_description"] = "Corrected source"
    newer = client.put(
        f"/api/tasks/{task['id']}",
        json={"expected_revision": current["revision"], "draft": current["draft"]},
    ).json()
    update = client.post(
        f"/api/tasks/{task['id']}/publish-statement",
        json={"expected_revision": newer["revision"], "approve": True},
    )
    assert update.status_code == 201, update.text
    assert update.json()["template"]["id"] == result["template"]["id"]
    assert update.json()["template"]["revision"] == 2
    history = client.get(f"/api/templates/{result['template']['id']}/history").json()
    assert len(history) == 2 and history[0]["spec"]["declaration"]["source"] == "Open website"
