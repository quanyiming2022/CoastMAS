"""Maintainer-owned assessment components with measured startup golden checks.

Metadata uploads cannot register code. These fixed handlers are explicitly
installed by application setup, and their complete ModelSpec snapshot is pinned.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from pydantic import JsonValue

from coastmas.adapters.runtime import PythonFunctionAdapter
from coastmas.core.contracts import ModelSpec, SceneSpec, VariableSpec
from coastmas.core.errors import CoastMASError, ConstraintError
from coastmas.core.execution import ExecutionRegistry
from coastmas.domain.indicator_frames import (
    IndicatorFrame,
    NormalizedFrame,
    ScoreFrame,
    aggregate_frame,
    normalize_frame,
    temporal_change,
    weight_frame,
)


@dataclass(frozen=True)
class BuiltinCatalog:
    models: tuple[ModelSpec, ...]
    registry: ExecutionRegistry


def normalize_component(
    context: dict[str, JsonValue], inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    frame = IndicatorFrame.model_validate(inputs.get("frame"))
    scene = SceneSpec.model_validate(context.get("scene"))
    if frame.years is not None:
        # Frame coordinates are calendar-year labels. Exact observation time remains
        # in the source catalog; this additional check prevents an unrelated period cube.
        if (
            min(frame.years) < scene.time_range.start.year
            or max(frame.years) > scene.time_range.end.year
        ):
            raise ConstraintError("indicator periods fall outside the saved scene years")
    return {"frame": normalize_frame(frame).model_dump(mode="json")}


def weight_component(
    inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    frame = NormalizedFrame.model_validate(inputs.get("frame"))
    method = parameters.get("method", 1)
    if isinstance(method, bool) or method not in (0, 1, 2):
        raise ConstraintError("weight method must be 0=equal, 1=manual or 2=entropy")
    names = {0: "equal", 1: "manual", 2: "entropy"}
    # Literal branches keep method semantics explicit at this typed boundary.
    selected = names[int(method)]
    weights = weight_frame(
        frame,
        method="equal" if selected == "equal" else "manual" if selected == "manual" else "entropy",
    )
    return {"weights": list(weights)}


def numeric_weights(value: JsonValue) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise ConstraintError("weights must be a numeric array")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ConstraintError("weights must be a numeric array")
        result.append(float(item))
    return tuple(result)


def composite_component(
    inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    frame = NormalizedFrame.model_validate(inputs.get("frame"))
    return {
        "scores": aggregate_frame(frame, numeric_weights(inputs.get("weights"))).model_dump(
            mode="json"
        )
    }


def topsis_component(
    inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    frame = NormalizedFrame.model_validate(inputs.get("frame"))
    return {
        "scores": aggregate_frame(
            frame, numeric_weights(inputs.get("weights")), method="topsis"
        ).model_dump(mode="json")
    }


def change_component(
    inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    return {
        "change": temporal_change(ScoreFrame.model_validate(inputs.get("scores"))).model_dump(
            mode="json"
        )
    }


def _golden_errors() -> dict[str, float]:
    source = IndicatorFrame.model_validate(
        {
            "unit_ids": ["a", "b"],
            "columns": [
                {
                    "name": "benefit",
                    "unit": "1",
                    "reference_unit": "1",
                    "lower": 0,
                    "upper": 100,
                    "positive": True,
                    "weight": 1,
                },
                {
                    "name": "pressure",
                    "unit": "1",
                    "reference_unit": "1",
                    "lower": 0,
                    "upper": 100,
                    "positive": False,
                    "weight": 3,
                },
            ],
            "values": [[0, 100], [50, 50]],
        }
    )
    normalized = normalize_frame(source)
    manual = weight_frame(normalized, method="manual")
    scores = aggregate_frame(normalized, manual)
    ideal = aggregate_frame(normalized, manual, method="topsis")
    temporal = source.model_copy(
        update={
            "values": (((0.0, 100.0), (50.0, 50.0)), ((25.0, 75.0), (75.0, 25.0))),
            "years": (2020.0, 2021.0),
        }
    )
    change = temporal_change(aggregate_frame(normalize_frame(temporal), manual))
    errors = {
        "normalize": float(np.max(np.abs(np.asarray(normalized.values) - [[[0, 0], [0.5, 0.5]]]))),
        "weight": float(np.max(np.abs(np.asarray(manual) - [0.25, 0.75]))),
        "composite": float(np.max(np.abs(np.asarray(scores.values) - [[0, 0.5]]))),
        "topsis": float(np.max(np.abs(np.asarray(ideal.values) - [[0, 1]]))),
        "change": float(np.max(np.abs(np.asarray(change.trend) - [0.25, 0.25]))),
    }
    if any(not np.isfinite(value) or value > 1e-12 for value in errors.values()):
        raise CoastMASError("BUILTIN_VALIDATION_FAILED", "assessment golden check failed")
    return errors


def _variable(name: str, standard: str, *, array: bool = False) -> VariableSpec:
    return VariableSpec(
        name=name,
        standard_name=standard,
        description=standard,
        data_type="array" if array else "json",
        unit="1",
        dimension="dimensionless",
        semantic_type="continuous",
        spatial_support="management_unit",
        temporal_support="declared_period",
        aggregation_type="intensive",
        nodata_policy="reject",
        required=True,
    )


def assessment_catalog(project_id: str) -> BuiltinCatalog:
    """Register fixed code only after real golden computations pass; no fabricated metrics."""
    errors = _golden_errors()
    raw = _variable("frame", "indicator_frame")
    normalized = _variable("frame", "normalized_indicator_frame")
    weights = _variable("weights", "indicator_weights", array=True)
    scores = _variable("scores", "assessment_scores")
    change = _variable("change", "temporal_assessment_change")
    signatures = {
        "normalize": ((raw,), (normalized,), "Indicator normalization"),
        "weight": ((normalized,), (weights,), "Indicator weighting"),
        "composite": ((normalized, weights), (scores,), "Weighted composite assessment"),
        "topsis": ((normalized, weights), (scores,), "TOPSIS assessment"),
        "change": ((scores,), (change,), "Temporal change and trend"),
    }
    adapter = PythonFunctionAdapter(
        {
            "weight": weight_component,
            "composite": composite_component,
            "topsis": topsis_component,
            "change": change_component,
        },
        contextual_handlers={"normalize": normalize_component},
    )
    registry = ExecutionRegistry()
    models: list[ModelSpec] = []
    # Fixed component release timestamp is part of each immutable version, not run time.
    released = datetime(2026, 9, 20, tzinfo=UTC)
    for component, (inputs, outputs, name) in signatures.items():
        model = ModelSpec.model_validate(
            {
                "id": f"builtin:{project_id}:{component}",
                "name": name,
                "display_name": name,
                "version": 1,
                "model_type": "STATISTICAL",
                "description": "Deterministic assessment with explicit entity and unit metadata",
                "capabilities": [component],
                "scientific_domain": ["coastal_sustainability"],
                "inputs": inputs,
                "outputs": outputs,
                "parameters": [
                    {
                        "name": "method",
                        "unit": "1",
                        "minimum": 0,
                        "maximum": 2,
                        "default": 1,
                        "required": True,
                    }
                ]
                if component == "weight"
                else [],
                "spatial_scale": {"minimum": 1, "maximum": 1e9, "unit": "m"},
                "temporal_scale": {"minimum": 1, "maximum": 1e12, "unit": "s"},
                "supported_geometry": ["grid", "point", "polygon", "multipolygon"],
                "supported_crs": ["EPSG:32650", "EPSG:4326"],
                "runtime_type": "python",
                "runtime_config": {"component": component, "release": "1"},
                "constraints": [],
                "validation_status": "VALIDATED",
                "execution_status": "EXECUTABLE",
                "validation_metrics": {"golden_max_abs_error": errors[component]},
                "references": ["docs/scientific-method.md"],
                "owner": "CoastMAS maintainers",
                "license": "MIT",
                "created_at": released,
                "updated_at": released,
            }
        )
        registry.register(model, adapter, component)
        models.append(model)
    return BuiltinCatalog(tuple(models), registry)
