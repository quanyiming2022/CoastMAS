"""Fixed optical model signatures; real imagery does not self-authorize executable code."""

from datetime import UTC, datetime

import numpy as np

from coastmas.adapters.runtime import PythonFunctionAdapter
from coastmas.core.contracts import ModelSpec, VariableSpec
from coastmas.core.execution import ExecutionRegistry
from coastmas.domain.builtin_catalog import BuiltinCatalog
from coastmas.domain.remote_sensing import normalized_difference
from coastmas.domain.remote_sensing_components import (
    vegetation_change,
    vegetation_index,
    water_index,
)


def variable(
    name: str, standard: str, *, structured: bool = False, paired: bool = False
) -> VariableSpec:
    return VariableSpec(
        name=name,
        standard_name=standard,
        description=standard,
        data_type="json" if structured else "raster",
        unit="1",
        dimension="dimensionless",
        semantic_type="continuous",
        spatial_support="grid",
        temporal_support="two_acquisitions" if paired else "acquisition",
        aggregation_type="intensive",
        nodata_policy="mask",
        required=True,
    )


def remote_sensing_catalog(project_id: str) -> BuiltinCatalog:
    registry = ExecutionRegistry()
    models = []
    adapter = PythonFunctionAdapter(
        {},
        max_output_bytes=16 * 1024 * 1024,
        contextual_handlers={
            "ndvi": vegetation_index,
            "ndwi": water_index,
            "ndvi_change": vegetation_change,
        },
    )
    error = abs(float(normalized_difference(np.array([[0.6]]), np.array([[0.2]]))[0, 0]) - 0.5)
    if error > 1e-12:
        raise ValueError("optical index golden check failed")
    released = datetime(2026, 9, 21, tzinfo=UTC)
    for component, label, bands in (
        ("ndvi", "植被指数（NDVI）", ("nir", "red")),
        ("ndwi", "水体指数（NDWI）", ("green", "nir")),
        ("ndvi_change", "双期植被指数变化（ΔNDVI）", ("observations",)),
    ):
        spec = ModelSpec.model_validate(
            {
                "id": f"builtin:{project_id}:{component}",
                "name": component.upper(),
                "display_name": label,
                "version": 1,
                "model_type": "RASTER",
                "description": (
                    "Calibrated surface-reflectance normalized difference with explicit NoData"
                ),
                "capabilities": [component],
                "scientific_domain": ["remote_sensing"],
                "inputs": [
                    variable(
                        band,
                        "surface_reflectance_" + band,
                        structured=component == "ndvi_change",
                        paired=component == "ndvi_change",
                    )
                    for band in bands
                ],
                "outputs": [
                    variable(
                        "preview",
                        component + "_preview",
                        structured=True,
                        paired=component == "ndvi_change",
                    ),
                    variable("index", component, paired=component == "ndvi_change"),
                    variable(
                        "summary",
                        component + "_statistics",
                        structured=True,
                        paired=component == "ndvi_change",
                    ),
                ],
                "parameters": [],
                "spatial_scale": {"minimum": 10, "maximum": 1000, "unit": "m"},
                "temporal_scale": {"unit": "s"},
                "supported_geometry": ["grid"],
                "supported_crs": ["EPSG:32650", "EPSG:32651", "EPSG:4326"],
                "runtime_type": "python",
                "runtime_config": {
                    "component": component,
                    "release": "1",
                    "requires_target_grid": True,
                    "requires_projected_grid": True,
                },
                "constraints": [],
                "validation_status": "VALIDATED",
                "execution_status": "EXECUTABLE",
                "validation_metrics": {"golden_max_abs_error": error},
                "references": ["docs/real-imagery-demos.md"],
                "owner": "CoastMAS maintainers",
                "license": "MIT",
                "created_at": released,
                "updated_at": released,
            }
        )
        registry.register(spec, adapter, component)
        models.append(spec)
    return BuiltinCatalog(tuple(models), registry)
