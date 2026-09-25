"""Definitions are scoped, versioned, partial and reusable across new file bytes."""

import pytest


def prepare(client, project, payload=b"id,distance\n1,0\n2,12\n", name="survey.csv"):
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Reusable definition", "purpose": "regression"},
    ).json()
    uploaded = client.post(
        f"/api/projects/{project}/assets",
        files={"file": (name, payload)},
        data={"task_id": task["id"], "expected_revision": "1"},
    ).json()
    return uploaded["task"], uploaded["asset"]


def publish(client, task, **editor):
    task["draft"]["options"]["semantic_definition"] = {
        "basis": "Survey protocol section 3",
        "scope": "same_names",
        **editor,
    }
    saved = client.put(
        f"/api/tasks/{task['id']}",
        json={"expected_revision": task["revision"], "draft": task["draft"]},
    ).json()
    response = client.post(
        f"/api/tasks/{task['id']}/publish-definition",
        json={"expected_revision": saved["revision"], "approve": True},
    )
    return response, saved


def test_definition_reuses_new_batch_without_inheriting_response_or_year(workspace):
    _, _, client, project = workspace
    task, first = prepare(client, project)
    task["draft"]["mapping"][1].update(concept="distance_to_water", unit="m", role="response")
    response, saved = publish(client, task)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["task"]["draft"]["mapping"][1]["role"] == "response"
    assert result["template"]["spec"]["rules"][0]["role"] is None
    assert result["template"]["spec"]["declaration"] == {}
    replay = client.post(
        f"/api/tasks/{task['id']}/publish-definition",
        json={"expected_revision": saved["revision"], "approve": True},
    )
    assert replay.json() == result
    newer, second = prepare(client, project, b"id,distance\n3,15\n4,0\n")
    assert first["sha256"] != second["sha256"]
    binding = newer["draft"]["mapping"][1]
    assert binding["unit"] == "m" and binding["concept"] == "distance_to_water"
    assert binding["role"] == "feature"
    assert binding["template_id"] == result["template"]["id"]
    assert newer["draft"]["mapping"][0]["unit"] is None
    other, _ = prepare(client, project, b"id,distance\n7,33\n", name="unrelated.csv")
    assert other["draft"]["mapping"][1]["unit"] is None
    changed = result["task"]
    changed["draft"]["mapping"][1]["unit"] = "km"
    revision, _ = publish(client, changed)
    assert revision.status_code == 201, revision.text
    assert revision.json()["template"]["id"] == result["template"]["id"]
    assert revision.json()["template"]["revision"] == 2
    assert len(client.get(f"/api/templates/{result['template']['id']}/history").json()) == 2


@pytest.mark.parametrize("case", ["unknown_unit", "invented_field", "conflicting_definitions"])
def test_definition_rejects_invalid_or_ambiguous_science_atomically(workspace, case):
    _, _, client, project = workspace
    task, _ = prepare(client, project)
    task["draft"]["mapping"][1]["unit"] = "m"
    if case == "unknown_unit":
        task["draft"]["mapping"][1]["unit"] = "imagined_coastal_unit"
    elif case == "invented_field":
        task["draft"]["mapping"][1]["field"] = "data/not_in_file"
    else:
        another, asset = prepare(client, project, name="other.csv")
        task["draft"]["selection"] += another["draft"]["selection"]
        binding = another["draft"]["mapping"][1]
        binding["unit"] = "kg"
        task["draft"]["mapping"].append(binding)
    response, saved = publish(client, task)
    assert response.status_code == 422, response.text
    assert client.get(f"/api/tasks/{task['id']}").json()["revision"] == saved["revision"]
    assert client.get(f"/api/projects/{project}/templates").json() == []


def test_partial_unit_definition_files_only_never_invents_meaning(workspace):
    _, _, client, project = workspace
    task, asset = prepare(client, project)
    task["draft"]["mapping"][1]["unit"] = "m"
    response, _ = publish(client, task, scope="files")
    assert response.status_code == 201, response.text
    rule = response.json()["template"]["spec"]["rules"][0]
    assert rule["concept"] is None and rule["support"] is None
    assert response.json()["template"]["spec"]["scope"]["asset_sha256"] == [asset["sha256"]]
    newer, _ = prepare(client, project, b"id,distance\n3,17\n")
    assert newer["draft"]["mapping"][1]["unit"] is None
