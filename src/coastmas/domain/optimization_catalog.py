"""Maintainer-installed MILP runtime; uploaded metadata never registers executable code."""

from datetime import UTC, datetime

from coastmas.adapters.runtime import PythonFunctionAdapter
from coastmas.core.contracts import ModelSpec, VariableSpec
from coastmas.core.errors import CoastMASError
from coastmas.core.execution import ExecutionRegistry
from coastmas.core.optimization import CandidateUnit
from coastmas.domain.builtin_catalog import BuiltinCatalog
from coastmas.domain.optimization import optimize_units
from coastmas.domain.optimization_components import optimize_component


def _golden_error() -> float:
    result = optimize_units(
        [
            CandidateUnit(
                id="protected",
                benefit=10000,
                cost=0,
                area=10,
                ecological_cost=0,
                risk=0,
                allowed=False,
            ),
            CandidateUnit(id="a", benefit=6, cost=4, area=2, ecological_cost=1, risk=1),
            CandidateUnit(id="b", benefit=4, cost=3, area=2, ecological_cost=1, risk=1),
        ],
        budget=4,
        minimum_area=2,
        maximum_ecological_cost=1,
        maximum_risk=1,
        time_limit=5,
    )
    if (
        result.status != "OPTIMAL"
        or result.selected != ("a",)
        or not result.constraints_satisfied
        or result.benefit is None
    ):
        raise CoastMASError("BUILTIN_VALIDATION_FAILED", "optimization golden allocation failed")
    error = abs(result.benefit - 6)
    if error > 1e-10:
        raise CoastMASError("BUILTIN_VALIDATION_FAILED", "optimization golden objective failed")
    return error


def optimization_catalog(project_id: str) -> BuiltinCatalog:
    error = _golden_error()
    variables = [
        VariableSpec(
            name=name,
            standard_name=standard,
            description=description,
            data_type="json",
            unit="1",
            dimension="dimensionless",
            semantic_type="continuous",
            spatial_support="management_unit",
            temporal_support="declared_period",
            aggregation_type="intensive",
            nodata_policy="reject",
            required=True,
        )
        for name, standard, description in (
            (
                "candidates",
                "spatial_optimization_candidates",
                "Structured additive quantities with explicit per-column units and hard bounds",
            ),
            (
                "allocation",
                "spatial_optimization_allocation",
                (
                    "Verified binary allocation, units and feasibility; "
                    "never an automatic policy decision"
                ),
            ),
        )
    ]
    released = datetime(2026, 9, 21, tzinfo=UTC)
    model = ModelSpec.model_validate(
        {
            "id": f"builtin:{project_id}:spatial_optimization",
            "name": "SpatialOptimizationModel",
            "display_name": "Spatial allocation with hard constraints",
            "version": 1,
            "model_type": "OPTIMIZATION",
            "description": (
                "Bounded binary MILP maximizing additive benefit under hard budget, "
                "area, ecological cost, additive risk and protected-unit constraints"
            ),
            "capabilities": ["spatial_optimization"],
            "scientific_domain": ["coastal_sustainability"],
            "inputs": [variables[0]],
            "outputs": [variables[1]],
            "parameters": [
                {
                    "name": "time_limit",
                    "unit": "s",
                    "minimum": 0.01,
                    "maximum": 120,
                    "default": None,
                    "required": True,
                    "description": "Solver time budget; timeout and infeasibility remain explicit",
                }
            ],
            "spatial_scale": {"minimum": 1, "maximum": 1e9, "unit": "m"},
            "temporal_scale": {"minimum": 1, "maximum": 1e12, "unit": "s"},
            "supported_geometry": ["polygon", "multipolygon"],
            "supported_crs": ["EPSG:32650", "EPSG:4326"],
            "runtime_type": "python",
            "runtime_config": {"component": "spatial_optimization", "release": "1"},
            "constraints": [],
            "validation_status": "VALIDATED",
            "execution_status": "EXECUTABLE",
            "validation_metrics": {"golden_max_abs_error": error},
            "references": ["docs/scientific-method.md"],
            "owner": "CoastMAS maintainers",
            "license": "MIT",
            "created_at": released,
            "updated_at": released,
        }
    )
    registry = ExecutionRegistry()
    registry.register(
        model,
        PythonFunctionAdapter({}, contextual_handlers={"spatial_optimization": optimize_component}),
        "spatial_optimization",
    )
    return BuiltinCatalog((model,), registry)
