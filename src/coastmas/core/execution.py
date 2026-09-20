"""Deterministic DAG execution using immutable, maintainer-registered runtimes.

Runtime metadata never imports code or selects an executable. Every model is
matched to a trusted registry snapshot before any data access or execution.
DataResolver implementations must validate source checksums and apply the
recomputed binding; they are trusted application infrastructure, not plugins
specified by user text. No LLM is involved in rerunning a saved workflow.
"""

import hashlib
import json
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import JsonValue

from coastmas.adapters.runtime import ModelAdapter, RunRequest
from coastmas.core.binding import convert_units
from coastmas.core.contracts import (
    BindingPlan,
    DataAssetSpec,
    ModelSpec,
    RunManifest,
    SceneSpec,
    VariableSpec,
)
from coastmas.core.errors import CoastMASError, ConstraintError
from coastmas.core.validation import validate_workflow


class DataResolver(Protocol):
    def resolve(
        self, asset: DataAssetSpec, target: VariableSpec, binding: BindingPlan, scene: SceneSpec
    ) -> JsonValue: ...


def model_identity(model: ModelSpec) -> str:
    canonical = json.dumps(
        model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class RegisteredRuntime:
    spec_checksum: str
    adapter: ModelAdapter
    handler: str


class ExecutionRegistry:
    def __init__(self) -> None:
        self._runtimes: dict[tuple[str, int], RegisteredRuntime] = {}

    def register(self, model: ModelSpec, adapter: ModelAdapter, handler: str) -> None:
        key = model.id, model.version
        if key in self._runtimes:
            raise CoastMASError("IMMUTABLE_CONFLICT", "model runtime version already registered")
        self._runtimes[key] = RegisteredRuntime(model_identity(model), adapter, handler)

    def resolve(self, model: ModelSpec) -> RegisteredRuntime:
        runtime = self._runtimes.get((model.id, model.version))
        if runtime is None or runtime.spec_checksum != model_identity(model):
            raise CoastMASError("MODEL_ERROR", "model snapshot differs from registered runtime")
        return runtime


@dataclass(frozen=True)
class WorkflowExecution:
    outputs: dict[str, JsonValue]
    node_outputs: dict[str, dict[str, JsonValue]]
    executed_nodes: tuple[str, ...]
    bindings: tuple[BindingPlan, ...]
    elapsed_seconds: float


def transform_numeric(
    value: JsonValue, source: str, target: str, *, allow_nodata: bool
) -> JsonValue:
    if value is None and allow_nodata:
        return None
    if isinstance(value, list):
        return [
            transform_numeric(item, source, target, allow_nodata=allow_nodata) for item in value
        ]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ConstraintError("numeric binding contains invalid data or forbidden NoData")
    return float(convert_units([value], source, target)[0])


def validate_value(value: JsonValue, variable: VariableSpec) -> None:
    json.dumps(value, allow_nan=False)
    if variable.data_type in {"scalar", "array", "raster"}:
        if variable.data_type == "scalar" and isinstance(value, list):
            raise ConstraintError("scalar output contains an array")
        if variable.data_type in {"array", "raster"} and not isinstance(value, list):
            raise ConstraintError("array output must contain a JSON array")
        if variable.data_type == "raster":
            if (
                not isinstance(value, list)
                or not value
                or not all(isinstance(row, list) and row for row in value)
                or len({len(row) for row in value if isinstance(row, list)}) != 1
            ):
                raise ConstraintError("raster output must be a rectangular nonempty matrix")
        transform_numeric(
            value, variable.unit, variable.unit, allow_nodata=variable.nodata_policy != "reject"
        )


def execute_workflow(
    manifest: RunManifest,
    *,
    registry: ExecutionRegistry,
    resolver: DataResolver,
    work_root: Path,
    cancel: threading.Event | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> WorkflowExecution:
    cancellation = cancel if cancel is not None else threading.Event()
    if cancellation.is_set():
        raise CoastMASError("CANCELLED", "workflow cancelled before execution")
    workflow = manifest.workflow
    report = validate_workflow(
        workflow, list(manifest.models), list(manifest.data_assets), manifest.scene
    )
    if not report.valid:
        raise ConstraintError(
            "workflow preflight rejected execution",
            {"issues": [issue.code for issue in report.issues]},
        )
    models = {(model.id, model.version): model for model in manifest.models}
    assets = {(asset.id, asset.version): asset for asset in manifest.data_assets}
    if len(models) != len(manifest.models) or len(assets) != len(manifest.data_assets):
        raise ConstraintError("manifest contains duplicate model or data versions")
    if (
        manifest.parameters != workflow.parameter_bindings
        or manifest.bindings != workflow.input_bindings
    ):
        raise ConstraintError("run manifest parameters or bindings differ from workflow snapshot")
    runtimes = {
        node.id: registry.resolve(models[(node.model_id, node.model_version)])
        for node in workflow.nodes
    }
    remaining = {node.id: node for node in workflow.nodes}
    outputs: dict[str, dict[str, JsonValue]] = {}
    order: list[str] = []
    started = time.monotonic()
    while remaining:
        ready = [
            node
            for node in remaining.values()
            if all(
                edge.source_node in outputs
                for edge in workflow.edges
                if edge.target_node == node.id
            )
        ]
        if not ready:
            raise ConstraintError("workflow contains an unresolved dependency")
        for node in ready:
            if cancellation.is_set():
                raise CoastMASError("CANCELLED", "workflow execution cancelled")
            model = models[(node.model_id, node.model_version)]
            inputs: dict[str, JsonValue] = {}
            variables = {variable.name: variable for variable in model.inputs}
            for binding in report.bindings:
                if binding.target.node_id == node.id:
                    target = variables[binding.target.variable]
                    value = resolver.resolve(
                        assets[(binding.source.id, binding.source.version)],
                        target,
                        binding,
                        manifest.scene,
                    )
                    validate_value(value, target)
                    inputs[target.name] = value
            for edge in workflow.edges:
                if edge.target_node != node.id:
                    continue
                source_node = next(item for item in workflow.nodes if item.id == edge.source_node)
                source_model = models[(source_node.model_id, source_node.model_version)]
                source = next(
                    item for item in source_model.outputs if item.name == edge.source_variable
                )
                target = variables[edge.target_variable]
                if source.data_type in {"raster", "vector"} and not set(
                    source_model.supported_crs
                ).intersection(model.supported_crs):
                    raise ConstraintError("edge needs an explicit spatial transformation node")
                value = outputs[edge.source_node][edge.source_variable]
                if source.unit != target.unit:
                    value = transform_numeric(
                        value,
                        source.unit,
                        target.unit,
                        allow_nodata=target.nodata_policy != "reject",
                    )
                validate_value(value, target)
                inputs[target.name] = value
            parameters: dict[str, JsonValue] = {
                item.name: item.default for item in model.parameters if item.default is not None
            }
            parameters.update(node.parameters)
            parameters.update(
                {
                    item.parameter: item.value
                    for item in workflow.parameter_bindings
                    if item.node_id == node.id
                }
            )
            remaining_seconds = workflow.execution_policy.timeout_seconds - (
                time.monotonic() - started
            )
            if remaining_seconds <= 0:
                raise CoastMASError("TIMEOUT", "workflow total execution deadline exceeded")
            runtime = runtimes[node.id]
            request = RunRequest(
                runtime.handler,
                inputs,
                parameters,
                work_root,
                remaining_seconds,
                cancellation,
                context={
                    "scene": manifest.scene.model_dump(mode="json"),
                    "node_id": node.id,
                    "random_seed": manifest.random_seed,
                    "software_version": manifest.software_version,
                },
            )
            runtime.adapter.validate(request)
            directory = runtime.adapter.prepare(request)
            try:
                raw, code, elapsed = runtime.adapter.execute(request, directory)
                result = runtime.adapter.collect(raw, code, elapsed)
            finally:
                runtime.adapter.cleanup(directory)
            declared = {variable.name: variable for variable in model.outputs}
            if set(result.outputs) - set(declared) or any(
                variable.required and variable.name not in result.outputs
                for variable in model.outputs
            ):
                raise CoastMASError(
                    "MODEL_OUTPUT_ERROR", "model output differs from declared variables"
                )
            for name, value in result.outputs.items():
                validate_value(value, declared[name])
            outputs[node.id] = result.outputs
            order.append(node.id)
            del remaining[node.id]
            if on_progress is not None:
                on_progress(len(order) / len(workflow.nodes))
    selected: dict[str, JsonValue] = {}
    for requested in workflow.output_definition:
        if requested.variable not in outputs[requested.node_id]:
            raise CoastMASError("MODEL_OUTPUT_ERROR", "requested workflow output missing")
        selected[f"{requested.node_id}.{requested.variable}"] = outputs[requested.node_id][
            requested.variable
        ]
    if cancellation.is_set():
        raise CoastMASError("CANCELLED", "workflow cancelled before collecting results")
    return WorkflowExecution(
        selected, outputs, tuple(order), report.bindings, time.monotonic() - started
    )
