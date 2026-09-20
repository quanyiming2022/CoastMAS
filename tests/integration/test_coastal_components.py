import csv
import json
from pathlib import Path

import pytest

from coastmas.adapters.geofiles import decode_geotiff
from coastmas.core.errors import CoastMASError
from coastmas.domain.coastal_components import (
    overlay_component,
    screening_component,
    statistics_component,
)
from tests.factories import scene


def coastal_inputs():
    directory = Path("sample-data")
    manifest = json.loads((directory / "manifest.json").read_text())
    dem = decode_geotiff((directory / "dem.tif").read_bytes())
    cover = decode_geotiff((directory / "land_cover_t1.tif").read_bytes())
    units = json.loads((directory / "management_units.geojson").read_text())
    units["crs"] = "EPSG:4326"
    with (directory / "population.csv").open() as stream:
        population = {
            "rows": list(csv.DictReader(stream)),
            "column_units": {"population": "person"},
            "unit_source": "catalog_declaration",
        }
    context = {
        "scene": scene(
            study_area=json.loads((directory / "coastal_aoi.geojson").read_text())["features"][0][
                "geometry"
            ],
            scenario_conditions={
                "vertical_datum": manifest["vertical_datum"],
                "sea_level_baseline_m": manifest["baseline_m"],
                "coastal_seeds": manifest["seeds"],
                "population_distribution": "uniform_within_management_unit",
            },
            data_policy={
                "study_area_crs": "EPSG:4326",
                "target_grid": {
                    "crs": dem.crs,
                    "transform": list(dem.transform)[:6],
                    "height": dem.values.shape[0],
                    "width": dem.values.shape[1],
                },
            },
        ).model_dump(mode="json")
    }
    return context, dem.values.tolist(), cover.values.tolist(), units, population


def test_separate_screen_overlay_and_statistics_match_real_sample_goldens():
    context, dem, cover, units, population = coastal_inputs()
    screen = screening_component(context, {"dem": dem}, {"increment": 0.5, "connectivity": 4})
    assert screen["area_m2"] == 80000
    assert screen["polygons"]["features"]
    impacts = overlay_component(
        context,
        {
            "inundation": screen["inundation"],
            "land_cover": cover,
            "units": units,
            "population": population,
        },
        {},
    )
    statistics = statistics_component(context, impacts, {})["statistics"]
    assert statistics["inundated_area_m2"] == 80000
    assert statistics["estimated_affected_population"] == 320
    assert statistics["land_cover_area_m2"] == {"1": 40000, "2": 40000}
    assert statistics["population_assumption"] == "uniform within each management unit"
    assert set(statistics["units"]) == {"U1", "U2", "U3", "U4"}
    assert "not hydrodynamics" in statistics["method"]


def test_population_allocation_requires_explicit_assumption_and_matching_units():
    context, dem, cover, units, population = coastal_inputs()
    mask = screening_component(context, {"dem": dem}, {"increment": 0.5})["inundation"]
    inputs = {"inundation": mask, "land_cover": cover, "units": units, "population": population}
    context["scene"]["scenario_conditions"].pop("population_distribution")
    with pytest.raises(CoastMASError, match="population"):
        overlay_component(context, inputs, {})
    context["scene"]["scenario_conditions"]["population_distribution"] = (
        "uniform_within_management_unit"
    )
    population["rows"].pop()
    with pytest.raises(CoastMASError, match="population"):
        overlay_component(context, inputs, {})


def test_unknown_dem_area_remains_unknown_in_management_statistics():
    context, dem, cover, units, population = coastal_inputs()
    dem[3][3] = None
    screen = screening_component(context, {"dem": dem}, {"increment": 0.5})
    assert screen["inundation"][3][3] is None
    impacts = overlay_component(
        context,
        {
            "inundation": screen["inundation"],
            "land_cover": cover,
            "units": units,
            "population": population,
        },
        {},
    )
    statistics = statistics_component(context, impacts, {})["statistics"]
    assert statistics["unknown_area_m2"] == 10000
    assert statistics["population_in_unknown_dem_area"] == 60


def test_study_area_mask_does_not_renormalize_population_to_clipped_area():
    from affine import Affine
    from shapely.geometry import Polygon, mapping

    context, dem, cover, units, population = coastal_inputs()
    grid = context["scene"]["data_policy"]["target_grid"]
    transform = Affine(*grid["transform"])
    polygon = Polygon([transform @ point for point in [(0, 0), (1, 0), (1, 4), (0, 4)]])
    context["scene"]["study_area"] = json.loads(json.dumps(mapping(polygon)))
    context["scene"]["data_policy"]["study_area_crs"] = grid["crs"]
    screen = screening_component(context, {"dem": dem}, {"increment": 0.5})
    assert screen["area_m2"] == 40000
    impacts = overlay_component(
        context,
        {
            "inundation": screen["inundation"],
            "land_cover": cover,
            "units": units,
            "population": population,
        },
        {},
    )
    stats = statistics_component(context, impacts, {})["statistics"]
    assert stats["estimated_affected_population"] == 160
    assert stats["unknown_area_m2"] == 0
    assert stats["units"]["U1"]["fraction"] == 0.5


def test_statistics_rejects_forged_inundation_codes():
    context, dem, cover, units, population = coastal_inputs()
    screen = screening_component(context, {"dem": dem}, {"increment": 0.5})
    impacts = overlay_component(
        context,
        {
            "inundation": screen["inundation"],
            "land_cover": cover,
            "units": units,
            "population": population,
        },
        {},
    )
    impacts["impacts"]["inundation"][0][0] = 2
    with pytest.raises(CoastMASError):
        statistics_component(context, impacts, {})
