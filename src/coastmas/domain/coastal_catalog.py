"""Registered coastal demonstration components and their measured sample checks."""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from pydantic import JsonValue

from coastmas.adapters.geofiles import decode_geotiff
from coastmas.adapters.runtime import PythonFunctionAdapter
from coastmas.core.contracts import UNITS, ModelSpec, SceneSpec, VariableSpec
from coastmas.core.errors import CoastMASError
from coastmas.domain.builtin_catalog import BuiltinCatalog, assessment_catalog
from coastmas.domain.coastal_components import (
    ImpactGrid,
    overlay_component,
    screening_component,
    statistics_component,
)
from coastmas.domain.optimization_catalog import optimization_catalog
from coastmas.domain.scenarios import verify_samples


def coastal_sample_scene(directory: Path, *, identifier: str = "coastal-demo-scene") -> SceneSpec:
    manifest = verify_samples(directory)
    dem = decode_geotiff((directory / "dem.tif").read_bytes())
    aoi = json.loads((directory / "coastal_aoi.geojson").read_text())["features"][0]["geometry"]
    return SceneSpec.model_validate(
        {
            "id": identifier,
            "name": "Synthetic coastal inundation screening",
            "version": 1,
            "management_goal": "Screen inundation and population/land-use impacts by unit",
            "study_area": aoi,
            "entity_types": ["management_unit"],
            "time_range": {"start": "2020-01-01T00:00:00Z", "end": "2023-01-01T00:00:00Z"},
            "scenario_conditions": {
                "vertical_datum": manifest.vertical_datum,
                "sea_level_baseline_m": manifest.baseline_m,
                "coastal_seeds": [list(seed) for seed in manifest.seeds],
                "population_distribution": "uniform_within_management_unit",
                "data_label": manifest.label,
            },
            "constraints": [],
            "required_outputs": ["statistics", "polygons", "inundation"],
            "data_policy": {
                "study_area_crs": "EPSG:4326",
                "target_grid": {
                    "crs": dem.crs,
                    "transform": list(dem.transform)[:6],
                    "height": dem.values.shape[0],
                    "width": dem.values.shape[1],
                },
            },
            "quality_requirements": {"method_scope": "screening, not hydrodynamics"},
        }
    )


def _number(value: JsonValue) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CoastMASError("BUILTIN_VALIDATION_FAILED", "golden result is not a number")
    return float(value)


def _coastal_goldens(directory: Path) -> dict[str, float]:
    scene = coastal_sample_scene(directory)
    context: dict[str, JsonValue] = {"scene": scene.model_dump(mode="json")}
    dem = decode_geotiff((directory / "dem.tif").read_bytes())
    cover = decode_geotiff((directory / "land_cover_t1.tif").read_bytes())
    boundaries = json.loads((directory / "management_units.geojson").read_text())
    boundaries["crs"] = "EPSG:4326"
    with (directory / "population.csv").open() as stream:
        population: dict[str, JsonValue] = {
            "rows": [dict(row) for row in csv.DictReader(stream)],
            "column_units": {"population": "person"},
            "unit_source": "catalog_declaration",
        }
    screen = screening_component(context, {"dem": dem.values.tolist()}, {"increment": 0.5})
    overlay = overlay_component(
        context,
        {
            "inundation": screen["inundation"],
            "land_cover": cover.values.tolist(),
            "units": boundaries,
            "population": population,
        },
        {},
    )
    impacts = ImpactGrid.model_validate(overlay["impacts"])
    values = np.asarray(impacts.population)[np.asarray(impacts.inundation) == 1]
    output = statistics_component(context, overlay, {})["statistics"]
    if not isinstance(output, dict):
        raise CoastMASError("BUILTIN_VALIDATION_FAILED", "coastal statistics missing")
    errors = {
        "screening": abs(_number(screen["area_m2"]) - 80000),
        "overlay": abs(float(values.sum()) - 320),
        "statistics": max(
            abs(_number(output["estimated_affected_population"]) - 320),
            abs(_number(output["inundated_area_m2"]) - 80000),
        ),
    }
    if any(not np.isfinite(error) or error > 1e-9 for error in errors.values()):
        raise CoastMASError("BUILTIN_VALIDATION_FAILED", "coastal sample golden checks failed")
    return errors


def _variable(
    name: str,
    standard: str,
    data_type: str,
    *,
    unit: str = "1",
    support: str = "grid",
    semantic: str = "continuous",
    aggregation: str = "intensive",
    nodata: str = "mask",
) -> VariableSpec:
    return VariableSpec.model_validate(
        {
            "name": name,
            "standard_name": standard,
            "description": standard,
            "data_type": data_type,
            "unit": unit,
            "dimension": str(UNITS.get_dimensionality(unit)),
            "semantic_type": semantic,
            "spatial_support": support,
            "temporal_support": "instant",
            "aggregation_type": aggregation,
            "nodata_policy": nodata,
            "required": True,
        }
    )


def coastal_catalog(project_id: str, directory: Path) -> BuiltinCatalog:
    catalog = assessment_catalog(project_id)
    errors = _coastal_goldens(directory)
    dem = _variable("dem", "elevation", "raster", unit="m")
    mask = _variable(
        "inundation",
        "potential_inundation",
        "raster",
        semantic="categorical",
        aggregation="categorical",
    )
    cover = _variable(
        "land_cover", "land_cover", "raster", semantic="categorical", aggregation="categorical"
    )
    boundaries = _variable(
        "units",
        "management_units",
        "json",
        support="management_unit",
        semantic="categorical",
        aggregation="categorical",
    )
    population = _variable(
        "population",
        "management_population",
        "json",
        support="management_unit",
        semantic="extensive",
        aggregation="extensive",
        nodata="reject",
    )
    impacts = _variable("impacts", "coastal_impact_grid", "json")
    statistics = _variable(
        "statistics", "coastal_management_statistics", "json", support="management_unit"
    )
    polygons = _variable(
        "polygons",
        "potential_inundation_polygons",
        "json",
        support="polygon",
        semantic="categorical",
        aggregation="categorical",
    )
    area = _variable(
        "area_m2",
        "potential_inundation_area",
        "scalar",
        unit="m**2",
        semantic="extensive",
        aggregation="extensive",
        nodata="reject",
    )
    signatures = {
        "screening": ((dem,), (mask, polygons, area), "Sea-level terrain screening", "RASTER"),
        "overlay": (
            (mask, cover, boundaries, population),
            (impacts,),
            "Population and land-use overlay",
            "GIS",
        ),
        "statistics": (
            (impacts,),
            (statistics,),
            "Management-unit impact statistics",
            "STATISTICAL",
        ),
    }
    adapter = PythonFunctionAdapter(
        {},
        max_output_bytes=16 * 1024 * 1024,
        contextual_handlers={
            "screening": screening_component,
            "overlay": overlay_component,
            "statistics": statistics_component,
        },
    )
    models = list(catalog.models)
    optimization = optimization_catalog(project_id)
    for model in optimization.models:
        runtime = optimization.registry.resolve(model)
        catalog.registry.register(model, runtime.adapter, runtime.handler)
        models.append(model)
    # Separate immutable signatures preserve the original management-unit release.
    for support in ("administrative_unit", "custom_polygon", "grid"):
        variant = assessment_catalog(project_id, spatial_support=support)
        for model in variant.models:
            runtime = variant.registry.resolve(model)
            catalog.registry.register(model, runtime.adapter, runtime.handler)
            models.append(model)
    released = datetime(2026, 9, 20, tzinfo=UTC)
    for component, (inputs, outputs, name, model_type) in signatures.items():
        constraints = [
            {
                "field": f"scene.data_policy.{field}",
                "operator": "required",
                "value": None,
                "description": f"explicit scene {field} required",
            }
            for field in ("target_grid", "study_area_crs")
        ]
        if component == "screening":
            constraints.extend(
                {
                    "field": f"scene.scenario_conditions.{field}",
                    "operator": "required",
                    "value": None,
                    "description": f"explicit {field} required",
                }
                for field in ("vertical_datum", "sea_level_baseline_m", "coastal_seeds")
            )
        if component == "overlay":
            constraints.append(
                {
                    "field": "scene.scenario_conditions.population_distribution",
                    "operator": "eq",
                    "value": "uniform_within_management_unit",
                    "description": "uniform population distribution must be explicit",
                }
            )
        model = ModelSpec.model_validate(
            {
                "id": f"builtin:{project_id}:{component}",
                "name": name,
                "display_name": name,
                "version": 1,
                "model_type": model_type,
                "description": "Terrain-connectivity demonstration, not hydrodynamic simulation",
                "capabilities": [component],
                "scientific_domain": ["coastal_risk_screening"],
                "inputs": inputs,
                "outputs": outputs,
                "parameters": [
                    {
                        "name": "increment",
                        "unit": "m",
                        "minimum": 0,
                        "maximum": 10,
                        "default": None,
                        "required": True,
                    },
                    {
                        "name": "connectivity",
                        "unit": "1",
                        "minimum": 4,
                        "maximum": 8,
                        "default": 4,
                        "required": True,
                    },
                ]
                if component == "screening"
                else [],
                "spatial_scale": {"minimum": 1, "maximum": 1e7, "unit": "m"},
                "temporal_scale": {"minimum": 1, "maximum": 1e12, "unit": "s"},
                "supported_geometry": ["grid", "polygon", "multipolygon"],
                "supported_crs": ["EPSG:32650", "EPSG:4326"],
                "runtime_type": "python",
                "runtime_config": {
                    "component": component,
                    "release": "1",
                    "requires_target_grid": True,
                    "requires_projected_grid": True,
                },
                "constraints": constraints,
                "validation_status": "VALIDATED",
                "execution_status": "EXECUTABLE",
                "validation_metrics": {"golden_max_abs_error": errors[component]},
                "references": ["docs/scientific-method.md", "sample-data/manifest.json"],
                "owner": "CoastMAS maintainers",
                "license": "MIT",
                "created_at": released,
                "updated_at": released,
            }
        )
        catalog.registry.register(model, adapter, component)
        models.append(model)
    return BuiltinCatalog(tuple(models), catalog.registry)
