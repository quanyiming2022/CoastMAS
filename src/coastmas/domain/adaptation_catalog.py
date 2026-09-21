"""Trusted explicit scientific adaptation nodes, independent of uploaded executable code."""

from datetime import UTC, datetime

from pydantic import JsonValue

from coastmas.adapters.runtime import PythonFunctionAdapter
from coastmas.core.contracts import ModelSpec, SceneSpec, VariableSpec
from coastmas.core.errors import ConstraintError
from coastmas.core.execution import ExecutionRegistry
from coastmas.core.temporal_adaptation import TemporalRequest, adapt_time_series
from coastmas.domain.builtin_catalog import BuiltinCatalog


def temporal_component(
    context: dict[str, JsonValue], inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    try:
        request = TemporalRequest.model_validate(inputs.get("request"))
        scene = SceneSpec.model_validate(context.get("scene"))
        start = request.target_time or request.window_start
        end = request.target_time or request.window_end
        if start != scene.time_range.start or end != scene.time_range.end:
            raise ValueError("temporal target must match the scene time range exactly")
        result = adapt_time_series(request)
    except (ValueError, OverflowError) as exc:
        raise ConstraintError(str(exc)) from exc
    return {"result": result.model_dump(mode="json")}


def adaptation_catalog(project_id: str) -> BuiltinCatalog:
    registry = ExecutionRegistry()
    released = datetime(2026, 9, 21, tzinfo=UTC)
    variables = [
        VariableSpec(
            name=name,
            standard_name="temporal_adaptation_" + name,
            description="Structured temporal values with explicit internal units and support",
            data_type="json",
            unit="1",
            dimension="dimensionless",
            semantic_type="continuous",
            spatial_support="nonspatial",
            temporal_support="explicit_support",
            aggregation_type="intensive",
            nodata_policy="propagate",
            required=True,
        )
        for name in ("request", "result")
    ]
    golden = TemporalRequest.model_validate(
        {
            "variable": "temperature",
            "unit": "degC",
            "output_unit": "kelvin",
            "aggregation_type": "intensive",
            "support": "interval",
            "method": "mean",
            "window_start": "2025-01-01T00:00:00Z",
            "window_end": "2025-01-01T04:00:00Z",
            "observations": [
                {"start": "2025-01-01T00:00:00Z", "end": "2025-01-01T01:00:00Z", "value": 10},
                {"start": "2025-01-01T01:00:00Z", "end": "2025-01-01T04:00:00Z", "value": 20},
            ],
        }
    )
    measured = adapt_time_series(golden).value
    if measured is None or abs(measured - 290.65) > 1e-12:
        raise ConstraintError("temporal golden validation failed")
    model = ModelSpec(
        id=f"builtin:{project_id}:temporal_adaptation",
        name="时间适配",
        display_name="时间适配",
        version=1,
        model_type="STATISTICAL",
        description="Explicit point/interval support; no extrapolation or missing-value inference",
        capabilities=("temporal_adaptation",),
        scientific_domain=("scientific_data_adaptation",),
        inputs=(variables[0],),
        outputs=(variables[1],),
        parameters=(),
        spatial_scale={"unit": "m"},
        temporal_scale={"unit": "s"},
        supported_geometry=(),
        supported_crs=(),
        runtime_type="python",
        runtime_config={"component": "temporal_adaptation", "release": "1"},
        constraints=(),
        validation_status="VALIDATED",
        execution_status="EXECUTABLE",
        validation_metrics={"golden_max_abs_error": abs(measured - 290.65)},
        references=("docs/temporal-adaptation.md",),
        owner="CoastMAS maintainers",
        license="MIT",
        created_at=released,
        updated_at=released,
    )
    registry.register(
        model,
        PythonFunctionAdapter({}, contextual_handlers={"temporal_adaptation": temporal_component}),
        "temporal_adaptation",
    )
    return BuiltinCatalog((model,), registry)
