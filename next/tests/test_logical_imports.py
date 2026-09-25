import hashlib
import io

import numpy as np
import rasterio
from affine import Affine

from coastmas_next.upload_sessions import NewUpload, Uploads


def tiff(tmp_path, name="coast.tif", crs="EPSG:4326", transform=None):
    path = tmp_path / name
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=4,
        height=3,
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform or Affine(1, 0, 110, 0, -1, 24),
    ) as ds:
        ds.write(np.arange(12, dtype="float32").reshape(3, 4), 1)
    return path.read_bytes()


def staged(workspace, files):
    _, store, client, project = workspace
    actor = client.get("/api/session").json()["id"]
    service = Uploads(store)
    result = []
    for path, data in files:
        row = service.create(
            actor,
            project,
            NewUpload(
                name=path.split("/")[-1],
                size=len(data),
                idempotency_key=hashlib.sha256(
                    (path + str(len(result))).encode() + data
                ).hexdigest(),
            ),
        )
        service.part(actor, row["id"], 0, io.BytesIO(data), hashlib.sha256(data).hexdigest())
        result.append({"upload_id": row["id"], "relative_path": path})
    return result


def complete(workspace, files, key="group", previous=None):
    _, _, client, project = workspace
    body = {
        "idempotency_key": key,
        "members": staged(workspace, files),
        "previous_asset_id": previous,
    }
    return client.post(f"/api/projects/{project}/logical-imports", json=body), body


def test_four_members_one_asset_native_values_and_replay(workspace, tmp_path):
    settings, _, client, project = workspace
    data = tiff(tmp_path)
    response, body = complete(
        workspace,
        [
            ("a/coast.tif", data),
            ("a/coast.tfw", b"1\n0\n0\n-1\n110.5\n23.5\n"),
            (
                "a/coast.tif.aux.xml",
                (
                    b'<PAMDataset><PAMRasterBand band="1"><UnitType>m</UnitType>'
                    b"</PAMRasterBand></PAMDataset>"
                ),
            ),
            ("a/coast.tif.ovr", b"corrupt optional overview"),
        ],
    )
    assert response.status_code == 201, response.text
    asset = response.json()["asset"]
    package = asset["facts"]["logical_package"]
    assert len(package["members"]) == 4
    assert package["members"][-1]["role"] == "unused_overview"
    assert client.get(f"/api/projects/{project}/catalog").json()["total"] == 1
    assert (
        client.post(f"/api/projects/{project}/logical-imports", json=body).json() == response.json()
    )
    point = client.post(
        f"/api/assets/{asset['id']}/inspect", json={"longitude": 111.5, "latitude": 22.5}
    ).json()
    assert point["stored_value"] == 5 and point["unit"] == "m"
    for member in package["members"]:
        assert (
            hashlib.sha256((settings.storage_root / member["object_key"]).read_bytes()).hexdigest()
            == member["sha256"]
        )
    assert client.get(f"/api/projects/{project}/tasks").json() == []


def test_worldfile_rotation_center_and_unknown_crs_are_not_guessed(workspace, tmp_path):
    _, _, client, _ = workspace
    data = tiff(tmp_path, crs=None, transform=Affine.identity())
    response, _ = complete(
        workspace, [("coast.tif", data), ("coast.tfw", b"2\n0.5\n0.25\n-2\n100\n200\n")]
    )
    assert response.status_code == 201, response.text
    asset = response.json()["asset"]
    assert asset["facts"]["crs"] is None
    assert asset["facts"]["transform"] == [2, 0.25, 98.875, 0.5, -2, 200.75]
    descriptor = client.get(f"/api/assets/{asset['id']}/view").json()
    assert descriptor["georeference_status"] != "located"
    assert descriptor["bounds"] is None


def test_orphans_cross_directory_and_unsafe_xml_do_not_enter_library(workspace, tmp_path):
    _, _, client, project = workspace
    response, _ = complete(workspace, [("lonely.tfw", b"1\n0\n0\n-1\n10\n20\n")])
    assert response.status_code == 422 and response.json()["code"] == "SIDECAR_REQUIRES_PRIMARY"
    response, _ = complete(
        workspace,
        [("a/coast.tif", tiff(tmp_path)), ("b/coast.tfw", b"1\n0\n0\n-1\n10\n20\n")],
        key="other",
    )
    assert response.status_code == 422 and response.json()["code"] == "PACKAGE_ASSOCIATION"
    xml = b'<!DOCTYPE x [<!ENTITY steal SYSTEM "file:///etc/passwd">]><PAMDataset><SRS>&steal;</SRS></PAMDataset>'
    response, _ = complete(
        workspace, [("coast.tif", tiff(tmp_path)), ("coast.tif.aux.xml", xml)], key="unsafe"
    )
    assert response.status_code == 422 and response.json()["code"] == "PAM_UNSAFE_OR_INVALID"
    assert client.get(f"/api/projects/{project}/catalog").json()["total"] == 0


def test_conflicting_georeference_and_wrong_mask_not_silently_ignored(workspace, tmp_path):
    response, _ = complete(
        workspace, [("coast.tif", tiff(tmp_path)), ("coast.tfw", b"1\n0\n0\n-1\n0\n0\n")]
    )
    assert response.status_code == 422 and response.json()["code"] == "LOCATION_CONFLICT"
    _, _, client, project = workspace
    assert client.get(f"/api/projects/{project}/catalog").json()["total"] == 0


def test_standalone_sidecar_is_not_a_csv_or_a_new_indicator(workspace):
    _, _, client, project = workspace
    response = client.post(
        f"/api/projects/{project}/assets", files={"file": ("lonely.tfw", b"1\n0\n0\n-1\n10\n20\n")}
    )
    assert response.status_code == 422 and response.json()["code"] == "SIDECAR_REQUIRES_PRIMARY"


def test_sidecar_reader_integrity_preserves_original_identity(workspace, tmp_path):
    import threading

    import pytest

    from coastmas_next.store import Problem
    from coastmas_next.worker import Worker

    settings, store, client, project = workspace
    raw = tiff(tmp_path, crs=None, transform=Affine.identity())
    response, _ = complete(
        workspace, [("coast.tif", raw), ("coast.tfw", b"2\n0.5\n0.25\n-2\n100\n200\n")]
    )
    assert response.status_code == 201, response.text
    asset = response.json()["asset"]
    manifest = {
        "actor": client.get("/api/session").json()["id"],
        "project_id": project,
        "draft": {"purpose": "inspect"},
        "assets": [asset],
    }
    assert (
        Worker(store).compute(manifest, threading.Event())["datasets"][0]["sha256"]
        == hashlib.sha256(raw).hexdigest()
    )
    member = next(
        m for m in asset["facts"]["logical_package"]["members"] if m["path"].endswith(".tfw")
    )
    (settings.storage_root / member["object_key"]).write_bytes(b"altered")
    with pytest.raises(Problem) as error:
        Worker(store).compute(manifest, threading.Event())
    assert error.value.code == "INPUT_INTEGRITY"
