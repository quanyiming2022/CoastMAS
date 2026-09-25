"""Actual vector parts/identities; viewing never needs entity or science creation."""

import io
import json
import zipfile

import fiona
import pytest
from coastmas_next.store import tasks
from pyproj import Transformer
from sqlalchemy import func, select


def package(tmp_path, driver="GPKG", crs="EPSG:3857"):
    path = tmp_path / ("layers.gpkg" if driver == "GPKG" else "coast.shp")
    for layer, lon in [("west", 110), ("east", 122)] if driver == "GPKG" else [("coast", 110)]:
        schema = {"geometry": "Point", "properties": {"code": "str", "value": "float"}}
        with fiona.open(
            path,
            "w",
            driver=driver,
            layer=layer if driver == "GPKG" else None,
            schema=schema,
            crs=crs,
        ) as sink:
            for i in range(3):
                x, y = (
                    Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(
                        lon + i * 0.01, 23
                    )
                    if crs
                    else (lon, 23)
                )
                sink.write(
                    {
                        "type": "Feature",
                        "properties": {"code": f"{i + 1:03}", "value": float(i - 1)},
                        "geometry": {"type": "Point", "coordinates": [x, y]},
                    }
                )
    if driver == "GPKG":
        return path.read_bytes()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for item in tmp_path.glob("coast.*"):
            archive.write(item, item.name)
    return out.getvalue()


def upload(workspace, data, name="parts.gpkg"):
    _, _, client, project = workspace
    response = client.post(f"/api/projects/{project}/assets", files={"file": (name, data)})
    assert response.status_code == 201, response.text
    return response.json()["asset"]


@pytest.mark.parametrize("driver", ["GPKG", "ESRI Shapefile"])
def test_all_parts_native_identity_paging_and_projection(workspace, tmp_path, driver):
    _, store, client, _ = workspace
    raw = package(tmp_path, driver=driver)
    asset = upload(workspace, raw)
    root = f"/api/assets/{asset['id']}/vector"
    listing = client.get(root + "/layers")
    assert listing.status_code == 200, listing.text
    layers = listing.json()["layers"]
    assert len(layers) == (2 if driver == "GPKG" else 1)
    assert all(layer["georeference_status"] == "located" for layer in layers)
    assert all(layer["total"] == 3 for layer in layers)
    for layer in layers:
        page = client.get(root + "/features", params={"layer": layer["name"], "limit": 2}).json()
        assert page["total"] == 3 and page["scope"] == "source_record_page"
        assert [f["properties"]["code"] for f in page["features"]] == ["001", "002"]
        assert [f["properties"]["value"] for f in page["features"]] == [-1, 0]
        assert abs(page["features"][0]["geometry"]["coordinates"][1] - 23) < 1e-8
        second = client.get(
            root + "/features", params={"layer": layer["name"], "limit": 2, "offset": 2}
        ).json()
        assert second["features"][0]["properties"]["code"] == "003"
        first = page["features"][0]
        native = client.get(root + "/records/0", params={"layer": layer["name"]}).json()
        assert native["id"] == first["id"]
        assert native["asset_id"] == asset["id"] and native["sha256"] == asset["sha256"]
        assert native["native_geometry"]["coordinates"][0] > 1_000_000
        assert native["properties"] == first["properties"]
        assert client.get(root + "/records/3", params={"layer": layer["name"]}).status_code == 404
    assert client.get(root + "/features", params={"layer": "nonexistent"}).status_code == 422
    assert (
        client.get(
            root + "/features", params={"layer": layers[0]["name"], "limit": 501}
        ).status_code
        == 422
    )
    assert client.get(f"/api/assets/{asset['id']}/download").content == raw
    with store.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(tasks)) == 0


def test_unknown_crs_preserves_attributes_without_guessing_location(workspace, tmp_path):
    asset = upload(workspace, package(tmp_path, driver="ESRI Shapefile", crs=None))
    client = workspace[2]
    root = f"/api/assets/{asset['id']}/vector"
    layer = client.get(root + "/layers").json()["layers"][0]
    assert layer["georeference_status"] == "missing" and layer["bounds"] is None
    page = client.get(root + "/features", params={"layer": layer["name"]}).json()
    assert page["features"][0]["geometry"] is None
    assert page["features"][0]["properties"]["code"] == "001"
    assert page["features"][0]["display_issue"]


def test_bad_geojson_coordinates_and_duplicate_ids_are_not_guessed_or_merged(workspace):
    raw = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "same",
                    "properties": {"code": "001"},
                    "geometry": {"type": "Point", "coordinates": [110, 23]},
                },
                {
                    "type": "Feature",
                    "id": "same",
                    "properties": {"code": "002"},
                    "geometry": {"type": "Point", "coordinates": [300000, 2500000]},
                },
            ],
        }
    ).encode()
    asset = upload(workspace, raw, "bad-location.geojson")
    client = workspace[2]
    root = f"/api/assets/{asset['id']}/vector"
    layer = client.get(root + "/layers").json()["layers"][0]
    assert layer["georeference_status"] == "conflict" and layer["bounds"] is None
    page = client.get(root + "/features", params={"layer": layer["name"]}).json()
    assert len({f["id"] for f in page["features"]}) == 2
    assert page["features"][1]["geometry"] is None
    assert page["features"][1]["properties"]["code"] == "002"


def test_vector_routes_recheck_project_permission(workspace, tmp_path):
    _, store, client, _ = workspace
    asset = upload(workspace, package(tmp_path))
    root = f"/api/assets/{asset['id']}/vector"
    assert client.get(root + "/layers").status_code == 200
    store.create_account("outsider-vector@example.test", "safe-password-for-tests")
    response = client.post(
        "/api/session",
        json={"email": "outsider-vector@example.test", "password": "safe-password-for-tests"},
    ).json()
    client.headers["X-CSRF-Token"] = response["csrf"]
    for route in ["/layers", "/features?layer=west", "/records/0?layer=west"]:
        assert client.get(root + route).status_code == 404
