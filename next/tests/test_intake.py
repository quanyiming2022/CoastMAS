"""Actual file facts, multiple standards and task-bound asset intake."""

import json

import numpy as np
import pytest
import rasterio
from coastmas_next.intake import Intake
from coastmas_next.profiles import inspect_file
from coastmas_next.store import Problem
from netCDF4 import Dataset
from rasterio.transform import from_origin


def test_csv_dialect_ids_zero_and_unknown_units(tmp_path):
    p = tmp_path / "anything.dat"
    p.write_text("id;value;date\n001;0;2022\n002;-1;2022\n003;;2022\n", encoding="utf-8-sig")
    f = inspect_file(p)
    assert (f["profile"], f["encoding"], f["dialect"]["delimiter"]) == ("csv", "utf-8-sig", ";")
    assert f["layers"][0]["preview"][0] == {"id": "001", "value": "0", "date": "2022"}
    assert f["layers"][0]["row_count"] == 3
    assert f["layers"][0]["fields"][1]["unit"] is None
    assert f["observed_period"] is None


def test_raster_magic_grid_and_physical_values(tmp_path):
    p = tmp_path / "fake.csv"
    with rasterio.open(
        p,
        "w",
        driver="GTiff",
        width=4,
        height=3,
        count=1,
        dtype="int16",
        crs="EPSG:4326",
        transform=from_origin(113, 23, 0.01, 0.01),
        nodata=-9999,
    ) as ds:
        ds.write(np.arange(12, dtype="int16").reshape(3, 4), 1)
        ds.scales, ds.offsets = (0.1,), (2.0,)
    f = inspect_file(p)
    assert (f["profile"], f["crs"]) == ("geotiff", "EPSG:4326")
    assert f["layers"][0]["fields"][0]["scale"] == 0.1
    assert f["layers"][0]["fields"][0]["offset"] == 2
    assert f["layers"][0]["preview"][0][0] == 2
    assert f["observed_period"] is None


def test_cf_calendar_bounds_and_cell_methods_are_retained(tmp_path):
    p = tmp_path / "series.nc"
    with Dataset(p, "w") as ds:
        ds.Conventions = "CF-1.12"
        ds.createDimension("time", 2)
        ds.createDimension("nv", 2)
        t = ds.createVariable("time", "f8", ("time",))
        t.units, t.calendar, t.bounds = "days since 2022-01-01", "360_day", "time_bounds"
        t[:] = [15, 45]
        b = ds.createVariable("time_bounds", "f8", ("time", "nv"))
        b[:] = [[0, 30], [30, 60]]
        v = ds.createVariable("height", "f8", ("time",))
        v.units, v.standard_name, v.cell_methods = "m", "sea_surface_height", "time: mean"
        v[:] = [0, 2]
    f = inspect_file(p)
    assert f["standard_version"] == "CF-1.12"
    assert f["coordinates"]["time"]["calendar"] == "360_day"
    assert f["coordinates"]["time"]["bounds_values"] == [[0, 30], [30, 60]]
    field = next(x for x in f["layers"][0]["fields"] if x["name"] == "height")
    assert (field["cell_methods"], field["unit"]) == ("time: mean", "m")


def test_geojson_and_multilayer_gpkg(tmp_path):
    import fiona

    p = tmp_path / "area.json"
    feature = {
        "type": "Feature",
        "id": "shore-1",
        "properties": {"name": "Shore", "cost": 0},
        "geometry": {"type": "Point", "coordinates": [113, 23]},
    }
    p.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}))
    facts = inspect_file(p)
    assert facts["profile"] == "geojson"
    assert facts["layers"][0]["preview"][0]["id"] == "shore-1"
    gpkg = tmp_path / "layers.gpkg"
    for layer in ["shore", "wetland"]:
        with fiona.open(
            gpkg,
            "w",
            driver="GPKG",
            layer=layer,
            crs="EPSG:4326",
            schema={"geometry": "Point", "properties": {"name": "str"}},
        ) as out:
            out.write({"geometry": feature["geometry"], "properties": {"name": layer}})
    assert {layer["name"] for layer in inspect_file(gpkg)["layers"]} == {"shore", "wetland"}


def test_upload_keeps_bytes_reuses_blob_and_attaches_independent_asset_to_task(workspace):
    settings, store, client, project = workspace
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "Intake", "purpose": "temporal"}
    ).json()
    raw = b"id;value\n001;0\n002;2\n"
    r = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("values.csv", raw)},
        data={"task_id": task["id"], "expected_revision": "1"},
    )
    assert r.status_code == 201, r.text
    asset = r.json()["asset"]
    assert asset["facts"]["profile"] == "csv"
    assert client.get(f"/api/assets/{asset['id']}/download").content == raw
    current = client.get(f"/api/tasks/{task['id']}").json()
    assert current["draft"]["selection"][0]["asset_id"] == asset["id"]
    assert current["draft"]["mapping"][0]["unit"] is None
    repeat = client.post(f"/api/projects/{project}/assets", files={"file": ("other-name.csv", raw)})
    assert repeat.json()["asset"]["id"] != asset["id"]
    assert repeat.json()["asset"]["object_key"] == asset["object_key"]
    assert repeat.json()["asset"]["name"] == "other-name.csv"
    assert repeat.json()["reused_blob"] is True


def test_unapproved_local_path_is_rejected(workspace, tmp_path):
    _, store, _, project = workspace
    source = tmp_path / "private.csv"
    source.write_text("secret,value\nx,1\n")
    with pytest.raises(Problem) as denied:
        Intake(store).local_file(project, source)
    assert denied.value.status == 403
