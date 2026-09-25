import io

import numpy as np
import pytest
from shapely.geometry import Point
from test_builtin_indicators import add, catalog, execute, spectral
from test_preparation_steps import research

from coastmas_next.indicator_kernels_v1 import spectral as calculate_spectral


@pytest.mark.parametrize(
    "code,expected,parameters",
    [
        ("ndvi", 0.5, {}),
        (
            "evi",
            1 / 2.05,
            {"gain": 2.5, "red_coefficient": 6.0, "blue_coefficient": 7.5, "background": 1.0},
        ),
        ("savi", 0.6 / 1.3, {"soil_factor": 0.5}),
        ("ndwi", -1 / 3, {}),
        ("mndwi", -1 / 7, {}),
        ("ndbi", -0.2, {}),
    ],
)
def test_spectral_profiles_physical_values_and_nodata(code, expected, parameters):
    bands = {
        k: np.array([v, 0, v])
        for k, v in {"red": 0.2, "nir": 0.6, "green": 0.3, "swir1": 0.4, "blue": 0.1}.items()
    }
    masks = {k: np.array([True, True, False]) for k in bands}
    out, valid = calculate_spectral("indicator." + code, bands, masks, parameters)
    assert out[0] == pytest.approx(expected, abs=1e-12)
    assert not valid[2] and np.isnan(out[2])
    if code not in {"evi", "savi"}:
        assert not valid[1]


def test_C_expansion_candidate_library_and_actual_rate(workspace):
    _, store, client, project = workspace
    first = spectral(
        client,
        project,
        ["land_cover"],
        [[[1, 1, 0, 0]]],
        {"observed_year": "2020", "built_up_codes": "[1]"},
        name="基期.tif",
    )
    task = research(client, project, [first])
    item = catalog(client, task)["indicator.urban_speed"]
    assert item["status"] == "missing" and item["missing"] == ["第二期土地利用数据"]
    last = spectral(
        client,
        project,
        ["land_cover"],
        [[[1, 1, 1, 0]]],
        {"observed_year": "2025", "built_up_codes": "[1]"},
        name="末期.tif",
    )
    item = catalog(client, task)["indicator.urban_speed"]
    assert item["status"] == "ready"
    selected = add(client, task, "indicator.urban_speed")
    task = selected["task"]
    assert last["id"] in [r["asset_id"] for r in task["draft"]["selection"]]
    result = execute(client, store, task, selected["items"][0]["selection_id"])
    stats = result["data"]["statistics"]
    assert stats["area0_m2"] == pytest.approx(200)
    assert stats["area1_m2"] == pytest.approx(300)
    assert stats["speed_m2_per_year"] == pytest.approx(20)
    assert {f["view_kind"] for f in result["data"]["files"]} == {"raster", "table"}


def test_E_road_density_uses_default_radius_and_deduplicated_clipped_length(workspace):
    settings, store, client, project = workspace
    grid = spectral(client, project, ["domain"], [[[1.0]]])
    # Explicit projected CRS in a GPKG avoids inventing a geographic location for GeoJSON.

    import fiona

    path = settings.storage_root / "roads-fixture.gpkg"
    schema = {"geometry": "LineString", "properties": {"highway": "str"}}
    with fiona.open(path, "w", driver="GPKG", layer="roads", crs="EPSG:6933", schema=schema) as ds:
        line = {"type": "LineString", "coordinates": [(398000, 2499995), (402000, 2499995)]}
        ds.write({"geometry": line, "properties": {"highway": "primary"}})
        ds.write({"geometry": line, "properties": {"highway": "primary"}})
    response = client.post(
        f"/api/projects/{project}/assets",
        files={
            "file": ("roads.gpkg", io.BytesIO(path.read_bytes()), "application/geopackage+sqlite3")
        },
    )
    assert response.status_code == 201, response.text
    roads = response.json()["asset"]
    task = research(client, project, [grid, roads])
    item = catalog(client, task)["indicator.road_density"]
    assert item["status"] == "ready", item
    selected = add(client, task, "indicator.road_density")
    task = selected["task"]
    result = execute(client, store, task, selected["items"][0]["selection_id"])
    import rasterio

    with rasterio.open(settings.storage_root / result["data"]["files"][0]["key"]) as ds:
        expected = 2000 / Point(0, 0).buffer(1000, quad_segs=64).area * 1000
        assert ds.read(1)[0, 0] == pytest.approx(expected, rel=1e-10)
    assert result["manifest"]["method"]["parameters"]["radius_m"] == 1000
    assert len(client.get(f"/api/projects/{project}/tasks").json()) == 1
