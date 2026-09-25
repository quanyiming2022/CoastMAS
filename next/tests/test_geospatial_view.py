"""Native data, display masks and personal view state: no scientific task prerequisite."""

import math

import numpy as np
import pytest
import rasterio
from affine import Affine
from coastmas_next.store import tasks
from rasterio.transform import from_origin
from sqlalchemy import func, select


def upload(
    workspace,
    tmp_path,
    values=None,
    *,
    crs="EPSG:4326",
    transform=None,
    nodata=-9999,
    name="view.tif",
):
    _, _, client, project = workspace
    values = np.array([[0, -2, 6], [8, -9999, 10]], dtype="float32") if values is None else values
    path = tmp_path / name
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform or from_origin(110, 23, 0.01, 0.01),
        nodata=nodata,
    ) as ds:
        ds.write(values, 1)
        ds.scales, ds.offsets = (2,), (5,)
    with path.open("rb") as stream:
        reply = client.post(f"/api/projects/{project}/assets", files={"file": (name, stream)})
    assert reply.status_code == 201, reply.text
    return reply.json()["asset"]


def test_view_and_native_inspect_need_no_task_or_science(workspace, tmp_path):
    _, store, client, _ = workspace
    asset = upload(workspace, tmp_path)
    url = f"/api/assets/{asset['id']}"
    reply = client.get(url + "/view")
    assert reply.status_code == 200, reply.text
    view = reply.json()
    assert view["georeference_status"] == "located"
    assert view["unit"] is None
    assert view["asset_revision"] == asset["revision"]
    assert view["sha256"] == asset["sha256"]
    assert view["statistics_scope"] == "bounded_nearest_sample"
    assert view["minimum"] == 1 and view["maximum"] == 25
    assert view["sample_valid_pixels"] == 5
    for col, row, expected in [(0, 0, 0), (1, 0, -2), (2, 1, 10)]:
        result = client.post(
            url + "/inspect",
            json={"longitude": 110 + (col + 0.5) * 0.01, "latitude": 23 - (row + 0.5) * 0.01},
        ).json()
        assert result["valid"] is True
        assert result["stored_value"] == expected
        assert result["value"] == expected * 2 + 5
        assert [result["column"], result["row"]] == [col, row]
        assert result["value_domain"] == "native_source_pixel"
    missing = client.post(url + "/inspect", json={"longitude": 110.015, "latitude": 22.985}).json()
    assert missing["valid"] is False and missing["value"] is None
    assert missing["status"] == "nodata"
    outside = client.post(url + "/inspect", json={"longitude": 111, "latitude": 23}).json()
    assert outside["status"] == "outside"
    with store.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(tasks)) == 0


@pytest.mark.parametrize("kind", ["missing", "conflict", "identity", "antimeridian"])
def test_bad_or_unsupported_location_keeps_actual_non_geographic_image(workspace, tmp_path, kind):
    _, _, client, _ = workspace
    crs, transform = "EPSG:4326", from_origin(110, 23, 0.01, 0.01)
    if kind == "missing":
        crs = None
    if kind == "conflict":
        transform = from_origin(300000, 2500000, 30, 30)
    if kind == "identity":
        transform = Affine.identity()
    if kind == "antimeridian":
        transform = from_origin(179, 23, 2, 0.01)
    asset = upload(workspace, tmp_path, crs=crs, transform=transform)
    url = f"/api/assets/{asset['id']}"
    view = client.get(url + "/view").json()
    assert view["georeference_status"] != "located"
    assert view["bounds"] is None and view["issues"]
    image = client.get(url + "/view.png")
    assert image.status_code == 200
    with rasterio.io.MemoryFile(image.content) as memory, memory.open() as ds:
        assert ds.read(4)[0, 0] == 255  # actual 0 remains visible
        assert ds.read(4)[1, 1] == 0
    assert client.post(url + "/inspect", json={"longitude": 110, "latitude": 23}).status_code == 422
    assert client.get(url + "/download").status_code == 200


def test_rotation_native_identity_and_transparent_warp_edges(workspace, tmp_path):
    _, _, client, _ = workspace
    transform = Affine.translation(110, 23) * Affine.rotation(30) * Affine.scale(0.01, -0.01)
    asset = upload(
        workspace,
        tmp_path,
        transform=transform,
        nodata=None,
        values=np.array([[0, -1], [2, 3]], dtype="float32"),
    )
    url = f"/api/assets/{asset['id']}"
    x, y = transform * (0.5, 0.5)
    result = client.post(url + "/inspect", json={"longitude": x, "latitude": y}).json()
    assert [result["column"], result["row"], result["stored_value"]] == [0, 0, 0]
    view = client.get(url + "/view").json()
    assert view["georeference_status"] == "located"
    z = 13
    tx = int((x + 180) / 360 * 2**z)
    ty = int((1 - math.asinh(math.tan(math.radians(y))) / math.pi) / 2 * 2**z)
    image = client.get(f"{url}/tiles/{z}/{tx}/{ty}.png")
    assert image.status_code == 200, image.text
    with rasterio.io.MemoryFile(image.content) as memory, memory.open() as ds:
        assert ds.shape == (256, 256)
        assert ds.read(4).min() == 0 and ds.read(4).max() == 255
    assert client.get(f"{url}/tiles/30/0/0.png").status_code == 422


def test_all_nodata_and_band_validation(workspace, tmp_path):
    _, _, client, _ = workspace
    asset = upload(workspace, tmp_path, values=np.full((3, 3), -9999, dtype="float32"))
    url = f"/api/assets/{asset['id']}"
    view = client.get(url + "/view").json()
    assert view["minimum"] is None and view["sample_valid_pixels"] == 0
    assert view["display_status"] == "empty_sample"
    image = client.get(url + "/view.png")
    with rasterio.io.MemoryFile(image.content) as memory, memory.open() as ds:
        assert not ds.read(4).any()
    assert client.get(url + "/view?band=2").status_code == 422


def test_catalog_paging_personal_state_conflict_and_scope(workspace, tmp_path):
    _, store, client, project = workspace
    a = upload(workspace, tmp_path, name="distance.tif")
    b = upload(workspace, tmp_path, values=np.ones((2, 2), dtype="float32"), name="other.tif")
    url = f"/api/projects/{project}"
    result = client.get(url + "/catalog?limit=1&sort=name").json()
    assert result["total"] == 2 and len(result["items"]) == 1
    assert client.get(url + "/catalog?query=distance").json()["items"][0]["id"] == a["id"]
    assert client.get(url + "/catalog?query=%25").json()["total"] == 0
    assert client.get(url + "/catalog?limit=101").status_code == 422
    state = client.get(url + "/view-state").json()
    assert state["revision"] == 0
    body = {
        "expected_revision": 0,
        "state": {
            "asset_id": a["id"],
            "band": 1,
            "camera": {"longitude": 110, "latitude": 23, "zoom": 9},
            "visible": True,
            "opacity": 0.9,
        },
    }
    saved = client.put(url + "/view-state", json=body)
    assert saved.status_code == 200, saved.text
    assert client.get(url + "/view-state").json()["state"] == body["state"]
    assert (
        client.put(
            url + "/view-state", json={**body, "state": {"asset_id": b["id"], "band": 1}}
        ).status_code
        == 409
    )
    outsider = store.create_account("outsider@test.example", "safe-password-for-tests")
    foreign = store.create_project(outsider, "foreign")
    assert client.get(f"/api/projects/{foreign}/catalog").status_code == 404
    login = client.post(
        "/api/session",
        json={"email": "outsider@test.example", "password": "safe-password-for-tests"},
    ).json()
    client.headers["X-CSRF-Token"] = login["csrf"]
    for route in ["/view", "/view.png", "/tiles/1/1/1.png", "/download"]:
        assert client.get(f"/api/assets/{a['id']}" + route).status_code == 404
    assert client.get(url + "/view-state").status_code == 404


def test_alpha_palette_and_cache_keep_valid_zero_and_original_codes(workspace, tmp_path):
    from rasterio.enums import ColorInterp

    _, _, client, project = workspace
    for mode in ["alpha", "palette"]:
        path = tmp_path / f"{mode}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=2,
            height=2,
            count=2 if mode == "alpha" else 1,
            dtype="uint8",
            crs="EPSG:4326",
            transform=from_origin(110, 23, 0.01, 0.01),
        ) as ds:
            ds.write(np.array([[0, 1], [2, 3]], dtype="uint8"), 1)
            if mode == "alpha":
                ds.write(np.array([[255, 0], [255, 255]], dtype="uint8"), 2)
                ds.colorinterp = (ColorInterp.gray, ColorInterp.alpha)
            else:
                ds.write_colormap(
                    1,
                    {
                        0: (200, 10, 10, 255),
                        1: (10, 200, 10, 255),
                        2: (10, 10, 200, 255),
                        3: (200, 200, 10, 255),
                    },
                )
        with path.open("rb") as stream:
            asset = client.post(
                f"/api/projects/{project}/assets", files={"file": (path.name, stream)}
            ).json()["asset"]
        base = f"/api/assets/{asset['id']}"
        assert client.get(base + "/view").status_code == 200
        first = client.get(base + "/view.png").content
        assert client.get(base + "/view.png").content == first
        with rasterio.io.MemoryFile(first) as memory, memory.open() as image:
            pixels = image.read()
            assert pixels[3, 0, 0] == 255
            if mode == "alpha":
                assert pixels[3, 0, 1] == 0
            else:
                assert pixels[:, 0, 0].tolist() == [200, 10, 10, 255]
        point = client.post(
            base + "/inspect", json={"longitude": 110.005, "latitude": 22.995}
        ).json()
        assert point["valid"] and point["stored_value"] == 0
