"""Full-grid and spatial result contracts, independent of preview images."""

import io
import json

import numpy as np
import pytest
import rasterio
from coastmas.domain.assessment import composite, entropy_weights, normalize, topsis
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from coastmas_next.worker import Worker


def configured(
    client,
    project,
    filename,
    content,
    profile,
    indicators,
    mappings,
    method="weighted",
    options=None,
):
    asset = client.post(
        f"/api/projects/{project}/assets", files={"file": (filename, content)}
    ).json()["asset"]
    template = client.post(
        f"/api/projects/{project}/templates",
        json={
            "title": "Explicit engineering reference, not a coastal conclusion",
            "purpose": "method",
            "profiles": [profile],
            "basis": "Independent numerical fixture; no business validity claim",
            "configuration": {"task": "assessment", "method": method, "indicators": indicators},
        },
    ).json()
    assert (
        client.post(f"/api/templates/{template['id']}/approve", json={"revision": 1}).status_code
        == 200
    )
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": filename, "purpose": "assessment"}
    ).json()
    draft = task["draft"]
    draft.update(
        selection=[{"asset_id": asset["id"], "revision": 1}],
        mapping=[{"asset_id": asset["id"], **m} for m in mappings],
        method_id=template["id"],
        options={"method_revision": 1, **(options or {})},
    )
    response = client.put(f"/api/tasks/{task['id']}", json={"expected_revision": 1, "draft": draft})
    assert response.status_code == 200, response.text
    return response.json(), asset


def execute(client, store, task, key="test"):
    response = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": key},
    )
    assert response.status_code == 202, response.text
    assert Worker(store).run_once()
    job = response.json()["id"]
    result = client.get(f"/api/jobs/{job}/result")
    assert result.status_code == 200, client.get(f"/api/jobs/{job}").text
    return job, result.json()["data"]


def raster_bytes(values, transform=None):
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            height=values.shape[1],
            width=values.shape[2],
            count=len(values),
            dtype="float64",
            crs="EPSG:4326",
            transform=transform or from_origin(113, 23, 0.001, 0.001),
            nodata=-999,
        ) as ds:
            ds.write(values)
            for band in range(1, len(values) + 1):
                ds.set_band_unit(band, "m")
        return memory.read()


@pytest.mark.parametrize("method", ["weighted", "entropy", "topsis"])
def test_full_grid_assessment_matches_whole_matrix_not_per_block(workspace, monkeypatch, method):
    from coastmas_next import raster_assessment

    monkeypatch.setattr(raster_assessment, "BLOCK", 2)
    settings, store, client, project = workspace
    values = np.array(
        [
            [[0, 1, 2, 3], [4, -999, 6, 7], [8, 9, 10, 11]],
            [[11, 1, 9, 3], [7, 5, 6, 4], [2, 1, 0, -999]],
        ],
        dtype="float64",
    )
    indicators = [
        {
            "concept": f"i{i}",
            "unit": "m",
            "lower": 0,
            "upper": 11,
            "positive": i == 0,
            **({"weight": (i + 1) / 3} if method != "entropy" else {}),
        }
        for i in range(2)
    ]
    task, _ = configured(
        client,
        project,
        "real-grid.tif",
        raster_bytes(values),
        "geotiff",
        indicators,
        [
            {
                "field": f"raster/band_{i + 1}",
                "concept": f"i{i}",
                "role": "feature",
                "support": "cell",
            }
            for i in range(2)
        ],
        method,
    )
    job, data = execute(client, store, task)
    valid = np.all(values != -999, axis=0)
    matrix = normalize(values[:, valid].T, [0, 0], [11, 11], [True, False])
    weights = entropy_weights(matrix) if method == "entropy" else np.array([1, 2]) / 3
    expected = (
        topsis(matrix, weights, [True, True]) if method == "topsis" else composite(matrix, weights)
    )
    assert data["scope"] == "full_grid"
    assert data["statistics"]["valid_pixels"] == int(valid.sum())
    assert data["statistics"]["total_pixels"] == 12
    np.testing.assert_allclose(data["weights"], weights, rtol=1e-12)
    roles = [f["role"] for f in data["files"]]
    assert roles == [
        "composite",
        "raw_indicator",
        "indicator",
        "contribution",
        "raw_indicator",
        "indicator",
        "contribution",
        "quality",
    ]
    with rasterio.open(settings.storage_root / data["files"][0]["key"]) as ds:
        score = ds.read(1, masked=True)
        assert ds.transform == from_origin(113, 23, 0.001, 0.001)
        assert ds.units == ("1",)
        np.testing.assert_array_equal(~score.mask, valid)
        np.testing.assert_allclose(score.compressed(), expected, rtol=1e-12, atol=1e-12)
    descriptor = client.get(f"/api/jobs/{job}/descriptor").json()
    assert descriptor["primary"]["role"] == "composite"
    assert len(descriptor["outputs"]) == 8
    assert data["method_snapshot"]["id"] == task["draft"]["method_id"]
    for index in range(2):
        raw_file = next(f for f in data["files"] if f["name"] == f"raw-indicator-{index + 1}.tif")
        with rasterio.open(settings.storage_root / raw_file["key"]) as raw:
            original = raw.read(1, masked=True)
            np.testing.assert_array_equal(~original.mask, values[index] != -999)
            np.testing.assert_allclose(original.compressed(), values[index][values[index] != -999])
            assert raw.units == ("m",)
            assert np.isnan(raw.nodata)
        score_file = next(f for f in data["files"] if f["name"] == f"indicator-{index + 1}.tif")
        with rasterio.open(settings.storage_root / score_file["key"]) as normalized:
            np.testing.assert_array_equal(
                ~normalized.read(1, masked=True).mask, values[index] != -999
            )
    assert data["statistics"]["maximum"] == pytest.approx(float(expected.max()))
    downloaded = client.get(f"/api/jobs/{job}/artifacts/0/download")
    with MemoryFile(downloaded.content) as memory, memory.open() as ds:
        np.testing.assert_allclose(ds.read(1, masked=True).compressed(), expected, rtol=1e-12)


def test_vector_scores_preserve_actual_geometry_and_native_source(workspace):
    _, store, client, project = workspace
    content = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "001",
                    "geometry": {"type": "Point", "coordinates": [113, 23]},
                    "properties": {"value": 5},
                },
                {
                    "type": "Feature",
                    "id": "002",
                    "geometry": {"type": "Point", "coordinates": [114, 24]},
                    "properties": {"value": 10},
                },
            ],
        }
    ).encode()
    task, asset = configured(
        client,
        project,
        "measured.geojson",
        content,
        "geojson",
        [
            {
                "concept": "pressure",
                "unit": "1",
                "lower": 0,
                "upper": 10,
                "positive": True,
                "weight": 1,
            }
        ],
        [
            {
                "field": "features/value",
                "concept": "pressure",
                "unit": "1",
                "support": "point",
                "role": "feature",
            }
        ],
    )
    job, data = execute(client, store, task)
    features = data["spatial_result"]["features"]
    assert [f["geometry"]["coordinates"] for f in features] == [[113, 23], [114, 24]]
    assert [f["properties"]["assessment_score"] for f in features] == [0.5, 1]
    assert data["spatial_result"]["source_asset_id"] == asset["id"]
    import zipfile

    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/jobs/{job}/bundle").content)) as archive:
        assert json.loads(archive.read("assessment.geojson"))["features"] == features


def test_csv_spatiality_uses_explicit_coordinates_not_extension(workspace):
    _, store, client, project = workspace
    indicators = [
        {"concept": "pressure", "unit": "1", "lower": 0, "upper": 10, "positive": True, "weight": 1}
    ]
    mappings = [
        {
            "field": "table/value",
            "concept": "pressure",
            "unit": "1",
            "support": "point",
            "role": "feature",
        }
    ]
    task, _ = configured(
        client,
        project,
        "points.csv",
        b"x,y,value\n113,23,5\n114,24,10\n",
        "csv",
        indicators,
        mappings,
    )
    _, plain = execute(client, store, task)
    assert "spatial_result" not in plain
    draft = task["draft"]
    draft["options"]["spatial_reference"] = {
        "x_field": "table/x",
        "y_field": "table/y",
        "crs": "EPSG:4326",
    }
    task = client.put(
        f"/api/tasks/{task['id']}", json={"expected_revision": task["revision"], "draft": draft}
    ).json()
    _, spatial = execute(client, store, task, "located")
    assert len(spatial["spatial_result"]["features"]) == 2
    assert spatial["spatial_result"]["features"][0]["geometry"]["coordinates"] == [113, 23]
    draft["options"]["spatial_reference"]["crs"] = "not-a-crs"
    changed = client.put(
        f"/api/tasks/{task['id']}", json={"expected_revision": task["revision"], "draft": draft}
    ).json()
    check = client.get(f"/api/tasks/{changed['id']}/preflight").json()
    assert not check["ready"]
    assert any(i["code"] == "SPATIAL_REFERENCE" for i in check["issues"])


def test_raster_rejects_outside_reference_without_partial_success(workspace):
    _, store, client, project = workspace
    task, _ = configured(
        client,
        project,
        "outside.tif",
        raster_bytes(np.array([[[0.0, 11.0]]])),
        "geotiff",
        [{"concept": "v", "unit": "m", "lower": 0, "upper": 10, "positive": True, "weight": 1}],
        [{"field": "raster/band_1", "concept": "v", "role": "feature"}],
    )
    run = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "outside"},
    )
    assert run.status_code == 202
    Worker(store).run_once()
    assert client.get(f"/api/jobs/{run.json()['id']}").json()["status"] == "failed"
    assert client.get(f"/api/jobs/{run.json()['id']}/result").status_code != 200


def test_raster_mismatched_grid_and_unknown_units_are_not_adapted_silently(workspace):
    _, _, client, project = workspace
    task, _ = configured(
        client,
        project,
        "grid.tif",
        raster_bytes(np.array([[[0.0, 1.0]]])),
        "geotiff",
        [
            {
                "concept": f"i{i}",
                "unit": "m",
                "lower": 0,
                "upper": 10,
                "positive": True,
                "weight": 0.5,
            }
            for i in range(2)
        ],
        [{"field": "raster/band_1", "concept": "i0", "role": "feature"}],
    )
    shifted = client.post(
        f"/api/projects/{project}/assets",
        files={
            "file": (
                "shifted.tif",
                raster_bytes(np.array([[[0.0, 1.0]]]), from_origin(113.001, 23, 0.001, 0.001)),
            )
        },
    ).json()["asset"]
    draft = task["draft"]
    draft["selection"].append({"asset_id": shifted["id"], "revision": 1})
    draft["mapping"].append(
        {"asset_id": shifted["id"], "field": "raster/band_1", "concept": "i1", "role": "feature"}
    )
    task = client.put(
        f"/api/tasks/{task['id']}", json={"expected_revision": task["revision"], "draft": draft}
    ).json()
    check = client.get(f"/api/tasks/{task['id']}/preflight").json()
    assert not check["ready"]
    assert any(issue["code"] == "GRID_ALIGNMENT_REQUIRED" for issue in check["issues"])
