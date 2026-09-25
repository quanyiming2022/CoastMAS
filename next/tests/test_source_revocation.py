"""Revoking a local grant stops new ingestion without deleting managed assets."""

from dataclasses import replace

import pytest
from coastmas_next.app import create_app
from coastmas_next.batches import BatchIntake
from coastmas_next.store import Problem, Store
from fastapi.testclient import TestClient


@pytest.mark.parametrize("when", ["queued", "during_read"])
def test_source_revocation_stops_queued_curator_reads_and_preserves_assets(
    workspace, tmp_path, monkeypatch, when
):
    settings, old_store, old_client, project = workspace
    root = tmp_path / "authorized"
    root.mkdir()
    (root / "first.csv").write_bytes(b"id,v\n1,2\n")
    (root / "second.csv").write_bytes(b"id,v\n3,4\n")
    settings = replace(settings, local_sources=(root,))
    store = Store(settings)
    client = TestClient(create_app(settings))

    def login(email):
        response = client.post(
            "/api/session", json={"email": email, "password": "safe-password-for-tests"}
        )
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        return response.json()["user"]["id"]

    admin = login("admin@example.test")
    curator = store.create_account("curator@example.test", "safe-password-for-tests")
    store.set_member(admin, project, curator, "curator")
    source = client.get(f"/api/projects/{project}/local-sources").json()[0]
    assert source["granted"] is False
    with pytest.raises(Problem) as denied:
        BatchIntake(store).browse(admin, project, source["id"])
    assert denied.value.code == "SOURCE_NOT_AUTHORIZED"
    path = f"/api/projects/{project}/local-sources/{source['id']}/grant"
    assert client.post(path).json()["granted"] is True
    login("curator@example.test")
    assert client.delete(path).status_code == 403
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Revocable sources", "purpose": "inspect"},
    ).json()
    batch = client.post(
        f"/api/projects/{project}/imports",
        json={
            "task_id": task["id"],
            "idempotency_key": "revocation",
            "items": [
                {"name": name, "path": name, "size": 9, "source_id": source["id"]}
                for name in ["first.csv", "second.csv"]
            ],
        },
    ).json()
    service = BatchIntake(store)
    assert service.run_once()
    state = service.read(curator, batch["id"])
    ready = next(item for item in state["items"] if item["status"] == "ready")
    login("admin@example.test")
    if when == "queued":
        assert client.delete(path).json()["granted"] is False
    else:
        original_ingest = service.intake.ingest

        def revoke_while_open(*args, **kwargs):
            assert client.delete(path).json()["granted"] is False
            return original_ingest(*args, **kwargs)

        monkeypatch.setattr(service.intake, "ingest", revoke_while_open)
    assert service.run_once()
    assert client.delete(path).status_code == 200
    assert client.get(f"/api/projects/{project}/local-sources").json()[0]["granted"] is False
    login("curator@example.test")
    assert client.get(f"/api/projects/{project}/local-sources").json() == []
    state = service.read(curator, batch["id"])
    assert sorted(item["status"] for item in state["items"]) == ["failed", "ready"]
    assert client.get(f"/api/assets/{ready['asset_id']}/download").status_code == 200
    assert (root / "first.csv").read_bytes() == b"id,v\n1,2\n"
    assert (root / "second.csv").read_bytes() == b"id,v\n3,4\n"
    login("admin@example.test")
    actions = [
        item["action"] for item in client.get(f"/api/projects/{project}/audit").json()["items"]
    ]
    assert actions.count("revoke_local_source") == 1
