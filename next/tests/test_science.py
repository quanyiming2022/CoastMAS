"""Numerical and domain tests against actual managed inputs, not canned outputs."""

import json

import pytest
from coastmas_next.worker import Worker
from netCDF4 import Dataset


def run_task(client, store, project, purpose, filename, raw, options, mapping=None):
    t = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Scientific fixture", "purpose": purpose},
    ).json()
    t = client.post(
        f"/api/projects/{project}/assets",
        files={"file": (filename, raw)},
        data={"task_id": t["id"], "expected_revision": "1"},
    ).json()["task"]
    t["draft"]["options"] = options
    if mapping:
        for item in t["draft"]["mapping"]:
            if item["field"] in mapping:
                item.update(mapping[item["field"]])
            else:
                item["role"] = "identity"
    else:
        t["draft"]["mapping"] = []
    saved = client.put(
        f"/api/tasks/{t['id']}", json={"expected_revision": t["revision"], "draft": t["draft"]}
    ).json()
    r = client.post(
        f"/api/tasks/{t['id']}/execute",
        json={"expected_revision": saved["revision"], "idempotency_key": "science"},
    )
    assert r.status_code == 202, r.text
    job = r.json()
    Worker(store).run_once()
    state = client.get(f"/api/jobs/{job['id']}").json()
    assert state["status"] == "succeeded", state
    return client.get(f"/api/jobs/{job['id']}/result").json()


def test_cf_360_day_interval_mean_is_not_gregorian(workspace, tmp_path):
    _, store, client, project = workspace
    p = tmp_path / "calendar.nc"
    with Dataset(p, "w") as ds:
        ds.Conventions = "CF-1.12"
        ds.createDimension("time", 2)
        ds.createDimension("bounds", 2)
        t = ds.createVariable("time", "f8", ("time",))
        t.units = "days since 2022-01-01"
        t.calendar = "360_day"
        t.bounds = "time_bounds"
        t[:] = [15, 45]
        b = ds.createVariable("time_bounds", "f8", ("time", "bounds"))
        b[:] = [[0, 30], [30, 60]]
        v = ds.createVariable("height", "f8", ("time",))
        v.units = "m"
        v.standard_name = "sea_surface_height"
        v.cell_methods = "time: mean"
        v[:] = [0, 2]
    result = run_task(
        client,
        store,
        project,
        "temporal",
        "series.nc",
        p.read_bytes(),
        {
            "variable": "height",
            "method": "mean",
            "start": "2022-01-01",
            "end": "2022-03-01",
            "output_unit": "cm",
        },
        {"dataset/height": {"unit": "m", "concept": "sea_surface_height", "support": "interval"}},
    )
    assert result["data"]["value"] == pytest.approx(100)
    assert result["data"]["calendar"] == "360_day"
    assert result["data"]["covered_duration"] == 60
    assert result["data"]["conversion"]["target_unit"] == "cm"


def test_entity_collection_keeps_geometry_identity_and_properties(workspace):
    _, store, client, project = workspace
    features = [
        {
            "type": "Feature",
            "id": f"unit-{n}",
            "properties": {"name": f"Unit {n}", "cost": n},
            "geometry": {"type": "Point", "coordinates": [113 + n / 10, 23]},
        }
        for n in range(3)
    ]
    result = run_task(
        client,
        store,
        project,
        "entities",
        "units.geojson",
        json.dumps({"type": "FeatureCollection", "features": features}).encode(),
        {},
    )
    assert [x["id"] for x in result["data"]["features"]] == ["unit-0", "unit-1", "unit-2"]
    assert result["data"]["features"][0]["properties"]["cost"] == 0
    assert result["data"]["type"] == "FeatureCollection"


def test_entity_execution_uses_each_selected_layer_and_mapped_identity(workspace, tmp_path):
    import fiona

    _, store, client, project = workspace
    path = tmp_path / "layers.gpkg"
    for layer, identity, x in [("unselected", "wrong", 110), ("selected", "001", 113)]:
        with fiona.open(
            path,
            "w",
            driver="GPKG",
            crs="EPSG:4326",
            layer=layer,
            schema={"geometry": "Point", "properties": {"unit_code": "str", "value": "int"}},
        ) as dst:
            dst.write(
                {
                    "type": "Feature",
                    "properties": {"unit_code": identity, "value": 0},
                    "geometry": {"type": "Point", "coordinates": [x, 23]},
                }
            )
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Selected actual layer", "purpose": "entities"},
    ).json()
    uploaded = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("layers.gpkg", path.read_bytes())},
        data={"task_id": task["id"], "expected_revision": 1},
    ).json()
    task = uploaded["task"]
    task["draft"]["selection"][0]["layer"] = "selected"
    task["draft"]["mapping"] = [
        {"asset_id": uploaded["asset"]["id"], "field": "selected/unit_code", "role": "identity"}
    ]
    task = client.put(
        f"/api/tasks/{task['id']}",
        json={"expected_revision": task["revision"], "draft": task["draft"]},
    ).json()
    job = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "layer-selection"},
    )
    assert job.status_code == 202, job.text
    assert Worker(store).run_once()
    result = client.get(f"/api/jobs/{job.json()['id']}/result")
    assert result.status_code == 200, result.text
    entities = result.json()["data"]
    assert [f["id"] for f in entities["features"]] == ["001"]
    assert entities["features"][0]["geometry"]["coordinates"] == [113, 23]
    assert entities["sources"][0]["layer"] == "selected"
