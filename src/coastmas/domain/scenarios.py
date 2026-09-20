"""Real file-to-computation demonstrations; orchestration and UI tested separately.

Administrative population is apportioned uniformly, explicitly an estimate.
Zonal denominator includes all cell centres in a management polygon; unknown
DEM area is reported separately rather than silently counted as dry land.
"""

import csv
import hashlib
import json
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter
from rasterio.features import rasterize  # type: ignore[import-untyped]
from rasterio.warp import transform_geom  # type: ignore[import-untyped]

from coastmas.adapters.geofiles import Grid, decode_geotiff
from coastmas.core.errors import CoastMASError, ConstraintError
from coastmas.core.numeric import FloatArray
from coastmas.domain.assessment import composite, normalize, temporal_assessment
from coastmas.domain.screening import screen_inundation

JSON_OUTPUT = TypeAdapter(dict[str, JsonValue])


class SampleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    label: Literal["SYNTHETIC / DEMONSTRATION DATA"]
    schema_version: Literal["1.0.0"]
    sha256: dict[str, str]
    baseline_m: float
    vertical_datum: str = Field(min_length=1)
    connectivity: Literal[4, 8]
    seeds: list[tuple[int, int]] = Field(min_length=1)
    seed: int


def verify_samples(directory: Path) -> SampleManifest:
    manifest = SampleManifest.model_validate_json((directory / "manifest.json").read_bytes())
    required = {
        "dem.tif",
        "land_cover_t1.tif",
        "management_units.geojson",
        "population.csv",
        "economic.csv",
    }
    if not required.issubset(manifest.sha256):
        raise ConstraintError("sample manifest is missing required datasets")
    for name, expected in manifest.sha256.items():
        path = directory / name
        if Path(name).name != name or path.is_symlink() or not path.is_file():
            raise ConstraintError("invalid sample manifest path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise CoastMASError("CHECKSUM_ERROR", "sample file checksum mismatch", {"file": name})
    return manifest


def management_zones(directory: Path, grid: Grid) -> tuple[FloatArray, list[str]]:
    collection = json.loads((directory / "management_units.geojson").read_text())
    identifiers: list[str] = []
    zones = np.zeros(grid.values.shape, dtype=np.float64)
    for index, feature in enumerate(collection["features"], start=1):
        identifier = feature["properties"]["unit_id"]
        if not isinstance(identifier, str) or identifier in identifiers:
            raise ConstraintError("management unit identifiers must be unique strings")
        geometry = transform_geom("EPSG:4326", grid.crs, feature["geometry"])
        cells = np.asarray(
            rasterize(
                [(geometry, 1)],
                out_shape=grid.values.shape,
                transform=grid.transform,
                fill=0,
                all_touched=False,
            ),
            dtype=bool,
        )
        if np.any((zones != 0) & cells):
            raise ConstraintError(
                "overlapping management unit cell centres require an explicit policy"
            )
        if not np.any(cells):
            raise ConstraintError("management unit has no raster coverage")
        zones[cells] = index
        identifiers.append(identifier)
    if np.any(zones == 0):
        raise ConstraintError("management units do not cover the demonstration grid")
    return zones, identifiers


def run_screening_scenario(directory: Path, *, increment: float) -> dict[str, JsonValue]:
    manifest = verify_samples(directory)
    dem = decode_geotiff((directory / "dem.tif").read_bytes())
    cover = decode_geotiff((directory / "land_cover_t1.tif").read_bytes())
    if (
        dem.unit != "m"
        or dem.crs != cover.crs
        or dem.transform != cover.transform
        or dem.values.shape != cover.values.shape
    ):
        raise ConstraintError("screening grids must align and elevation must be in metres")
    zones, identifiers = management_zones(directory, dem)
    screening = screen_inundation(
        dem.values,
        baseline=manifest.baseline_m,
        increment=increment,
        seeds=manifest.seeds,
        connectivity=manifest.connectivity,
        dem_datum=dem.vertical_datum,
        water_datum=manifest.vertical_datum,
        cell_area=dem.cell_area_m2,
    )
    populations: dict[str, float] = {}
    with (directory / "population.csv").open() as stream:
        for row in csv.DictReader(stream):
            identifier, population = row["unit_id"], float(row["population"])
            if identifier in populations or not np.isfinite(population) or population < 0:
                raise ConstraintError("population records must be unique, finite and nonnegative")
            populations[identifier] = population
    if set(populations) != set(identifiers):
        raise ConstraintError("population and management units differ")
    unit_results: dict[str, object] = {}
    total_population = 0.0
    wet = screening.mask == 1
    for index, identifier in enumerate(identifiers, start=1):
        cells = zones == index
        fraction = float(np.count_nonzero(cells & wet) / np.count_nonzero(cells))
        affected = populations[identifier] * fraction
        total_population += affected
        unit_results[identifier] = {
            "fraction": fraction,
            "estimated_population": affected,
            "inundated_area_m2": float(np.count_nonzero(cells & wet) * dem.cell_area_m2),
            "unknown_area_m2": float(
                np.count_nonzero(cells & (screening.mask == -1)) * dem.cell_area_m2
            ),
        }
    land_area = {
        str(int(value)): float(np.count_nonzero(wet & (cover.values == value)) * dem.cell_area_m2)
        for value in np.unique(cover.values[np.isfinite(cover.values)])
    }
    land_area = {key: area for key, area in land_area.items() if area > 0}
    output = {
        "label": manifest.label,
        "method": "terrain-connectivity screening, not hydrodynamics",
        "inundated_area_m2": screening.area,
        "estimated_affected_population": total_population,
        "population_assumption": "uniform within each management unit",
        "units": unit_results,
        "land_cover_area_m2": land_area,
        "unknown_land_cover_wet_area_m2": float(
            np.count_nonzero(wet & ~np.isfinite(cover.values)) * dem.cell_area_m2
        ),
        "mask": screening.mask.tolist(),
        "baseline_m": manifest.baseline_m,
        "increment_m": increment,
        "absolute_water_level_m": screening.absolute_water_level,
        "vertical_datum": manifest.vertical_datum,
        "connectivity": manifest.connectivity,
        "seeds": [list(seed) for seed in manifest.seeds],
        "input_sha256": manifest.sha256,
    }
    return JSON_OUTPUT.validate_python(output)


def run_assessment_scenarios(directory: Path) -> dict[str, JsonValue]:
    manifest = verify_samples(directory)
    records: dict[tuple[int, str], tuple[float, float]] = {}
    with (directory / "economic.csv").open() as stream:
        for row in csv.DictReader(stream):
            key = int(row["year"]), row["unit_id"]
            if key in records:
                raise ConstraintError("duplicate assessment unit and period")
            records[key] = float(row["economic"]), float(row["pressure"])
    years = sorted({key[0] for key in records})
    units = sorted({key[1] for key in records})
    if not years or any((year, unit) not in records for year in years for unit in units):
        raise ConstraintError("assessment has incomplete unit-period coverage")
    cube = np.array([[records[(year, unit)] for unit in units] for year in years], dtype=np.float64)
    lower, upper, positive, weights = [0.0, 0.0], [100.0, 100.0], [True, False], [0.5, 0.5]
    scores = composite(normalize(cube[0], lower, upper, positive), weights)
    dynamic = temporal_assessment(cube, lower, upper, positive, weights, years)
    return JSON_OUTPUT.validate_python(
        {
            "label": manifest.label,
            "units": units,
            "years": years,
            "framework": {
                "version": "1.0.0",
                "lower": lower,
                "upper": upper,
                "positive": positive,
                "weights": weights,
            },
            "scenario_b": {"scores": scores.tolist()},
            "scenario_c": {
                "scores": dynamic.scores.tolist(),
                "ranks": dynamic.ranks.tolist(),
                "change": dynamic.change.tolist(),
                "trend_per_year": dynamic.trend.tolist(),
            },
            "input_sha256": manifest.sha256,
        }
    )
