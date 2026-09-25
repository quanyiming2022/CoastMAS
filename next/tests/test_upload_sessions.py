"""Resumable byte identity, isolated ownership and finalization without a task."""

import hashlib
from dataclasses import replace

from coastmas_next.app import create_app
from coastmas_next.store import Store
from fastapi.testclient import TestClient


def setup(workspace):
    settings, _, _, project = workspace
    store = Store(replace(settings, upload_chunk_bytes=8))
    client = TestClient(create_app(store.settings))
    user = client.post(
        "/api/session", json={"email": "admin@example.test", "password": "safe-password-for-tests"}
    ).json()
    client.headers["X-CSRF-Token"] = user["csrf"]
    return store, client, project


def begin(client, project, payload, key="one", name="real.csv"):
    response = client.post(
        f"/api/projects/{project}/uploads",
        json={"name": name, "size": len(payload), "idempotency_key": key},
    )
    assert response.status_code == 201, response.text
    return response.json()


def part(client, session, index, payload):
    return client.post(
        f"/api/uploads/{session}/parts/{index}",
        files={"file": ("part", payload)},
        data={"sha256": hashlib.sha256(payload).hexdigest()},
    )


def test_parts_replay_restart_and_finalize_preserve_exact_file(workspace):
    store, client, project = setup(workspace)
    source = b"id,value\n001,0\n002,4\n"
    upload = begin(client, project, source)
    session = upload["id"]
    assert begin(client, project, source)["id"] == session
    assert (
        client.post(
            f"/api/projects/{project}/uploads",
            json={"name": "changed.csv", "size": len(source), "idempotency_key": "one"},
        ).status_code
        == 409
    )
    assert part(client, session, 0, source[:8]).status_code == 200
    assert part(client, session, 0, source[:8]).status_code == 200
    assert part(client, session, 0, b"changed!").status_code == 409
    assert client.post(f"/api/uploads/{session}/complete").status_code == 409
    # New HTTP client recovers server parts; no local file bytes are stored in drafts.
    _, restored, _ = setup(workspace)
    state = restored.get(f"/api/uploads/{session}").json()
    assert state["parts"]["0"]["sha256"] == hashlib.sha256(source[:8]).hexdigest()
    for index, start in enumerate(range(8, len(source), 8), 1):
        assert part(restored, session, index, source[start : start + 8]).status_code == 200
    ready = restored.post(f"/api/uploads/{session}/complete")
    assert ready.status_code == 200, ready.text
    asset = ready.json()["asset"]
    assert asset["sha256"] == hashlib.sha256(source).hexdigest()
    assert restored.get(f"/api/assets/{asset['id']}/download").content == source
    assert restored.post(f"/api/uploads/{session}/complete").json()["asset"]["id"] == asset["id"]
    assert restored.get(f"/api/projects/{project}/tasks").json() == []
    assert restored.get(f"/api/projects/{project}/uploads").json() == []


def test_bad_chunk_bounds_hash_and_owner(workspace):
    store, client, project = setup(workspace)
    source = b"id,v\n001,2\n"
    upload = begin(client, project, source)
    base = f"/api/uploads/{upload['id']}"
    assert part(client, upload["id"], 0, b"too big chunk").status_code == 413
    assert part(client, upload["id"], 9, b"x").status_code == 422
    assert part(client, upload["id"], 0, b"short").status_code == 422
    assert (
        client.post(
            base + "/parts/0", files={"file": ("x", source[:8])}, data={"sha256": "0" * 64}
        ).status_code
        == 422
    )
    assert client.get(base).json()["parts"] == {}
    user = client.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    ).json()
    client.headers["X-CSRF-Token"] = user["csrf"]
    assert client.get(base).status_code == 404
    assert (
        client.post(
            f"/api/projects/{project}/uploads",
            json={"name": "file.csv", "size": 10, "idempotency_key": "bad"},
        ).status_code
        == 403
    )


def test_invalid_file_failure_does_not_remove_other_successes(workspace):
    _, client, project = setup(workspace)
    broken = begin(client, project, b"II*\x00bad", "broken", name="broken.tif")
    assert part(client, broken["id"], 0, b"II*\x00bad").status_code == 200
    assert client.post(f"/api/uploads/{broken['id']}/complete").status_code == 422
    state = client.get(f"/api/uploads/{broken['id']}").json()
    assert state["status"] == "failed" and state["error"]["code"]
    assert state["parts"]["0"]["size"] == 7
    good = b"id,v\n1,2"
    session = begin(client, project, good, "good")
    assert part(client, session["id"], 0, good).status_code == 200
    assert client.post(f"/api/uploads/{session['id']}/complete").status_code == 200
    assert client.get(f"/api/uploads/{broken['id']}").json()["status"] == "failed"


def test_cancel_only_removes_owned_unfinished_parts(workspace):
    store, client, project = setup(workspace)
    content = b"id,v\n1,2"
    session = begin(client, project, content)
    assert part(client, session["id"], 0, content).status_code == 200
    root = store.settings.storage_root / "receiving" / session["id"]
    assert (root / "0").is_file()
    assert client.delete(f"/api/uploads/{session['id']}").status_code == 200
    assert not (root / "0").exists()
    assert part(client, session["id"], 0, content).status_code == 409
    assert client.get(f"/api/projects/{project}/uploads").json() == []
    assert client.post(f"/api/uploads/{session['id']}/complete").status_code == 409


def test_tampered_staging_is_never_registered(workspace):
    store, client, project = setup(workspace)
    content = b"id,v\n1,2"
    session = begin(client, project, content)
    assert part(client, session["id"], 0, content).status_code == 200
    (store.settings.storage_root / "receiving" / session["id"] / "0").write_bytes(b"id,v\n9,9")
    result = client.post(f"/api/uploads/{session['id']}/complete")
    assert result.status_code == 409 and result.json()["code"] == "PART_CHANGED"
    assert client.get(f"/api/projects/{project}/assets").json() == []


def test_disk_budget_checked_before_accepting_upload(workspace, monkeypatch):
    import shutil
    from types import SimpleNamespace

    _, client, project = setup(workspace)
    monkeypatch.setattr(shutil, "disk_usage", lambda _: SimpleNamespace(free=16))
    response = client.post(
        f"/api/projects/{project}/uploads",
        json={"name": "real.csv", "size": 10, "idempotency_key": "low-disk"},
    )
    assert response.status_code == 507
    assert response.json()["code"] == "UPLOAD_DISK_BUDGET"
    assert client.get(f"/api/projects/{project}/uploads").json() == []
