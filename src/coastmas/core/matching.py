"""Deterministic single-model retrieval with hard rejection before soft ranking.

This produces candidate fragments, not a claim that an entire scene is solved.
Scores are transparent retrieval heuristics, never scientific validation metrics.
"""

import math
from dataclasses import dataclass
from typing import Annotated, Self

from pydantic import Field, model_validator

from coastmas.core.contracts import (
    BindingPlan,
    BindingTarget,
    Contract,
    DataAssetSpec,
    ExecutionPolicy,
    ModelSpec,
    SceneSpec,
    VersionReference,
    WorkflowNode,
    WorkflowSpec,
)
from coastmas.core.validation import ValidationIssue, validate_asset_binding, validate_workflow

Weight = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class MatchWeights(Contract):
    capability: Weight = 1
    data_availability: Weight = 1
    scale_fitness: Weight = 1
    validation_evidence: Weight = 1
    runtime_cost: Weight = 1
    user_preference: Weight = 1

    @model_validator(mode="after")
    def positive_total(self) -> Self:
        if sum(self.model_dump().values()) <= 0:
            raise ValueError("at least one ranking weight must be positive")
        return self


@dataclass(frozen=True)
class ModelMatch:
    model_id: str
    model_version: int
    score: float | None
    components: dict[str, float | None]
    issues: tuple[ValidationIssue, ...]
    workflow: WorkflowSpec | None


@dataclass(frozen=True)
class MatchResult:
    ranked: tuple[ModelMatch, ...]
    rejected: tuple[ModelMatch, ...]


def _validate_scores(values: dict[str, float], *, preference: bool) -> None:
    for value in values.values():
        if (
            isinstance(value, bool)
            or not math.isfinite(value)
            or value < 0
            or (preference and value > 1)
        ):
            raise ValueError("preference must be in [0,1]; runtime must be finite and nonnegative")


def _fragment(
    model: ModelSpec, assets: list[DataAssetSpec], scene: SceneSpec, parameters: dict[str, float]
) -> tuple[WorkflowSpec, list[ValidationIssue]]:
    bindings: list[BindingPlan] = []
    failures: list[ValidationIssue] = []
    for variable in model.inputs:
        valid: list[BindingPlan] = []
        invalid: list[ValidationIssue] = []
        for asset in assets:
            # Ignore unrelated assets, but retain failed compatibility checks for relevant data.
            if not any(item.standard_name == variable.standard_name for item in asset.variables):
                continue
            candidate = BindingPlan(
                source=VersionReference(id=asset.id, version=asset.version),
                target=BindingTarget(node_id="candidate", variable=variable.name),
                semantic_mapping="exact_standard_name",
                unit_conversion=None,
                crs_transform=None,
                resampling=None,
                temporal_transform=None,
                quality_check=(),
                status="MANUAL_REVIEW",
            )
            report = validate_asset_binding(asset, variable, model, scene, candidate)
            valid.extend(report.bindings)
            invalid.extend(report.issues)
        if valid:
            # Prefer fewer actual transformations; ties are stable across catalog ordering.
            valid.sort(
                key=lambda item: (
                    sum(
                        value is not None
                        for value in (
                            item.unit_conversion,
                            item.crs_transform,
                            item.temporal_transform,
                        )
                    ),
                    item.source.id,
                    item.source.version,
                )
            )
            bindings.append(valid[0])
        elif variable.required:
            failures.extend(invalid)
    fragment = WorkflowSpec(
        id=f"candidate-{model.id}-{model.version}",
        name=model.name,
        version=1,
        scene_type="candidate_fragment",
        nodes=(
            WorkflowNode(
                id="candidate",
                model_id=model.id,
                model_version=model.version,
                parameters=parameters,
            ),
        ),
        edges=(),
        input_bindings=tuple(bindings),
        parameter_bindings=(),
        constraints=(),
        validation_rules=(),
        execution_policy=ExecutionPolicy(timeout_seconds=60, max_retries=0),
        output_definition=tuple(
            BindingTarget(node_id="candidate", variable=item.name) for item in model.outputs
        ),
    )
    return fragment, failures


def match_models(
    models: list[ModelSpec],
    assets: list[DataAssetSpec],
    scene: SceneSpec,
    *,
    capability: str,
    parameters: dict[str, float],
    weights: MatchWeights | None = None,
    runtime_seconds: dict[str, float] | None = None,
    preferences: dict[str, float] | None = None,
) -> MatchResult:
    """Filter authorized catalog snapshots; caller is responsible for project visibility.

    Runtime estimates must be supplied from measurements; missing values remain null.
    Missing components contribute zero with the full configured denominator, so absent
    evidence does not improve a candidate's score. Preference is explicitly user supplied.
    """
    if len({(item.id, item.version) for item in models}) != len(models):
        raise ValueError("duplicate model version")
    if len({(item.id, item.version) for item in assets}) != len(assets):
        raise ValueError("duplicate data version")
    runtimes = runtime_seconds or {}
    preferences = preferences or {}
    _validate_scores(runtimes, preference=False)
    _validate_scores(preferences, preference=True)
    configured = (weights or MatchWeights()).model_dump()
    total_weight = sum(configured.values())
    ranked: list[ModelMatch] = []
    rejected: list[ModelMatch] = []
    for model in models:
        fragment, failures = _fragment(model, assets, scene, parameters)
        report = validate_workflow(fragment, [model], assets, scene)
        failures.extend(report.issues)
        if capability not in model.capabilities:
            failures.append(ValidationIssue("CAPABILITY", "requested capability is not declared"))
        if failures:
            rejected.append(
                ModelMatch(model.id, model.version, None, {}, tuple(dict.fromkeys(failures)), None)
            )
            continue
        fragment = fragment.model_copy(update={"input_bindings": report.bindings})
        required = {item.name for item in model.inputs if item.required}
        bound = {item.target.variable for item in report.bindings}
        # Scale compatibility is binary here; applicability has already been hard checked.
        # Evidence presence means recorded metrics. It does not certify their values.
        components: dict[str, float | None] = {
            "capability": 1.0,
            "data_availability": len(required & bound) / len(required) if required else 1.0,
            "scale_fitness": 1.0,
            "validation_evidence": 1.0 if model.validation_metrics else 0.0,
            "runtime_cost": 1 / (1 + runtimes[model.id]) if model.id in runtimes else None,
            "user_preference": preferences.get(model.id),
        }
        score = (
            sum(
                configured[key] * (value if value is not None else 0)
                for key, value in components.items()
            )
            / total_weight
        )
        ranked.append(ModelMatch(model.id, model.version, score, components, (), fragment))
    ranked.sort(key=lambda item: (-(item.score or 0), item.model_id, item.model_version))
    rejected.sort(key=lambda item: (item.model_id, item.model_version))
    return MatchResult(tuple(ranked), tuple(rejected))
