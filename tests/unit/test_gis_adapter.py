import math

import pytest
from pyproj import Transformer
from shapely.geometry import shape

from coastmas.adapters.gis import RasterGISAdapter
from coastmas.adapters.runtime import RunRequest
from coastmas.core.errors import CoastMASError


def grid(values, unit="m"):
    return {
        "values": values,
        "crs": "EPSG:32650",
        "transform": [10, 0, 500000, 0, -10, 3500000],
        "unit": unit,
        "vertical_datum": None,
    }


def run(tmp_path, handler, inputs, parameters=None):
    return (
        RasterGISAdapter().run(RunRequest(handler, inputs, parameters or {}, tmp_path, 10)).outputs
    )


def test_calculator_uses_units_and_does_not_hide_nodata(tmp_path):
    result = run(
        tmp_path,
        "calculator",
        {
            "rasters": {"a": grid([[1, None]], "m"), "b": grid([[100, 100]], "cm")},
            "expression": "a+b",
            "output_unit": "m",
        },
    )
    assert result["grid"]["values"] == [[2, None]]
    with pytest.raises(CoastMASError, match="unit|dimension"):
        run(
            tmp_path,
            "calculator",
            {"rasters": {"a": grid([[2]])}, "expression": "a*a", "output_unit": "m"},
        )


def test_zonal_statistics_and_polygonize_preserve_valid_area(tmp_path):
    result = run(
        tmp_path,
        "zonal_statistics",
        {"values": grid([[1, None], [3, 4]]), "zones": grid([[1, 1], [2, 2]], "dimensionless")},
    )
    assert result["zones"]["1"]["coverage"] == 0.5
    assert result["zones"]["2"]["total"] == 7
    polygons = run(
        tmp_path,
        "polygonize",
        {"grid": grid([[1, 1], [2, None]], "dimensionless")},
        {"connectivity": 4},
    )
    assert len(polygons["features"]) == 2
    assert sum(shape(feature["geometry"]).area for feature in polygons["features"]) == 300


def test_buffer_intersection_and_overlay_use_projected_units(tmp_path):
    point = {"id": "p", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}
    result = run(tmp_path, "buffer", {"crs": "EPSG:32650", "features": [point]}, {"distance_m": 10})
    assert shape(result["features"][0]["geometry"]).area == pytest.approx(math.pi * 100, rel=0.001)
    with pytest.raises(CoastMASError, match="projected"):
        run(tmp_path, "buffer", {"crs": "EPSG:4326", "features": [point]}, {"distance_m": 10})

    def rectangle(identifier, left, right):
        return {
            "id": identifier,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[left, 0], [right, 0], [right, 10], [left, 10], [left, 0]]],
            },
            "properties": {},
        }

    layers = {
        "crs": "EPSG:32650",
        "left": [rectangle("a", 0, 10)],
        "right": [rectangle("b", 5, 15)],
    }
    intersection = run(tmp_path, "intersection", layers)
    assert shape(intersection["features"][0]["geometry"]).area == 50
    union = run(tmp_path, "overlay", dict(layers, operation="union"))
    assert shape(union["features"][0]["geometry"]).area == 150


def test_resampling_preserves_categories_and_reprojection_is_real(tmp_path):
    destination = {
        "crs": "EPSG:32650",
        "transform": [5, 0, 500000, 0, -5, 3500000],
        "height": 4,
        "width": 4,
    }
    request = {
        "grid": grid([[1, 2], [3, None]], "dimensionless"),
        "target": destination,
        "kind": "categorical",
        "method": "nearest",
    }
    result = run(tmp_path, "resampling", request)
    assert result["grid"]["values"][0] == [1, 1, 2, 2]
    request["method"] = "bilinear"
    with pytest.raises(CoastMASError, match="categorical"):
        run(tmp_path, "resampling", request)
    longitude, latitude = Transformer.from_crs("EPSG:32650", "EPSG:4326", always_xy=True).transform(
        500000, 3500000
    )
    request.update(
        method="nearest",
        target={
            "crs": "EPSG:4326",
            "transform": [0.0001, 0, longitude, 0, -0.0001, latitude],
            "height": 4,
            "width": 4,
        },
    )
    projected = run(tmp_path, "reprojection", request)
    assert projected["grid"]["crs"] == "EPSG:4326"
    assert any(value is not None for row in projected["grid"]["values"] for value in row)
