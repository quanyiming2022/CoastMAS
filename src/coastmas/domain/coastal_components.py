"""Composable terrain screening and explicit uniform-population impact estimates.

All rasters share the saved scene target grid. Administrative population totals
require complete unit coverage by that grid; a clipped unit is never silently
renormalized. Study-area cell centres define the analysis support.
"""

import math
from typing import Annotated, Literal

import numpy as np
from affine import Affine
from pydantic import Field, FiniteFloat, JsonValue, TypeAdapter
from rasterio.features import rasterize, shapes  # type: ignore[import-untyped]
from shapely.geometry import Polygon, shape  # type: ignore[import-untyped]

from coastmas.adapters.datasource import reproject_features
from coastmas.adapters.geofiles import Grid
from coastmas.core.contracts import Contract, Name, SceneSpec
from coastmas.core.contracts import TargetGridSpec as TargetGrid
from coastmas.core.errors import ConstraintError
from coastmas.domain.screening import screen_inundation

JSON_OBJECT = TypeAdapter(dict[str, JsonValue])
METHOD: Literal["terrain-connectivity screening, not hydrodynamics"] = (
    "terrain-connectivity screening, not hydrodynamics"
)
NullableMatrix = tuple[tuple[FiniteFloat | None, ...], ...]


class PopulationRecord(Contract):
    unit_id: Name
    population: Annotated[float, Field(ge=0, allow_inf_nan=False)]


class ImpactGrid(Contract):
    unit_ids: tuple[Name, ...]
    zones: tuple[tuple[int, ...], ...]
    inundation: NullableMatrix
    land_cover: NullableMatrix
    population: tuple[tuple[FiniteFloat, ...], ...]
    cell_area_m2: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    active: tuple[tuple[bool, ...], ...]
    method: Literal["terrain-connectivity screening, not hydrodynamics"] = METHOD
    population_assumption: Literal["uniform within each management unit"] = (
        "uniform within each management unit"
    )


def _scene_grid(context: dict[str, JsonValue]) -> tuple[SceneSpec, Grid, np.ndarray]:
    scene = SceneSpec.model_validate(context.get("scene"))
    spec = TargetGrid.model_validate(scene.data_policy.get("target_grid"))
    grid = Grid(np.zeros((spec.height, spec.width)), spec.crs, Affine(*spec.transform), "1")
    _ = grid.cell_area_m2  # Reject angular grids before interpreting area as square metres.
    crs = scene.data_policy.get("study_area_crs")
    if not isinstance(crs, str):
        raise ConstraintError("study area requires an explicit CRS")
    collection = reproject_features(
        {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": scene.study_area}],
        },
        crs,
        f"{crs} -> {grid.crs}",
    )
    if not isinstance(collection, dict) or not isinstance(collection.get("features"), list):
        raise ConstraintError("study area geometry unavailable")
    features = collection["features"]
    if not isinstance(features, list) or not isinstance(features[0], dict):
        raise ConstraintError("study area feature unavailable")
    geometry = features[0]["geometry"]
    polygon = shape(geometry)
    if (
        not polygon.is_valid
        or polygon.is_empty
        or polygon.geom_type not in {"Polygon", "MultiPolygon"}
    ):
        raise ConstraintError("study area must be a valid nonempty polygon")
    active = np.asarray(
        rasterize(
            [(geometry, 1)],
            out_shape=grid.values.shape,
            transform=grid.transform,
            fill=0,
            all_touched=False,
        ),
        dtype=bool,
    )
    if not np.any(active):
        raise ConstraintError("study area contains no target cell centres")
    return scene, grid, active


def _matrix(value: JsonValue, shape_expected: tuple[int, ...], label: str) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ConstraintError(f"{label} must be a numeric grid") from exc
    if array.shape != shape_expected or np.any(np.isinf(array)):
        raise ConstraintError(f"{label} shape differs from saved target grid or contains infinity")
    return array


def _nullable(array: np.ndarray) -> list[JsonValue]:
    return [[float(value) if np.isfinite(value) else None for value in row] for row in array]


def screening_component(
    context: dict[str, JsonValue], inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    scene, grid, active = _scene_grid(context)
    dem = _matrix(inputs.get("dem"), grid.values.shape, "DEM").copy()
    dem[~active] = np.nan
    baseline = scene.scenario_conditions.get("sea_level_baseline_m")
    increment = parameters.get("increment")
    connectivity = parameters.get("connectivity", 4)
    datum = scene.scenario_conditions.get("vertical_datum")
    if (
        isinstance(baseline, bool)
        or not isinstance(baseline, (int, float))
        or isinstance(increment, bool)
        or not isinstance(increment, (int, float))
        or isinstance(connectivity, bool)
        or connectivity not in (4, 8)
        or not isinstance(datum, str)
    ):
        raise ConstraintError(
            "explicit baseline, increment, datum and 4/8 connectivity are required"
        )
    seeds = TypeAdapter(list[tuple[int, int]]).validate_python(
        scene.scenario_conditions.get("coastal_seeds")
    )
    result = screen_inundation(
        dem,
        baseline=float(baseline),
        increment=float(increment),
        seeds=seeds,
        connectivity=int(connectivity),
        dem_datum=datum,
        water_datum=datum,
        cell_area=grid.cell_area_m2,
    )
    wet = result.mask == 1
    features: list[JsonValue] = []
    for geometry, _ in shapes(
        wet.astype("uint8"), mask=wet, transform=grid.transform, connectivity=int(connectivity)
    ):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "method": METHOD,
                    "absolute_water_level_m": result.absolute_water_level,
                },
                "geometry": geometry,
            }
        )
    geographic = reproject_features(
        {"type": "FeatureCollection", "features": features}, grid.crs, f"{grid.crs} -> EPSG:4326"
    )
    if not isinstance(geographic, dict):
        raise ConstraintError("screening polygon output unavailable")
    geographic.pop("crs", None)  # RFC 7946 GeoJSON is always longitude/latitude.
    mask = result.mask.astype(float)
    mask[mask == -1] = np.nan
    return {"inundation": _nullable(mask), "polygons": geographic, "area_m2": result.area}


def overlay_component(
    context: dict[str, JsonValue], inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    scene, grid, active = _scene_grid(context)
    if scene.scenario_conditions.get("population_distribution") != "uniform_within_management_unit":
        raise ConstraintError(
            "population allocation requires an explicit uniform-distribution assumption"
        )
    mask = _matrix(inputs.get("inundation"), grid.values.shape, "inundation")
    if np.any(np.isfinite(mask) & ~np.isin(mask, [0, 1])):
        raise ConstraintError("inundation must contain 0, 1 or NoData")
    cover = _matrix(inputs.get("land_cover"), grid.values.shape, "land cover")
    known_cover = cover[np.isfinite(cover)]
    if np.any(known_cover != np.floor(known_cover)):
        raise ConstraintError("land-cover classes must be integral")
    units = inputs.get("units")
    if not isinstance(units, dict) or not isinstance(units.get("crs"), str):
        raise ConstraintError("management units require explicit CRS")
    source_crs = units["crs"]
    if not isinstance(source_crs, str):
        raise ConstraintError("management unit CRS missing")
    transformed = reproject_features(units, source_crs, f"{source_crs} -> {grid.crs}")
    if not isinstance(transformed, dict) or not isinstance(transformed.get("features"), list):
        raise ConstraintError("management unit features missing")
    features = transformed["features"]
    if not isinstance(features, list) or not features:
        raise ConstraintError("management unit collection is empty")
    footprint = Polygon(
        [
            grid.transform @ coordinate
            for coordinate in (
                (0, 0),
                (grid.values.shape[1], 0),
                (grid.values.shape[1], grid.values.shape[0]),
                (0, grid.values.shape[0]),
            )
        ]
    )
    zones = np.zeros(grid.values.shape, dtype=int)
    identifiers: list[str] = []
    for index, feature in enumerate(features, start=1):
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            raise ConstraintError("management unit attributes missing")
        properties = feature["properties"]
        if not isinstance(properties, dict):
            raise ConstraintError("management unit attributes missing")
        identifier = properties.get("unit_id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ConstraintError("management unit identifiers must be unique strings")
        geometry = feature.get("geometry")
        polygon = shape(geometry)
        if (
            not polygon.is_valid
            or polygon.is_empty
            or polygon.geom_type not in {"Polygon", "MultiPolygon"}
        ):
            raise ConstraintError("management units must be valid polygons")
        if not footprint.buffer(1e-6).covers(polygon):
            raise ConstraintError(
                "population allocation requires complete management unit coverage"
            )
        cells = rasterize(
            [(geometry, 1)],
            out_shape=grid.values.shape,
            transform=grid.transform,
            fill=0,
            all_touched=False,
        ).astype(bool)
        if not np.any(cells) or np.any(cells & (zones != 0)):
            raise ConstraintError("management unit cell centres overlap or are absent")
        zones[cells] = index
        identifiers.append(identifier)
    if np.any(active & (zones == 0)):
        raise ConstraintError("management units do not cover study-area cell centres")
    table = inputs.get("population")
    if not isinstance(table, dict) or not isinstance(table.get("column_units"), dict):
        raise ConstraintError("population table requires declared column units")
    column_units = table["column_units"]
    if not isinstance(column_units, dict) or column_units.get("population") != "person":
        raise ConstraintError("population must be a person count, not density or percentage")
    rows = table.get("rows")
    if not isinstance(rows, list):
        raise ConstraintError("population table rows missing")
    populations: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ConstraintError("population record must be an object")
        record = PopulationRecord.model_validate(
            {"unit_id": row.get("unit_id"), "population": row.get("population")}
        )
        if record.unit_id in populations:
            raise ConstraintError("duplicate population unit")
        populations[record.unit_id] = record.population
    if set(populations) != set(identifiers):
        raise ConstraintError("population records and management units differ")
    population = np.zeros(grid.values.shape, dtype=float)
    for index, identifier in enumerate(identifiers, start=1):
        cells = zones == index
        population[cells] = populations[identifier] / np.count_nonzero(cells)
    impacts = ImpactGrid.model_validate(
        {
            "unit_ids": identifiers,
            "zones": zones.tolist(),
            "inundation": _nullable(mask),
            "land_cover": _nullable(cover),
            "population": population.tolist(),
            "cell_area_m2": grid.cell_area_m2,
            "active": active.tolist(),
        }
    )
    return {"impacts": impacts.model_dump(mode="json")}


def statistics_component(
    context: dict[str, JsonValue], inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    _, grid, active = _scene_grid(context)
    impacts = ImpactGrid.model_validate(inputs.get("impacts"))
    mask = _matrix([list(row) for row in impacts.inundation], grid.values.shape, "inundation")
    cover = _matrix([list(row) for row in impacts.land_cover], grid.values.shape, "land cover")
    if np.any(np.isfinite(mask) & ~np.isin(mask, [0, 1])):
        raise ConstraintError("inundation must contain 0, 1 or NoData")
    observed_cover = cover[np.isfinite(cover)]
    if np.any(observed_cover != np.floor(observed_cover)):
        raise ConstraintError("land-cover classes must be integral")
    zones = np.asarray(impacts.zones, dtype=int)
    population = np.asarray(impacts.population, dtype=float)
    if (
        zones.shape != grid.values.shape
        or population.shape != grid.values.shape
        or not np.array_equal(np.asarray(impacts.active), active)
        or not math.isclose(impacts.cell_area_m2, grid.cell_area_m2, rel_tol=1e-12)
        or np.any(population < 0)
        or len(set(impacts.unit_ids)) != len(impacts.unit_ids)
        or np.any(active & ((zones < 1) | (zones > len(impacts.unit_ids))))
    ):
        raise ConstraintError("impact grids or entity alignment differ from the saved scene")
    wet = active & (mask == 1)
    unknown = active & ~np.isfinite(mask)
    units: dict[str, JsonValue] = {}
    for index, identifier in enumerate(impacts.unit_ids, start=1):
        cells = zones == index
        if not np.any(cells):
            raise ConstraintError("management unit has no target-grid support")
        if not np.allclose(population[cells], population[cells][0], rtol=1e-12, atol=0):
            raise ConstraintError("population grid contradicts the declared uniform allocation")
        units[identifier] = {
            "inundated_area_m2": float(np.count_nonzero(cells & wet) * grid.cell_area_m2),
            "unknown_area_m2": float(np.count_nonzero(cells & unknown) * grid.cell_area_m2),
            "study_area_m2": float(np.count_nonzero(cells & active) * grid.cell_area_m2),
            "estimated_population": float(population[cells & wet].sum()),
            "population_in_unknown_dem_area": float(population[cells & unknown].sum()),
            "fraction": float(np.count_nonzero(cells & wet) / np.count_nonzero(cells)),
        }
    categories: dict[str, JsonValue] = {
        str(int(value)): float(np.count_nonzero(wet & (cover == value)) * grid.cell_area_m2)
        for value in np.unique(cover[wet & np.isfinite(cover)])
    }
    return {
        "statistics": {
            "method": METHOD,
            "population_assumption": "uniform within each management unit",
            "allocation_support": "cell-centre rasterization of complete management units",
            "units": units,
            "inundated_area_m2": float(np.count_nonzero(wet) * grid.cell_area_m2),
            "estimated_affected_population": float(population[wet].sum()),
            "unknown_area_m2": float(np.count_nonzero(unknown) * grid.cell_area_m2),
            "population_in_unknown_dem_area": float(population[unknown].sum()),
            "unknown_land_cover_wet_area_m2": float(
                np.count_nonzero(wet & ~np.isfinite(cover)) * grid.cell_area_m2
            ),
            "land_cover_area_m2": categories,
        }
    }
