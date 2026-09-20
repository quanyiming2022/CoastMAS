"""Versioned public contracts. Missing scientific metadata remains explicit.

Frozen models prevent attribute changes; serialized versions are additionally
protected by database constraints when persisted. JSON extensions are copied
and hashed at the persistence boundary, never treated as mutable identity.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

import pint
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    JsonValue,
    model_validator,
)

Name = Annotated[str, Field(min_length=1, max_length=256, pattern=r".*\S.*")]
Version = Annotated[int, Field(ge=1, strict=True)]
Scalar = str | bool | int | FiniteFloat | None
UNITS = pint.UnitRegistry()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class TimeRange(Contract):
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def chronological(self) -> Self:
        if self.end < self.start:
            raise ValueError("time end precedes start")
        return self


class Extent(Contract):
    west: FiniteFloat
    south: FiniteFloat
    east: FiniteFloat
    north: FiniteFloat

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.west >= self.east or self.south >= self.north:
            raise ValueError("extent must have positive width and height")
        return self


class TargetGridSpec(Contract):
    crs: Name
    transform: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
    width: Annotated[int, Field(strict=True, gt=0, le=10000)]
    height: Annotated[int, Field(strict=True, gt=0, le=10000)]

    @model_validator(mode="after")
    def bounded_invertible(self) -> Self:
        if self.width * self.height > 4_000_000:
            raise ValueError("target grid exceeds four million cells")
        a, b, _, d, e, _ = self.transform
        if a * e - b * d == 0:
            raise ValueError("target grid transform must be invertible")
        return self


class VariableSpec(Contract):
    name: Name
    standard_name: Name
    description: str
    data_type: Literal["raster", "vector", "table", "scalar", "array", "json"]
    unit: Name
    dimension: Name
    semantic_type: Literal["continuous", "categorical", "extensive"]
    spatial_support: Name
    temporal_support: Name
    aggregation_type: Literal["intensive", "extensive", "categorical", "instantaneous"]
    nodata_policy: Literal["reject", "mask", "propagate"]
    required: bool

    @model_validator(mode="after")
    def dimensional_consistency(self) -> Self:
        try:
            actual = UNITS.get_dimensionality(self.unit)
            expected = UNITS.get_dimensionality(self.dimension)
        except (pint.UndefinedUnitError, ValueError, TypeError) as exc:
            raise ValueError("unknown unit or dimension") from exc
        if actual != expected:
            raise ValueError("unit does not match declared dimension")
        return self


class ParameterSpec(Contract):
    name: Name
    unit: Name
    minimum: FiniteFloat | None = None
    maximum: FiniteFloat | None = None
    default: FiniteFloat | None = None
    required: bool = True
    description: str = ""

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum exceeds maximum")
        if self.default is not None:
            if self.minimum is not None and self.default < self.minimum:
                raise ValueError("default below minimum")
            if self.maximum is not None and self.default > self.maximum:
                raise ValueError("default above maximum")
        return self


class ConstraintSpec(Contract):
    field: Name
    operator: Literal["eq", "ne", "ge", "le", "in", "required"]
    value: JsonValue
    description: str


class ScaleSpec(Contract):
    minimum: Annotated[float, Field(gt=0)] | None = None
    maximum: Annotated[float, Field(gt=0)] | None = None
    unit: Name

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("scale minimum exceeds maximum")
        return self


class ModelType(StrEnum):
    STATISTICAL = "STATISTICAL"
    PROCESS = "PROCESS"
    MACHINE_LEARNING = "MACHINE_LEARNING"
    RASTER = "RASTER"
    GIS = "GIS"
    HYBRID = "HYBRID"
    EXTERNAL = "EXTERNAL"


class ModelSpec(Contract):
    id: Name
    name: Name
    display_name: Name
    version: Version
    model_type: ModelType
    description: str
    capabilities: tuple[Name, ...]
    scientific_domain: tuple[Name, ...]
    inputs: tuple[VariableSpec, ...]
    outputs: tuple[VariableSpec, ...]
    parameters: tuple[ParameterSpec, ...]
    spatial_scale: ScaleSpec
    temporal_scale: ScaleSpec
    supported_geometry: tuple[Name, ...]
    supported_crs: tuple[Name, ...]
    runtime_type: Literal["python", "cli", "docker", "http", "raster_gis", "ml", "metadata"]
    runtime_config: dict[str, JsonValue]
    constraints: tuple[ConstraintSpec, ...]
    validation_status: Literal["UNVALIDATED", "VALIDATED", "REJECTED"]
    validation_metrics: dict[str, FiniteFloat]
    references: tuple[str, ...]
    owner: Name
    license: Name
    created_at: AwareDatetime
    updated_at: AwareDatetime
    enabled: bool = True
    execution_status: Literal["EXECUTABLE", "NOT_EXECUTABLE"] = "NOT_EXECUTABLE"

    @model_validator(mode="after")
    def unambiguous(self) -> Self:
        for group in (self.inputs, self.outputs, self.parameters):
            names = [item.name for item in group]
            if len(names) != len(set(names)):
                raise ValueError("duplicate model field names")
        if self.runtime_type == "metadata" and self.execution_status == "EXECUTABLE":
            raise ValueError("metadata-only model is not executable")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at precedes created_at")
        return self


class DataAssetSpec(Contract):
    id: Name
    name: Name
    type: Literal["raster", "vector", "table", "json", "service", "database"]
    uri: Name
    format: Literal[
        "GeoTIFF",
        "COG",
        "GeoJSON",
        "Shapefile",
        "GeoPackage",
        "CSV",
        "NetCDF",
        "JSON",
        "HTTP",
        "DATABASE",
    ]
    crs: str | None
    vertical_datum: str | None
    spatial_extent: Extent | None
    time_start: AwareDatetime | None
    time_end: AwareDatetime | None
    time_resolution: str | None
    variables: tuple[VariableSpec, ...]
    quality: dict[str, JsonValue]
    source: Name
    license: Name
    version: Version
    checksum: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]

    @model_validator(mode="after")
    def time_coverage(self) -> Self:
        if (self.time_start is None) != (self.time_end is None):
            raise ValueError("time coverage must supply both endpoints")
        if self.time_start is not None and self.time_end is not None:
            if self.time_end < self.time_start:
                raise ValueError("time end precedes start")
        return self


class VersionReference(Contract):
    id: Name
    version: Version


class SceneSpec(Contract):
    id: Name
    name: Name
    version: Version
    management_goal: Name
    study_area: dict[str, JsonValue]
    entity_types: tuple[Name, ...]
    time_range: TimeRange
    scenario_conditions: dict[str, JsonValue]
    constraints: tuple[ConstraintSpec, ...]
    required_outputs: tuple[Name, ...]
    data_policy: dict[str, JsonValue]
    quality_requirements: dict[str, JsonValue]
    entity_references: tuple[VersionReference, ...] = Field(default=(), max_length=500)
    data_references: tuple[VersionReference, ...] = Field(default=(), max_length=500)

    @model_validator(mode="after")
    def unique_selected_resources(self) -> Self:
        for references in (self.entity_references, self.data_references):
            if len({reference.id for reference in references}) != len(references):
                raise ValueError("each scene resource must select one exact version")
        return self


class BindingTarget(Contract):
    node_id: Name
    variable: Name


class BindingPlan(Contract):
    source: VersionReference
    target: BindingTarget
    semantic_mapping: Name
    unit_conversion: str | None
    crs_transform: str | None
    resampling: Literal["nearest", "bilinear", "cubic", "sum", "area_weighted"] | None
    temporal_transform: Literal["nearest", "mean", "sum", "min", "max", "interpolation"] | None
    quality_check: tuple[str, ...]
    status: Literal["VALIDATED", "BLOCKED", "MANUAL_REVIEW"]


class ParameterBinding(Contract):
    node_id: Name
    parameter: Name
    value: FiniteFloat


class WorkflowNode(Contract):
    id: Name
    model_id: Name
    model_version: Version
    parameters: dict[str, FiniteFloat] = Field(default_factory=dict)
    kind: Literal["data", "transform", "model", "validation", "output"] = "model"


class WorkflowEdge(Contract):
    source_node: Name
    source_variable: Name
    target_node: Name
    target_variable: Name


class ExecutionPolicy(Contract):
    timeout_seconds: Annotated[int, Field(gt=0, le=86400)]
    max_retries: Annotated[int, Field(ge=0, le=5)]


class WorkflowSpec(Contract):
    id: Name
    name: Name
    version: Version
    scene_type: Name
    nodes: Annotated[tuple[WorkflowNode, ...], Field(min_length=1)]
    edges: tuple[WorkflowEdge, ...]
    input_bindings: tuple[BindingPlan, ...]
    parameter_bindings: tuple[ParameterBinding, ...]
    constraints: tuple[ConstraintSpec, ...]
    validation_rules: tuple[Name, ...]
    execution_policy: ExecutionPolicy
    output_definition: tuple[BindingTarget, ...]

    @model_validator(mode="after")
    def valid_graph(self) -> Self:
        identifiers = {node.id for node in self.nodes}
        if len(identifiers) != len(self.nodes):
            raise ValueError("duplicate node identifier")
        adjacency: dict[str, list[str]] = {identifier: [] for identifier in identifiers}
        degree = dict.fromkeys(identifiers, 0)
        targets: set[tuple[str, str]] = set()
        for edge in self.edges:
            if edge.source_node not in identifiers or edge.target_node not in identifiers:
                raise ValueError("edge references unknown node")
            target = (edge.target_node, edge.target_variable)
            if target in targets:
                raise ValueError("multiple producers for input")
            targets.add(target)
            adjacency[edge.source_node].append(edge.target_node)
            degree[edge.target_node] += 1
        for binding in self.input_bindings:
            if binding.target.node_id not in identifiers:
                raise ValueError("binding references unknown node")
            target = (binding.target.node_id, binding.target.variable)
            if target in targets:
                raise ValueError("multiple producers for input")
            targets.add(target)
        for parameter in self.parameter_bindings:
            if parameter.node_id not in identifiers:
                raise ValueError("parameter references unknown node")
        for output in self.output_definition:
            if output.node_id not in identifiers:
                raise ValueError("output references unknown node")
        ready = [identifier for identifier, count in degree.items() if count == 0]
        visited = 0
        while ready:
            current = ready.pop()
            visited += 1
            for child in adjacency[current]:
                degree[child] -= 1
                if degree[child] == 0:
                    ready.append(child)
        if visited != len(identifiers):
            raise ValueError("workflow contains cycle; explicit iterative groups required")
        return self


class ExecutionJob(Contract):
    id: Name
    workflow_id: Name
    scene_id: Name
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
    submitted_by: Name
    started_at: AwareDatetime | None
    finished_at: AwareDatetime | None
    progress: Annotated[float, Field(ge=0, le=1)]
    current_node: str | None
    error: dict[str, JsonValue] | None
    logs: tuple[str, ...]
    cancel_requested: bool = False


class RunManifest(Contract):
    scene: SceneSpec
    workflow: WorkflowSpec
    models: tuple[ModelSpec, ...]
    data_assets: tuple[DataAssetSpec, ...]
    parameters: tuple[ParameterBinding, ...]
    software_version: Name
    container_image: Name
    timestamp: AwareDatetime
    random_seed: Annotated[int, Field(ge=0)]
    bindings: tuple[BindingPlan, ...]
    environment: dict[str, str]


class EntityBinding(Contract):
    result_object_id: Name
    geographic_entity_id: Name
    geographic_entity_version: Version
    management_unit_id: Name | None

    @model_validator(mode="after")
    def distinct_identifiers(self) -> Self:
        identifiers = [self.result_object_id, self.geographic_entity_id]
        if self.management_unit_id is not None:
            identifiers.append(self.management_unit_id)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("result object, geographic entity and management unit IDs must differ")
        return self


class ResultManifest(Contract):
    id: Name
    job_id: Name
    revision: Version
    result_type: Name
    storage_uri: Name
    checksum: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    entity_binding: tuple[EntityBinding, ...]
    spatial_extent: Extent | None
    time_range: TimeRange | None
    unit: Name
    quality_status: Literal["RAW", "VALIDATED", "REVIEWED", "PUBLISHED", "REJECTED"]
    provenance: Name
    created_at: datetime
