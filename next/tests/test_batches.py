"""Durable batch intake: partial failures, replay, scope and no source mutation."""

from dataclasses import replace

from coastmas_next.batches import BatchIntake
from coastmas_next.store import Store


def test_upload_batch_recovers_partial_failure_and_replay_preserves_task(workspace):
    _, store, client, project = workspace
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "Batch", "purpose": "inspect"}
    ).json()
    creation = {
        "task_id": task["id"],
        "idempotency_key": "batch-one",
        "items": [{"name": "first.csv", "size": 9}, {"name": "second.csv", "size": 10}],
    }
    response = client.post(f"/api/projects/{project}/imports", json=creation)
    assert response.status_code == 201, response.text
    batch = response.json()
    replay = client.post(f"/api/projects/{project}/imports", json=creation).json()
    assert replay["id"] == batch["id"]
    first, second = batch["items"]
    endpoint = f"/api/imports/{batch['id']}/items/{first['id']}/content"
    sent = client.post(endpoint, files={"file": ("first.csv", b"id,v\n1,2\n")})
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "ready"
    saved = client.get(f"/api/tasks/{task['id']}").json()
    assert len(saved["draft"]["selection"]) == 1
    assert (
        client.post(endpoint, files={"file": ("first.csv", b"id,v\n1,2\n")}).json()["asset_id"]
        == sent.json()["asset_id"]
    )
    assert client.get(f"/api/tasks/{task['id']}").json()["revision"] == saved["revision"]
    endpoint2 = f"/api/imports/{batch['id']}/items/{second['id']}/content"
    failed = client.post(endpoint2, files={"file": ("second.csv", b"\x00" * 10)})
    assert failed.status_code == 422
    state = client.get(f"/api/imports/{batch['id']}").json()
    assert state["items"][0]["status"] == "ready"
    assert state["items"][1]["status"] == "failed"
    recovered = client.post(endpoint2, files={"file": ("second.csv", b"id,v\n2,33\n")})
    assert recovered.status_code == 200, recovered.text
    assert len(client.get(f"/api/tasks/{task['id']}").json()["draft"]["selection"]) == 2
    creation["items"][0]["name"] = "different.csv"
    assert client.post(f"/api/projects/{project}/imports", json=creation).status_code == 409


def test_local_batch_no_traversal_no_symlinks_and_hash_matches(tmp_path, workspace):
    settings, old_store, client, project = workspace
    root = tmp_path / "authorized"
    root.mkdir()
    (root / "safe.csv").write_bytes(b"id,v\n1,2\n")
    outside = tmp_path / "private.csv"
    outside.write_text("private")
    (root / "link.csv").symlink_to(outside)
    store = Store(replace(settings, local_sources=(root,)))
    service = BatchIntake(store)
    actor = client.get("/api/session").json()["id"]
    source = service.sources(actor, project)[0]["id"]
    # A configured connection is not a project grant, including for administrators.
    from sqlalchemy import insert

    from coastmas_next.batches import source_grants

    with store.engine.begin() as connection:
        connection.execute(
            insert(source_grants).values(project_id=project, source_id=source, actor=actor)
        )
    names = [item["name"] for item in service.browse(actor, project, source)["items"]]
    assert "safe.csv" in names and "link.csv" not in names
    import pytest

    from coastmas_next.store import Problem

    for path in ["../private.csv", "link.csv", "/etc/passwd"]:
        with pytest.raises(Problem):
            service.open_source(actor, project, source, path)
    task = old_store.new_task(
        actor,
        project,
        {
            "title": "Local",
            "purpose": "inspect",
            "selection": [],
            "mapping": [],
            "options": {},
            "method_id": None,
        },
    )
    batch = service.create(
        actor,
        project,
        {
            "task_id": task["id"],
            "idempotency_key": "local",
            "items": [{"name": "safe.csv", "size": 9, "source_id": source, "path": "safe.csv"}],
        },
    )
    assert service.run_once()
    state = service.read(actor, batch["id"])
    assert state["items"][0]["status"] == "ready"
    assert (root / "safe.csv").read_bytes() == b"id,v\n1,2\n"
    assert len(old_store.task(actor, task["id"])["draft"]["selection"]) == 1
    viewer = old_store.create_account("other-curator@example.test", "safe-password-for-tests")
    old_store.set_member(actor, project, viewer, "analyst")
    with pytest.raises(Problem):
        service.browse(viewer, project, source)


def test_ready_upload_replay_must_match_actual_bytes(workspace):
    _, _, client, project = workspace
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "Replay", "purpose": "inspect"}
    ).json()
    batch = client.post(
        f"/api/projects/{project}/imports",
        json={
            "task_id": task["id"],
            "idempotency_key": "ready-hash",
            "items": [{"name": "a.csv", "size": 9}],
        },
    ).json()
    item = batch["items"][0]
    path = f"/api/imports/{batch['id']}/items/{item['id']}/content"
    assert client.post(path, files={"file": ("a.csv", b"id,v\n1,2\n")}).status_code == 200
    assert client.post(path, files={"file": ("a.csv", b"id,v\n1,3\n")}).status_code == 409


def test_local_file_changed_while_queued_is_not_silently_substituted(tmp_path, workspace):
    settings, original, client, project = workspace
    root = tmp_path / "batch-source"
    root.mkdir()
    source = root / "a.csv"
    source.write_bytes(b"id,v\n1,2\n")
    store = Store(replace(settings, local_sources=(root,)))
    service = BatchIntake(store)
    actor = client.get("/api/session").json()["id"]
    source_id = service.sources(actor, project)[0]["id"]
    from sqlalchemy import insert

    from coastmas_next.batches import source_grants

    with store.engine.begin() as connection:
        connection.execute(
            insert(source_grants).values(project_id=project, source_id=source_id, actor=actor)
        )
    task = original.new_task(
        actor,
        project,
        {"title": "Changed", "purpose": "inspect", "selection": [], "mapping": [], "options": {}},
    )
    batch = service.create(
        actor,
        project,
        {
            "task_id": task["id"],
            "idempotency_key": "changed",
            "items": [{"name": "a.csv", "size": 9, "source_id": source_id, "path": "a.csv"}],
        },
    )
    source.write_bytes(b"id,v\n1,3\n")
    assert service.run_once()
    item = service.read(actor, batch["id"])["items"][0]
    assert item["status"] == "failed"
    assert item["error"]["code"] == "SOURCE_CHANGED"
    assert original.task(actor, task["id"])["draft"]["selection"] == []
