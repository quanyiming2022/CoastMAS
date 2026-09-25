"""Real preparation operators are independent of evaluation approval and keep task identity."""

import io

import numpy as np
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import func, select

from coastmas_next.store import tasks
from coastmas_next.worker import Worker


def raster(client, project, values, transform=None, name="影像.tif"):
    data = np.asarray(values, dtype="float32")
    if data.ndim == 2:
        data = data[None]
    with rasterio.MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            width=data.shape[2],
            height=data.shape[1],
            count=data.shape[0],
            dtype="float32",
            crs="EPSG:32649",
            transform=transform or from_origin(400000, 2500000, 30, 30),
            nodata=-9999,
        ) as ds:
            ds.write(data)
        payload = memory.read()
    r = client.post(
        f"/api/projects/{project}/assets", files={"file": (name, io.BytesIO(payload), "image/tiff")}
    )
    assert r.status_code == 201, r.text
    return r.json()["asset"]


def research(client, project, assets):
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "goal": "comprehensive-assessment", "title": "独立空间准备"},
    ).json()
    r = client.post(
        f"/api/tasks/{task['id']}/inputs:attach",
        json={
            "expected_revision": 1,
            "idempotency_key": "sources",
            "inputs": [{"asset_id": a["id"], "revision": 1} for a in assets],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["task"]


def execute(client, store, task, asset, operator, parameters):
    node = client.post(
        f"/api/tasks/{task['id']}/processing-nodes",
        json={
            "expected_revision": task["revision"],
            "asset_id": asset["id"],
            "operator": operator,
            "parameters": parameters,
            "idempotency_key": operator,
        },
    )
    assert node.status_code == 201, node.text
    reply = client.post(
        f"/api/processing-nodes/{node.json()['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": operator},
    )
    assert reply.status_code == 202, reply.text
    worker = Worker(store)
    assert worker.run_once()
    result = client.get(f"/api/jobs/{reply.json()['id']}/result")
    assert result.status_code == 200, result.text
    return result.json()["data"]


def test_ndvi_from_actual_multiband_source_without_evaluation_method(workspace):
    settings, store, client, project = workspace
    source = raster(client, project, [[[1, 2, -9999], [0, 4, 2]], [[3, 2, 8], [0, 0, 6]]])
    task = research(client, project, [source])
    assert client.get(f"/api/tasks/{task['id']}/preflight").json()["ready"] is False
    result = execute(
        client,
        store,
        task,
        source,
        "ndvi",
        {"red_band": 1, "nir_band": 2, "qa_policy": "source_mask"},
    )
    with rasterio.open(settings.storage_root / result["files"][0]["key"]) as ds:
        got = ds.read(1, masked=True)
        np.testing.assert_allclose(got.compressed(), [0.5, 0, -1, 0.5])
        assert got.mask.tolist() == [[False, False, True], [True, False, False]]
        assert ds.units[0] == "1"
    assert result["statistics"]["total_pixels"] == 6 and result["statistics"]["valid_pixels"] == 4
    assert client.get("/api/tasks/" + task["id"]).json() == task
    with store.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(tasks)) == 1


def test_alignment_uses_reference_grid_and_rejects_interpolated_categories(workspace):
    settings, store, client, project = workspace
    source = raster(client, project, [[1, 2], [3, 4]], name="类别.tif")
    reference = raster(
        client, project, np.ones((4, 4)), from_origin(400000, 2500000, 15, 15), "参考.tif"
    )
    task = research(client, project, [source, reference])
    result = execute(
        client,
        store,
        task,
        source,
        "align_grid",
        {
            "reference_asset_id": reference["id"],
            "quantity_kind": "category",
            "resampling": "nearest",
        },
    )
    with rasterio.open(settings.storage_root / result["files"][0]["key"]) as ds:
        np.testing.assert_array_equal(
            ds.read(1), [[1, 1, 2, 2], [1, 1, 2, 2], [3, 3, 4, 4], [3, 3, 4, 4]]
        )
        assert tuple(ds.transform) == tuple(from_origin(400000, 2500000, 15, 15))
    node = client.post(
        f"/api/tasks/{task['id']}/processing-nodes",
        json={
            "expected_revision": task["revision"],
            "asset_id": source["id"],
            "operator": "align_grid",
            "parameters": {
                "reference_asset_id": reference["id"],
                "quantity_kind": "category",
                "resampling": "bilinear",
            },
            "idempotency_key": "invalid-category",
        },
    )
    assert node.status_code == 422 and node.json()["code"] == "CATEGORY_RESAMPLING"
