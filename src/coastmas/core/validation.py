"""Hard preflight checks shared by planning and execution.

Reports are recomputed from registered versions; a caller-provided VALIDATED
binding is never evidence. Rejection cannot be offset by a ranking score.
"""

import math
from dataclasses import dataclass

import pint
from pydantic import JsonValue
from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError

from coastmas.core.binding import choose_resampling, convert_units, validate_semantics
from coastmas.core.contracts import (
    BindingPlan,
    ConstraintSpec,
    DataAssetSpec,
    ModelSpec,
    SceneSpec,
    VariableSpec,
    WorkflowSpec,
)
from coastmas.core.errors import ConstraintError


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    node_id: str | None = None
    variable: str | None = None


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]
    bindings: tuple[BindingPlan, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


def constraint_satisfied(constraint: ConstraintSpec, context: dict[str, JsonValue]) -> bool:
    value: JsonValue = context
    for part in constraint.field.split("."):
        if not isinstance(value, dict) or part not in value:
            return False
        value = value[part]
    expected = constraint.value
    if constraint.operator == "required":
        return value is not None
    if constraint.operator == "eq":
        return type(value) is type(expected) and value == expected
    if constraint.operator == "ne":
        return type(value) is not type(expected) or value != expected
    if constraint.operator == "in":
        return isinstance(expected, list) and value in expected
    if (
        isinstance(value, (float, int))
        and not isinstance(value, bool)
        and isinstance(expected, (float, int))
        and not isinstance(expected, bool)
    ):
        if constraint.operator == "ge":
            return value >= expected
        if constraint.operator == "le":
            return value <= expected
    return False


def validate_asset_binding(
    asset: DataAssetSpec,
    target: VariableSpec,
    model: ModelSpec,
    scene: SceneSpec,
    binding: BindingPlan,
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    node_id = binding.target.node_id

    def reject(code: str, message: str) -> None:
        issues.append(ValidationIssue(code, message, node_id, target.name))

    sources = [item for item in asset.variables if item.standard_name == target.standard_name]
    if len(sources) != 1:
        reject("BINDING_INCOMPATIBLE", "exactly one approved source variable is required")
        return ValidationReport(tuple(issues), ())
    source = sources[0]
    try:
        semantic = validate_semantics(source, target, {})
    except ConstraintError as exc:
        reject("BINDING_INCOMPATIBLE", exc.message)
        return ValidationReport(tuple(issues), ())
    unit_conversion = None if source.unit == target.unit else f"{source.unit} -> {target.unit}"
    crs_transform = None
    if asset.type in ("raster", "vector"):
        if not asset.crs:
            reject("CRS_MISSING", "spatial data requires CRS")
        elif not model.supported_crs:
            reject("CRS_UNDECLARED", "model must declare supported CRS")
        else:
            try:
                original = CRS(asset.crs)
                matches = [code for code in model.supported_crs if original == CRS(code)]
                destination = matches[0] if matches else model.supported_crs[0]
                if not matches:
                    Transformer.from_crs(
                        original,
                        CRS(destination),
                        always_xy=True,
                        allow_ballpark=False,
                        only_best=True,
                    )
                    crs_transform = f"{asset.crs} -> {destination}"
            except ProjError:
                reject("CRS_INVALID", "requested coordinate transformation is unavailable")
        geometry = asset.quality.get("geometry")
        if geometry not in model.supported_geometry:
            reject("GEOMETRY", "data geometry is absent or unsupported")
        scale_field = "spatial_resolution_m" if asset.type == "raster" else "spatial_support_m"
        resolution = asset.quality.get(scale_field)
        if not isinstance(resolution, (int, float)) or isinstance(resolution, bool):
            reject("SPATIAL_SCALE", "declared spatial resolution/support is required")
        else:
            try:
                scale = float(convert_units([resolution], "m", model.spatial_scale.unit)[0])
                if not math.isfinite(scale) or scale <= 0:
                    reject("SPATIAL_SCALE", "spatial resolution must be finite and positive")
                elif (
                    model.spatial_scale.minimum is not None and scale < model.spatial_scale.minimum
                ) or (
                    model.spatial_scale.maximum is not None and scale > model.spatial_scale.maximum
                ):
                    reject("SPATIAL_SCALE", "resolution outside model applicability")
            except ConstraintError as exc:
                reject("SPATIAL_SCALE", exc.message)
    if target.standard_name in ("elevation", "sea_level", "water_level"):
        datum = scene.scenario_conditions.get("vertical_datum")
        if not datum or not asset.vertical_datum or datum != asset.vertical_datum:
            reject("VERTICAL_DATUM", "missing or incompatible vertical datum")
    if asset.time_start is None or asset.time_end is None:
        reject("TIME_MISSING", "data requires explicit temporal coverage")
    elif asset.time_start > scene.time_range.start or asset.time_end < scene.time_range.end:
        reject("TIME_COVERAGE", "data does not cover requested scene period")
    if not asset.time_resolution:
        reject("TEMPORAL_SCALE", "data temporal resolution is missing")
    else:
        try:
            # A quantity string is accepted by Pint, but never evaluated as Python.
            from coastmas.core.contracts import UNITS

            interval = float(
                UNITS.Quantity(asset.time_resolution).to(model.temporal_scale.unit).magnitude
            )
            if not math.isfinite(interval) or interval <= 0:
                reject("TEMPORAL_SCALE", "invalid temporal resolution")
            elif (
                model.temporal_scale.minimum is not None and interval < model.temporal_scale.minimum
            ) or (
                model.temporal_scale.maximum is not None and interval > model.temporal_scale.maximum
            ):
                reject("TEMPORAL_SCALE", "temporal scale outside model applicability")
        except (ValueError, TypeError, pint.PintError) as exc:
            reject("TEMPORAL_SCALE", str(exc))
    if asset.quality.get("validated") is not True:
        reject("DATA_QUALITY", "data quality has not been validated")
    try:
        resampling = choose_resampling(source.semantic_type, binding.resampling)
    except ConstraintError as exc:
        reject("RESAMPLING", exc.message)
        resampling = None
    if issues:
        return ValidationReport(tuple(issues), ())
    verified = BindingPlan(
        source=binding.source,
        target=binding.target,
        semantic_mapping=semantic,
        unit_conversion=unit_conversion,
        crs_transform=crs_transform,
        resampling=resampling,
        temporal_transform=binding.temporal_transform,
        quality_check=("semantics", "unit", "CRS", "vertical_datum", "scale", "time", "quality"),
        status="VALIDATED",
    )
    return ValidationReport((), (verified,))


def validate_workflow(
    workflow: WorkflowSpec, models: list[ModelSpec], assets: list[DataAssetSpec], scene: SceneSpec
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    bindings: list[BindingPlan] = []
    registry = {(model.id, model.version): model for model in models}
    data = {(asset.id, asset.version): asset for asset in assets}
    nodes = {node.id: node for node in workflow.nodes}
    supplied = {
        (item.target.node_id, item.target.variable): item for item in workflow.input_bindings
    }
    incoming = {(edge.target_node, edge.target_variable): edge for edge in workflow.edges}
    for node in workflow.nodes:
        model = registry.get((node.model_id, node.model_version))
        if model is None:
            issues.append(
                ValidationIssue("MODEL_MISSING", "registered model version not found", node.id)
            )
            continue
        if not model.enabled:
            issues.append(ValidationIssue("MODEL_DISABLED", "model disabled", node.id))
        if model.execution_status != "EXECUTABLE":
            issues.append(
                ValidationIssue("MODEL_NOT_EXECUTABLE", "model is metadata-only", node.id)
            )
        if model.validation_status != "VALIDATED":
            issues.append(ValidationIssue("MODEL_UNVALIDATED", "model lacks validation", node.id))
        parameters = {item.name: item for item in model.parameters}
        values = dict(node.parameters)
        for parameter_binding in workflow.parameter_bindings:
            if parameter_binding.node_id == node.id:
                if parameter_binding.parameter in values:
                    issues.append(
                        ValidationIssue(
                            "PARAMETER_DUPLICATE", "two parameter_binding sources", node.id
                        )
                    )
                values[parameter_binding.parameter] = parameter_binding.value
        for name in values:
            if name not in parameters:
                issues.append(
                    ValidationIssue("PARAMETER_UNKNOWN", "parameter not registered", node.id, name)
                )
        for name, parameter in parameters.items():
            value = values.get(name, parameter.default)
            if value is None:
                if parameter.required:
                    issues.append(
                        ValidationIssue(
                            "PARAMETER_MISSING", "required parameter missing", node.id, name
                        )
                    )
            elif (parameter.minimum is not None and value < parameter.minimum) or (
                parameter.maximum is not None and value > parameter.maximum
            ):
                issues.append(
                    ValidationIssue("PARAMETER_RANGE", "parameter outside range", node.id, name)
                )
        parameter_context: dict[str, JsonValue] = {
            name: values.get(name, parameter.default) for name, parameter in parameters.items()
        }
        context: dict[str, JsonValue] = {
            "parameters": parameter_context,
            "scene": scene.model_dump(mode="json"),
            "model": model.model_dump(mode="json"),
        }
        for constraint in model.constraints:
            if not constraint_satisfied(constraint, context):
                issues.append(
                    ValidationIssue("DECLARED_CONSTRAINT", constraint.description, node.id)
                )
        for variable in model.inputs:
            key = (node.id, variable.name)
            binding = supplied.get(key)
            edge = incoming.get(key)
            if binding is not None:
                asset = data.get((binding.source.id, binding.source.version))
                if asset is None:
                    issues.append(
                        ValidationIssue(
                            "DATA_MISSING", "data version missing", node.id, variable.name
                        )
                    )
                else:
                    report = validate_asset_binding(asset, variable, model, scene, binding)
                    issues.extend(report.issues)
                    bindings.extend(report.bindings)
            elif edge is not None:
                producer = nodes[edge.source_node]
                upstream = registry.get((producer.model_id, producer.model_version))
                output = (
                    next(
                        (item for item in upstream.outputs if item.name == edge.source_variable),
                        None,
                    )
                    if upstream
                    else None
                )
                if output is None:
                    issues.append(
                        ValidationIssue(
                            "OUTPUT_MISSING",
                            "producer output not registered",
                            node.id,
                            variable.name,
                        )
                    )
                else:
                    try:
                        validate_semantics(output, variable, {})
                    except ConstraintError as exc:
                        issues.append(
                            ValidationIssue(
                                "EDGE_INCOMPATIBLE", exc.message, node.id, variable.name
                            )
                        )
            elif variable.required:
                issues.append(
                    ValidationIssue(
                        "INPUT_MISSING", "required input has no producer", node.id, variable.name
                    )
                )
        declared_inputs = {variable.name for variable in model.inputs}
        for target_node, target_variable in supplied.keys() | incoming.keys():
            if target_node == node.id and target_variable not in declared_inputs:
                issues.append(
                    ValidationIssue(
                        "INPUT_UNKNOWN", "target variable not registered", node.id, target_variable
                    )
                )
    for requested_output in workflow.output_definition:
        node = nodes[requested_output.node_id]
        model = registry.get((node.model_id, node.model_version))
        if model is not None and requested_output.variable not in {
            item.name for item in model.outputs
        }:
            issues.append(
                ValidationIssue(
                    "OUTPUT_MISSING",
                    "requested output not registered",
                    node.id,
                    requested_output.variable,
                )
            )
    scene_context: dict[str, JsonValue] = {"scene": scene.model_dump(mode="json")}
    for constraint in workflow.constraints + scene.constraints:
        if not constraint_satisfied(constraint, scene_context):
            issues.append(ValidationIssue("DECLARED_CONSTRAINT", constraint.description))
    known_rules = {
        "semantics",
        "units",
        "crs",
        "vertical_datum",
        "time",
        "scale",
        "parameters",
        "dag",
    }
    for rule in workflow.validation_rules:
        if rule not in known_rules:
            issues.append(
                ValidationIssue("VALIDATION_RULE_UNKNOWN", "validation rule not implemented")
            )
    return ValidationReport(tuple(issues), tuple(bindings))
