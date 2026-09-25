"""Actual full-grid spatial output, fixed-run viewer, and enforced output contract."""

import hashlib
from threading import Event

import numpy as np
import pytest
import rasterio
from coastmas_next.store import Problem
from coastmas_next.worker import Worker
from rasterio.transform import from_origin


def prepare(workspace, tmp_path, crs="EPSG:4326"):
    _, _, client, project = workspace
    path = tmp_path / "grid.tif"
    values = np.array([[0, -1, -9999], [3, np.nan, 6]], dtype="float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=3,
        height=2,
        count=1,
        dtype="float32",
        crs=crs,
        transform=from_origin(110, 24, 0.1, 0.1),
        nodata=-9999,
    ) as ds:
        ds.write(values, 1)
    a = client.post(
        f"/api/projects/{project}/assets", files={"file": ("grid.tif", path.read_bytes())}
    ).json()["asset"]
    t = client.post(
        "/api/tasks", json={"project_id": project, "title": "覆盖检查", "purpose": "spatial"}
    )
    assert t.status_code == 201, t.text
    task = t.json()
    attached = client.post(
        f"/api/tasks/{task['id']}/sources", json={"expected_revision": 1, "assets": [a["id"]]}
    ).json()
    draft = attached["draft"]
    draft["options"] = {"operator": "valid_mask", "band": 1}
    saved = client.put(
        f"/api/tasks/{task['id']}", json={"expected_revision": 2, "draft": draft}
    ).json()
    return saved, a, values


def test_full_mask_result_descriptor_inspection_and_download(workspace, tmp_path):
    settings, store, client, _ = workspace
    task, source, _ = prepare(workspace, tmp_path)
    preflight = client.get(f"/api/tasks/{task['id']}/preflight").json()
    assert preflight["ready"], preflight
    response = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "coverage"},
    )
    assert response.status_code == 202, response.text
    job = response.json()
    assert Worker(store).run_once()
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "succeeded"
    result = client.get(f"/api/jobs/{job['id']}/result").json()
    data = result["data"]
    assert data["statistics"] == {
        "total_pixels": 6,
        "valid_pixels": 4,
        "invalid_pixels": 2,
        "scope": "full_grid",
    }
    output = data["files"][0]
    assert output["sha256"] != source["sha256"]
    with rasterio.open(settings.storage_root / output["key"]) as ds:
        assert ds.read(1).tolist() == [[1, 1, 0], [1, 0, 1]]
        assert ds.crs.to_string() == "EPSG:4326"
        assert list(ds.transform)[:6] == [0.1, 0, 110, 0, -0.1, 24]
        assert ds.nodata is None  # invalid source coverage is valid output category zero
    descriptor = client.get(f"/api/jobs/{job['id']}/descriptor").json()
    assert descriptor["run_id"] == job["id"] and descriptor["primary"]["sha256"] == output["sha256"]
    assert (
        descriptor["primary"]["role"] == "result" and descriptor["primary"]["view_kind"] == "raster"
    )
    root = descriptor["primary"]["resource"]
    assert root.startswith(f"/jobs/{job['id']}/artifacts/")
    assert client.get("/api" + root + "/view").json()["sha256"] == output["sha256"]
    pixel = client.post(
        "/api" + root + "/inspect", json={"longitude": 110.25, "latitude": 23.95, "band": 1}
    ).json()
    assert pixel["valid"] is True and pixel["value"] == 0
    download = client.get("/api" + root + "/download")
    assert hashlib.sha256(download.content).hexdigest() == output["sha256"]
    assert client.get("/api" + root + "/tiles/0/0/0.png").headers["content-type"] == "image/png"
    assert result["states"]["business_validated"] is False


def test_unknown_location_only_blocks_georeferenced_analysis_not_source_read(workspace, tmp_path):
    _, _, client, _ = workspace
    task, a, _ = prepare(workspace, tmp_path, crs=None)
    check = client.get(f"/api/tasks/{task['id']}/preflight").json()
    assert not check["ready"] and any(i["code"] == "SPATIAL_LOCATION" for i in check["issues"])
    assert client.get(f"/api/assets/{a['id']}/view.png").status_code == 200


def test_missing_or_mismatched_expected_output_cannot_publish(workspace, tmp_path):
    from coastmas_next.spatial import validate_outputs

    _, _, client, _ = workspace
    task, a, _ = prepare(workspace, tmp_path)
    manifest = {"draft": task["draft"], "assets": [a]}
    with pytest.raises(Problem) as error:
        validate_outputs(manifest, {"files": []}, tmp_path)
    assert error.value.code == "OUTPUT_CONTRACT"
    cancelled = Event()
    cancelled.set()
    from coastmas_next.spatial import compute

    with pytest.raises(Problem) as stopped:
        compute(workspace[0], manifest, cancelled, tmp_path / "out")
    assert stopped.value.code == "CANCELLED"


def test_start_from_selected_asset_is_saved_atomic_and_retryable(workspace, tmp_path):
    _, store, client, project = workspace
    _, source, _ = prepare(workspace, tmp_path)
    body = {"asset_id": source["id"], "band": 1, "idempotency_key": "start-mask-once"}
    first = client.post(f"/api/projects/{project}/spatial-tasks", json=body)
    assert first.status_code == 201, first.text
    task = first.json()
    assert task["revision"] == 1 and task["draft"]["title"].startswith("有效覆盖")
    assert task["draft"]["selection"] == [{"asset_id": source["id"], "revision": 1, "layer": None}]
    replay = client.post(f"/api/projects/{project}/spatial-tasks", json=body)
    assert replay.json()["id"] == task["id"]
    changed = client.post(f"/api/projects/{project}/spatial-tasks", json={**body, "band": 2})
    assert changed.status_code in {409, 422}
    assert client.get(f"/api/tasks/{task['id']}").json()["draft"] == task["draft"]


def test_result_view_is_private_persistent_and_does_not_change_frozen_run(workspace, tmp_path):
    settings, store, client, _ = workspace
    task, _, _ = prepare(workspace, tmp_path)
    job = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "view"},
    ).json()
    assert Worker(store).run_once()
    before = client.get(f"/api/jobs/{job['id']}/result").content
    url = f"/api/jobs/{job['id']}/view-state"
    state = {
        "asset_id": None,
        "band": 1,
        "camera": {"longitude": 110, "latitude": 24, "zoom": 9},
        "visible": False,
        "opacity": 0.3,
    }
    saved = client.put(url, json={"expected_revision": 0, "state": state})
    assert saved.status_code == 200, saved.text
    from coastmas_next.store import Store

    Store(settings).initialize()
    assert client.get(url).json()["state"] == state
    assert client.put(url, json={"expected_revision": 0, "state": state}).status_code == 409
    assert client.get(f"/api/jobs/{job['id']}/result").content == before
    login = client.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    ).json()
    client.headers["X-CSRF-Token"] = login["csrf"]
    assert client.get(url).json()["state"] is None
    assert client.put(url, json={"expected_revision": 0, "state": state}).status_code == 200


def test_blank_spatial_task_has_explicit_default_tool_before_source_choice(workspace):
    _, _, client, project = workspace
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "资料稍后选择", "purpose": "spatial"}
    ).json()
    assert task["draft"]["options"] == {"operator": "valid_mask", "band": 1}
    assert task["draft"]["selection"] == []
    check = client.get(f"/api/tasks/{task['id']}/preflight").json()
    assert not check["ready"] and any(issue["code"] == "DATA_REQUIRED" for issue in check["issues"])
