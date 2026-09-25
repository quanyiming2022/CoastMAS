import hashlib
from io import BytesIO
from zipfile import ZipFile

from test_logical_imports import tiff


def test_group_resume_and_supplement_keep_received_parts_and_original_download(workspace, tmp_path):
    _, _, client, project = workspace
    xml = b'<PAMDataset><PAMRasterBand band="1"><UnitType>m</UnitType></PAMRasterBand></PAMDataset>'
    created = client.post(
        f"/api/projects/{project}/upload-groups",
        json={
            "idempotency_key": "resume",
            "files": [{"relative_path": "coast.tif.aux.xml", "size": len(xml)}],
        },
    )
    assert created.status_code == 201, created.text
    group = created.json()
    member = group["members"][0]
    response = client.post(
        f"/api/uploads/{member['upload_id']}/parts/0",
        files={"file": ("part", xml)},
        data={"sha256": hashlib.sha256(xml).hexdigest()},
    )
    assert response.status_code == 200, response.text
    missing = client.post(f"/api/upload-groups/{group['id']}/complete")
    assert missing.status_code == 422 and missing.json()["code"] == "SIDECAR_REQUIRES_PRIMARY"
    recovered = client.get(f"/api/projects/{project}/upload-groups").json()[0]
    assert recovered["members"][0]["upload"]["received_bytes"] == len(xml)
    raw = tiff(tmp_path)
    supplemented = client.post(
        f"/api/upload-groups/{group['id']}/members",
        json={
            "idempotency_key": "main",
            "files": [{"relative_path": "coast.tif", "size": len(raw)}],
        },
    )
    assert supplemented.status_code == 200, supplemented.text
    main = supplemented.json()["members"][1]
    response = client.post(
        f"/api/uploads/{main['upload_id']}/parts/0",
        files={"file": ("part", raw)},
        data={"sha256": hashlib.sha256(raw).hexdigest()},
    )
    assert response.status_code == 200, response.text
    ready = client.post(f"/api/upload-groups/{group['id']}/complete")
    assert ready.status_code == 200, ready.text
    assert client.post(f"/api/upload-groups/{group['id']}/complete").json() == ready.json()
    assert client.get(f"/api/projects/{project}/upload-groups").json() == []
    download = client.get(f"/api/assets/{ready.json()['asset']['id']}/download")
    with ZipFile(BytesIO(download.content)) as archive:
        assert archive.read("coast.tif") == raw
        assert archive.read("coast.tif.aux.xml") == xml
        assert "coastmas-integrity-manifest.json" in archive.namelist()


def test_orphan_world_file_reuses_managed_primary_as_new_version(workspace, tmp_path):
    _, _, client, project = workspace
    raw = tiff(tmp_path)
    original = client.post(
        f"/api/projects/{project}/assets", files={"file": ("coast.tif", raw)}
    ).json()["asset"]
    world = b"1\n0\n0\n-1\n110.5\n23.5\n"
    group = client.post(
        f"/api/projects/{project}/upload-groups",
        json={
            "idempotency_key": "world",
            "files": [{"relative_path": "coast.tfw", "size": len(world)}],
        },
    ).json()
    member = group["members"][0]
    client.post(
        f"/api/uploads/{member['upload_id']}/parts/0",
        files={"file": ("part", world)},
        data={"sha256": hashlib.sha256(world).hexdigest()},
    )
    choices = client.get(f"/api/upload-groups/{group['id']}/primary-candidates")
    assert choices.status_code == 200, choices.text
    assert [x["id"] for x in choices.json()] == [original["id"]]
    linked = client.post(
        f"/api/upload-groups/{group['id']}/primary",
        json={"asset_id": original["id"], "revision": 1},
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["members"][1]["upload"]["received_bytes"] == len(raw)
    ready = client.post(f"/api/upload-groups/{group['id']}/complete")
    assert ready.status_code == 200, ready.text
    asset = ready.json()["asset"]
    assert asset["id"] != original["id"] and asset["revision"] == 2
    assert asset["facts"]["logical_package"]["previous_asset_id"] == original["id"]
    assert client.get("/api/assets/" + original["id"]).json() == original
    assert client.post(f"/api/upload-groups/{group['id']}/complete").json() == ready.json()
    with ZipFile(
        BytesIO(client.get("/api/assets/" + asset["id"] + "/download").content)
    ) as archive:
        assert archive.read("coast.tif") == raw and archive.read("coast.tfw") == world


def test_shapefile_members_are_one_logical_vector_not_table_fragments(workspace, tmp_path):
    import fiona

    _, _, client, project = workspace
    path = tmp_path / "areas.shp"
    with fiona.open(
        path,
        "w",
        driver="ESRI Shapefile",
        schema={"geometry": "Point", "properties": {"value": "float"}},
        crs="EPSG:4326",
    ) as collection:
        collection.write(
            {"geometry": {"type": "Point", "coordinates": (113, 23)}, "properties": {"value": 7.5}}
        )
    selected = [
        p for p in tmp_path.glob("areas.*") if p.suffix in {".shp", ".shx", ".dbf", ".prj", ".cpg"}
    ]
    group = client.post(
        f"/api/projects/{project}/upload-groups",
        json={
            "idempotency_key": "shape",
            "files": [{"relative_path": p.name, "size": p.stat().st_size} for p in selected],
        },
    ).json()
    for member in group["members"]:
        raw = (tmp_path / member["relative_path"]).read_bytes()
        reply = client.post(
            f"/api/uploads/{member['upload_id']}/parts/0",
            files={"file": ("part", raw)},
            data={"sha256": hashlib.sha256(raw).hexdigest()},
        )
        assert reply.status_code == 200
    ready = client.post(f"/api/upload-groups/{group['id']}/complete")
    assert ready.status_code == 200, ready.text
    asset = ready.json()["asset"]
    assert asset["facts"]["profile"] == "shapefile"
    assert asset["facts"]["layers"][0]["row_count"] == 1
    assert len(asset["facts"]["logical_package"]["members"]) == len(selected)
