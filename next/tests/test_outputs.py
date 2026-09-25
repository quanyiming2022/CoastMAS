"""Scientific previews and complete export preserve data and disclose bounded display."""

import io
import json
import zipfile

import numpy as np
import rasterio
from coastmas_next.worker import Worker
from rasterio.transform import from_origin


def test_actual_raster_preview_has_georeference_and_transparent_nodata(workspace, tmp_path):
    _, _, client, project = workspace
    path = tmp_path / "actual.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(110, 23, 0.01, 0.01),
        nodata=-9999,
    ) as ds:
        values = np.arange(16, dtype="float32").reshape(4, 4)
        values[0, 0] = -9999
        ds.write(values, 1)
    with path.open("rb") as source:
        asset = client.post(
            f"/api/projects/{project}/assets", files={"file": ("real.tif", source)}
        ).json()["asset"]
    metadata = client.get(f"/api/assets/{asset['id']}/preview")
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["scope"] == "bounded_display_not_full_statistics"
    assert len(metadata.json()["coordinates"]) == 4
    png = client.get(f"/api/assets/{asset['id']}/preview.png")
    assert png.status_code == 200
    with rasterio.io.MemoryFile(png.content) as memory:
        with memory.open() as image:
            assert image.count == 4
            assert image.read(4).min() == 0


def test_geojson_result_bundle_contains_full_features_and_frozen_provenance(workspace):
    _, store, client, project = workspace
    source = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "001",
                "properties": {"value": 0},
                "geometry": {"type": "Point", "coordinates": [110, 23]},
            }
        ],
    }
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "Entity outputs", "purpose": "entities"}
    ).json()
    task = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("entities.geojson", json.dumps(source).encode())},
        data={"task_id": task["id"], "expected_revision": "1"},
    ).json()["task"]
    job = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "export"},
    ).json()
    assert Worker(store).run_once()
    reply = client.get(f"/api/jobs/{job['id']}/bundle")
    assert reply.status_code == 200, reply.text
    with zipfile.ZipFile(io.BytesIO(reply.content)) as archive:
        geojson = json.loads(archive.read("entities.geojson"))
        assert geojson["features"][0]["id"] == "001"
        assert geojson["features"][0]["properties"]["value"] == 0
        complete = json.loads(archive.read("result.json"))
        assert complete["manifest"]["assets"][0]["sha256"]
        assert complete["states"]["business_validated"] is False


def test_infeasible_allocation_export_retains_unknown_selection(workspace, tmp_path):
    from coastmas_next.outputs import bundle

    _, store, _, _ = workspace
    result = {
        "data": {
            "row_ids": ["001"],
            "allocations": [
                {
                    "id": "001",
                    "allowed": True,
                    "selected": None,
                    "benefit": 4,
                    "cost": 2,
                    "area": 3,
                    "ecological_cost": 0,
                    "risk": 0,
                }
            ],
        }
    }
    original = tmp_path / "actual-result.json"
    original.write_text(json.dumps(result))
    archive_path = bundle(store, {}, result, original)
    with zipfile.ZipFile(archive_path) as archive:
        import csv

        rows = list(
            csv.DictReader(io.StringIO(archive.read("allocations.csv").decode("utf-8-sig")))
        )
        assert rows[0]["selected"] == ""
        assert rows[0]["allowed"] == "true"
        metadata = json.loads(archive.read("allocations.csv-metadata.json"))
        selected = next(c for c in metadata["tableSchema"]["columns"] if c["name"] == "selected")
        assert selected["null"] == [""]
    archive_path.unlink()
