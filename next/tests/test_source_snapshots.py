"""Explicit managed source snapshots; no library enumeration or mutable source links."""

from dataclasses import replace

from fastapi.testclient import TestClient

from coastmas_next.app import create_app
from coastmas_next.store import Store


def environment(workspace, tmp_path):
    settings, _, _, project = workspace
    root = tmp_path / "source"
    root.mkdir()
    (root / "a.csv").write_bytes(b"id,v\n1,2\n")
    settings = replace(settings, local_sources=(root,))
    store = Store(settings)
    client = TestClient(create_app(settings))
    session = client.post(
        "/api/session", json={"email": "admin@example.test", "password": "safe-password-for-tests"}
    ).json()
    client.headers["X-CSRF-Token"] = session["csrf"]
    source = client.get(f"/api/projects/{project}/local-sources").json()[0]["id"]
    assert client.post(f"/api/projects/{project}/local-sources/{source}/grant").status_code == 200
    return settings, store, client, project, root, source


def test_source_queue_replays_without_task_and_original_changes_do_not_change_snapshot(
    workspace, tmp_path
):
    settings, store, client, project, root, source = environment(workspace, tmp_path)
    from coastmas_next.source_snapshots import SourceSnapshots

    before = client.get(f"/api/projects/{project}/assets").json()
    body = {"source_id": source, "paths": ["a.csv"], "idempotency_key": "explicit-import"}
    response = client.post(f"/api/projects/{project}/source-snapshots", json=body)
    assert response.status_code == 201, response.text
    item = response.json()["items"][0]
    assert client.get(f"/api/projects/{project}/assets").json() == before
    assert SourceSnapshots(store).run_once()
    state = client.get(f"/api/projects/{project}/source-snapshots").json()[0]
    assert state["status"] == "ready"
    managed = client.get(f"/api/assets/{state['asset_id']}/download").content
    assert managed == b"id,v\n1,2\n"
    (root / "a.csv").write_bytes(b"id,v\n1,9\n")
    assert client.get(f"/api/assets/{state['asset_id']}/download").content == managed
    replay = client.post(f"/api/projects/{project}/source-snapshots", json=body)
    assert replay.json()["items"][0]["id"] == item["id"]
    assert not SourceSnapshots(store).run_once()
    assert client.get(f"/api/management/catalog/tasks?project={project}").json()["total"] == 0


def test_group_source_snapshot_and_revocation_fail_closed(workspace, tmp_path):
    settings, store, client, project, root, source = environment(workspace, tmp_path)
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    from coastmas_next.source_snapshots import SourceSnapshots

    with rasterio.open(
        root / "image.tif",
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(113, 23, 0.01, 0.01),
    ) as image:
        image.write(np.ones((2, 2), dtype="float32"), 1)
    (root / "image.tif.aux.xml").write_text(
        '<PAMDataset><PAMRasterBand band="1"><UnitType>1</UnitType></PAMRasterBand></PAMDataset>'
    )
    reply = client.post(
        f"/api/projects/{project}/source-snapshots",
        json={
            "source_id": source,
            "paths": ["image.tif", "image.tif.aux.xml"],
            "idempotency_key": "group",
        },
    )
    assert reply.status_code == 201, reply.text
    assert len(reply.json()["items"]) == 1
    assert SourceSnapshots(store).run_once()
    record = client.get(f"/api/projects/{project}/source-snapshots").json()[0]
    assert record["status"] == "ready"
    asset = client.get(f"/api/assets/{record['asset_id']}").json()
    assert len(asset["facts"]["logical_package"]["members"]) == 2
    client.post(
        f"/api/projects/{project}/source-snapshots",
        json={"source_id": source, "paths": ["a.csv"], "idempotency_key": "revoke"},
    )
    client.delete(f"/api/projects/{project}/local-sources/{source}/grant")
    assert SourceSnapshots(store).run_once()
    failed = client.get(f"/api/projects/{project}/source-snapshots").json()[0]
    assert failed["status"] == "failed" and failed["error"]["code"] == "SOURCE_NOT_AUTHORIZED"
    assert failed["asset_id"] is None


def test_grant_revoked_at_actual_registration_prevents_csv_commit(workspace, tmp_path, monkeypatch):
    _, store, client, project, _, source = environment(workspace, tmp_path)
    from sqlalchemy import delete

    from coastmas_next.batches import source_grants
    from coastmas_next.intake import Intake
    from coastmas_next.source_snapshots import SourceSnapshots

    client.post(
        f"/api/projects/{project}/source-snapshots",
        json={"source_id": source, "paths": ["a.csv"], "idempotency_key": "commit-race"},
    )
    original = Intake.ingest

    def revoke(self, *args, **kwargs):
        with store.engine.begin() as c:
            c.execute(delete(source_grants).where(source_grants.c.project_id == project))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Intake, "ingest", revoke)
    assert SourceSnapshots(store).run_once()
    state = client.get(f"/api/projects/{project}/source-snapshots").json()[0]
    assert state["status"] == "failed" and state["error"]["code"] == "SOURCE_NOT_AUTHORIZED"
    assert client.get(f"/api/projects/{project}/catalog").json()["total"] == 0
