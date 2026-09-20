"""Real raster and vector operations through the common process lifecycle.

Vector payloads carry an explicit CRS and are internal geometry mappings;
projected coordinates are not mislabelled as RFC 7946 GeoJSON exports. Overlay
unions dissolve geometry and explicitly report all source IDs rather than
inventing an attribute aggregation rule. Buffer uses 32 segments per quadrant.
"""

import json
import math
from dataclasses import asdict
from functools import partial
from typing import Literal

import numpy as np
from affine import Affine
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter
from pyproj import CRS
from rasterio.features import shapes  # type: ignore[import-untyped]
from shapely.geometry import mapping, shape  # type: ignore[import-untyped]
from shapely.geometry.base import BaseGeometry  # type: ignore[import-untyped]
from shapely.ops import unary_union  # type: ignore[import-untyped]

from coastmas.adapters.datasource import TargetGrid
from coastmas.adapters.geofiles import Grid, resample_grid
from coastmas.adapters.runtime import Handler, PythonFunctionAdapter
from coastmas.core.errors import ConstraintError
from coastmas.domain.raster import zonal_statistics
from coastmas.domain.raster_units import calculate_grids

JSON_OUTPUT = TypeAdapter(dict[str, JsonValue])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class GridPayload(Input):
    values: list[list[float | None]]
    crs: str
    transform: tuple[float, float, float, float, float, float]
    unit: str
    vertical_datum: str | None = None

    def grid(self) -> Grid:
        return Grid(
            np.asarray(self.values, dtype=np.float64),
            self.crs,
            Affine(*self.transform),
            self.unit,
            self.vertical_datum,
        )


def grid_json(grid: Grid) -> dict[str, JsonValue]:
    return JSON_OUTPUT.validate_python(
        {
            "values": [
                [float(value) if np.isfinite(value) else None for value in row]
                for row in grid.values
            ],
            "crs": grid.crs,
            "transform": list(grid.transform)[:6],
            "unit": grid.unit,
            "vertical_datum": grid.vertical_datum,
        }
    )


class CalculatorInput(Input):
    rasters: dict[str, GridPayload]
    expression: str
    output_unit: str


def calculate(
    inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    if parameters:
        raise ConstraintError("calculator accepts only its explicit expression inputs")
    data = CalculatorInput.model_validate(inputs)
    result = calculate_grids(
        data.expression,
        {name: value.grid() for name, value in data.rasters.items()},
        data.output_unit,
    )
    return {"grid": grid_json(result)}


class ZonalInput(Input):
    values: GridPayload
    zones: GridPayload


def zones(inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]) -> dict[str, JsonValue]:
    if parameters:
        raise ConstraintError("zonal statistics do not accept implicit area overrides")
    data = ZonalInput.model_validate(inputs)
    values, labels = data.values.grid(), data.zones.grid()
    if values.crs != labels.crs or values.transform != labels.transform:
        raise ConstraintError("zone and value grids must be aligned")
    result = zonal_statistics(values.values, labels.values, cell_area=values.cell_area_m2)
    return JSON_OUTPUT.validate_python(
        {
            "zones": {str(key): asdict(value) for key, value in result.items()},
            "unit": values.unit,
            "area_unit": "m^2",
            "denominator": "all cells assigned to zone",
        }
    )


class RegridInput(Input):
    grid: GridPayload
    target: TargetGrid
    kind: Literal["continuous", "categorical", "extensive"]
    method: Literal["nearest", "bilinear", "average", "sum", "area_weighted"]


def regrid(inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]) -> dict[str, JsonValue]:
    if parameters:
        raise ConstraintError("regridding parameters must be in the explicit target grid")
    data = RegridInput.model_validate(inputs)
    result = resample_grid(
        data.grid.grid(),
        crs=data.target.crs,
        transform=Affine(*data.target.transform),
        shape=(data.target.height, data.target.width),
        kind=data.kind,
        method=data.method,
    )
    return {"grid": grid_json(result)}


class PolygonizeInput(Input):
    grid: GridPayload


class PolygonizeOptions(Input):
    connectivity: Literal[4, 8] = 4


def polygonize(
    inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    grid = PolygonizeInput.model_validate(inputs).grid.grid()
    options = PolygonizeOptions.model_validate(parameters)
    known = np.isfinite(grid.values)
    observed = grid.values[known]
    if np.any(observed != np.floor(observed)) or np.any(np.abs(observed) > 2**31 - 1):
        raise ConstraintError("polygonize requires categorical int32 values")
    labels = np.where(known, grid.values, 0).astype("int32")
    features = [
        {"type": "Feature", "properties": {"value": int(value)}, "geometry": geometry}
        for geometry, value in shapes(
            labels, mask=known, transform=grid.transform, connectivity=options.connectivity
        )
    ]
    return JSON_OUTPUT.validate_json(
        json.dumps({"features": features, "crs": grid.crs}, allow_nan=False)
    )


class Feature(Input):
    id: str = Field(min_length=1)
    geometry: dict[str, JsonValue]
    properties: dict[str, JsonValue] = Field(default_factory=dict)

    def geometry_object(self) -> BaseGeometry:
        geometry = shape(self.geometry)
        if geometry.is_empty or not geometry.is_valid or geometry.has_z:
            raise ConstraintError("geometry must be valid, nonempty and explicitly two dimensional")
        return geometry


class BufferInput(Input):
    crs: str
    features: list[Feature] = Field(min_length=1, max_length=10000)


class BufferOptions(Input):
    distance_m: float = Field(gt=0, le=100000)


def buffer(inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]) -> dict[str, JsonValue]:
    data = BufferInput.model_validate(inputs)
    options = BufferOptions.model_validate(parameters)
    reference = CRS(data.crs)
    if not reference.is_projected or len(reference.axis_info) < 2:
        raise ConstraintError("buffer distance requires a suitable projected CRS")
    first, second = (axis.unit_conversion_factor for axis in reference.axis_info[:2])
    if not math.isfinite(first) or first <= 0 or first != second:
        raise ConstraintError("buffer projected axis units must be equal and convertible to metres")
    features = [
        {
            "id": feature.id,
            "geometry": mapping(
                feature.geometry_object().buffer(options.distance_m / first, quad_segs=32)
            ),
            "properties": feature.properties,
        }
        for feature in data.features
    ]
    return JSON_OUTPUT.validate_json(
        json.dumps({"features": features, "crs": data.crs}, allow_nan=False)
    )


class OverlayInput(Input):
    crs: str
    left: list[Feature] = Field(min_length=1, max_length=1000)
    right: list[Feature] = Field(min_length=1, max_length=1000)
    operation: Literal["intersection", "union", "difference", "symmetric_difference"] = (
        "intersection"
    )


def overlay(
    intersection_only: bool, inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    if parameters:
        raise ConstraintError("overlay does not accept unspecified parameters")
    data = OverlayInput.model_validate(inputs)
    CRS(data.crs)
    if len(data.left) * len(data.right) > 100000:
        raise ConstraintError("overlay pair budget exceeded")
    left = [(feature, feature.geometry_object()) for feature in data.left]
    right = [(feature, feature.geometry_object()) for feature in data.right]
    features: list[dict[str, object]] = []
    if intersection_only or data.operation == "intersection":
        for source, a in left:
            for target, b in right:
                result = a.intersection(b)
                if not result.is_empty:
                    features.append(
                        {
                            "geometry": mapping(result),
                            "properties": {
                                "left_id": source.id,
                                "right_id": target.id,
                                "left_properties": source.properties,
                                "right_properties": target.properties,
                            },
                        }
                    )
    else:
        a = unary_union([geometry for _, geometry in left])
        b = unary_union([geometry for _, geometry in right])
        if data.operation == "union":
            result = a.union(b)
        elif data.operation == "difference":
            result = a.difference(b)
        else:
            result = a.symmetric_difference(b)
        if not result.is_empty:
            features.append(
                {
                    "geometry": mapping(result),
                    "properties": {
                        "operation": data.operation,
                        "source_ids": [feature.id for feature in data.left + data.right],
                        "attribute_policy": "dissolved; no inferred aggregation",
                    },
                }
            )
    return JSON_OUTPUT.validate_json(
        json.dumps({"features": features, "crs": data.crs}, allow_nan=False)
    )


class RasterGISAdapter(PythonFunctionAdapter):
    def __init__(self) -> None:
        handlers: dict[str, Handler] = {
            "calculator": calculate,
            "zonal_statistics": zones,
            "reprojection": regrid,
            "resampling": regrid,
            "polygonize": polygonize,
            "buffer": buffer,
            "intersection": partial(overlay, True),
            "overlay": partial(overlay, False),
        }
        super().__init__(handlers, max_output_bytes=16 * 1024 * 1024)
