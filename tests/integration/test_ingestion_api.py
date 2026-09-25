import hashlib
import json
from uuid import uuid4

import numpy as np
import rasterio
from rasterio.transform import from_origin


def raster_file(path):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=3,
        height=2,
        count=1,
        dtype="int8",
        crs="EPSG:4326",
        transform=from_origin(110, 30, 0.01, 0.01),
        nodata=-128,
    ) as dataset:
        dataset.write(np.array([[0, -1, 2], [-128, 1, 0]], dtype="int8"), 1)
    return path.read_bytes()


def test_ingest_missing_science_creates_real_asset_with_exact_download(
    authenticated, storage, tmp_path
):
    client, csrf, project, _ = authenticated
    client.app.state.artifact_store = storage
    content = raster_file(tmp_path / "raw.tif")
    response = client.post(
        "/api/v1/data-assets/ingest",
        headers={"X-CSRF-Token": csrf},
        data={
            "project_id": project,
            "declaration": json.dumps(
                {"name": "真实栅格", "source": "公开网站", "license": "非商业", "year": 2022}
            ),
        },
        files={"file": ("source.tif", content, "image/tiff")},
    )
    assert response.status_code == 201, response.text
    spec = response.json()["spec"]
    assert spec["variables"] == []
    assert spec["time_start"] is None and spec["time_end"] is None
    assert spec["quality"]["validated"] is False
    assert spec["quality"]["ingestion_state"] == "INGESTED_PENDING_MAPPING"
    assert spec["crs"] == "EPSG:4326"
    assert spec["checksum"] == hashlib.sha256(content).hexdigest()
    assert spec["quality"]["declarations"]["year"] == 2022
    assert client.get(f"/api/v1/data-assets/{spec['id']}/download").content == content
    preview = client.get(f"/api/v1/data-assets/{spec['id']}/preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["preview"]["values"] == [[0, -1, 2], [None, 1, 0]]
    assert preview.json()["metadata"]["validated"] is False


def test_local_ingest_is_project_scoped_and_rejects_path_escape(
    authenticated, storage, tmp_path, monkeypatch
):
    client, csrf, project, _ = authenticated
    client.app.state.artifact_store = storage
    root = tmp_path / "allowed"
    root.mkdir()
    content = raster_file(root / "data.tif")
    (root / "link.tif").symlink_to(root / "data.tif")
    monkeypatch.setenv(
        "COASTMAS_LOCAL_IMPORT_ROOTS",
        json.dumps({"business": {"path": str(root), "project_ids": [project]}}),
    )
    params = {"project_id": project, "source": "business"}
    listed = client.get("/api/v1/data-assets/local-files", params=params)
    assert listed.status_code == 200, listed.text
    assert [f["path"] for f in listed.json()["files"]] == ["data.tif"]
    assert str(root) not in listed.text
    headers = {"X-CSRF-Token": csrf}
    body = {
        **params,
        "path": "data.tif",
        "declaration": {
            "name": "Local source",
            "source": "user provided",
            "license": "noncommercial",
        },
    }
    for path in ["../data.tif", str(root / "data.tif"), "link.tif"]:
        response = client.post(
            "/api/v1/data-assets/ingest-local", headers=headers, json={**body, "path": path}
        )
        assert response.status_code in (403, 422), response.text
    imported = client.post("/api/v1/data-assets/ingest-local", headers=headers, json=body)
    assert imported.status_code == 201, imported.text
    assert imported.json()["spec"]["checksum"] == hashlib.sha256(content).hexdigest()
    denied = client.get(
        "/api/v1/data-assets/local-files", params={**params, "project_id": str(uuid4())}
    )
    assert denied.status_code == 403
    assert (root / "data.tif").read_bytes() == content


def test_mapping_requires_actual_units_and_preserves_zero_nodata(authenticated, storage, tmp_path):
    from tests.factories import asset, variable

    client, csrf, project, _ = authenticated
    client.app.state.artifact_store = storage
    content = raster_file(tmp_path / "mapped.tif")
    declared = asset(
        id=uuid4().hex,
        crs="EPSG:4326",
        spatial_extent=None,
        vertical_datum=None,
        variables=[variable(nodata_policy="mask")],
    )
    uploaded = client.post(
        "/api/v1/data-assets/upload",
        headers={"X-CSRF-Token": csrf},
        data={"project_id": project, "metadata": declared.model_dump_json()},
        files={"file": ("mapped.tif", content, "image/tiff")},
    )
    assert uploaded.status_code == 201, uploaded.text
    quality = uploaded.json()["spec"]["quality"]
    assert quality["unit_source"] == "catalog_declaration"
    assert quality["valid_cells"] == 5 and quality["nodata_cells"] == 1
    assert quality["minimum"] == -1 and quality["maximum"] == 2
    assert quality["validated"] is True
    rejected = declared.model_copy(
        update={"id": uuid4().hex, "variables": [variable(nodata_policy="reject")]}
    )
    invalid = client.post(
        "/api/v1/data-assets/upload",
        headers={"X-CSRF-Token": csrf},
        data={"project_id": project, "metadata": rejected.model_dump_json()},
        files={"file": ("mapped.tif", content, "image/tiff")},
    )
    assert invalid.status_code == 422


def test_large_nodata_jsonb_roundtrip_preserves_resource_integrity(
    authenticated, storage, tmp_path
):
    client, csrf, project, _ = authenticated
    client.app.state.artifact_store = storage
    path = tmp_path / "float.tif"
    nodata = -3.4028230607370965e38
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=2,
        height=1,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(110, 30, 0.01, 0.01),
        nodata=nodata,
    ) as dataset:
        dataset.write(np.array([[0, nodata]], dtype="float32"), 1)
    created = client.post(
        "/api/v1/data-assets/ingest",
        headers={"X-CSRF-Token": csrf},
        data={
            "project_id": project,
            "declaration": json.dumps(
                {"name": "large NoData", "source": "test", "license": "test"}
            ),
        },
        files={"file": ("float.tif", path.read_bytes(), "image/tiff")},
    )
    assert created.status_code == 201, created.text
    identifier = created.json()["resource_id"]
    loaded = client.get(f"/api/v1/data-assets/{identifier}")
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["checksum"] == created.json()["checksum"]
