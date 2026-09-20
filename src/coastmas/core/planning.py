"""Bounded, deterministic templates; all candidates use the shared hard preflight.

The caller supplies authorized immutable catalog snapshots and a trusted runtime
registry. Ambiguity is reported rather than resolved by silently dropping data,
conditions or requested outputs. This module performs no external requests.
"""

import hashlib
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Annotated, Literal, Self

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
    WorkflowEdge,
    WorkflowNode,
    WorkflowSpec,
)
from coastmas.core.errors import CoastMASError
from coastmas.core.execution import ExecutionRegistry
from coastmas.core.validation import validate_asset_binding, validate_workflow

if TYPE_CHECKING:
    from coastmas.core.llm import ProviderProposal


class ManagementGoal(Contract):
    original_text: Annotated[str, Field(min_length=1, max_length=8000)]
    template: Literal["coastal_impact", "sustainability", "temporal_change"]
    sea_level_increment_m: Annotated[float, Field(ge=0, le=10)] | None = None
    weight_method: Literal["equal", "manual", "entropy"] = "manual"
    assessment_method: Literal["composite", "topsis"] = "composite"

    @model_validator(mode="after")
    def applicable_parameters(self) -> Self:
        if (self.template == "coastal_impact") != (self.sea_level_increment_m is not None):
            raise ValueError("sea-level increment is required only for the coastal template")
        if self.template == "temporal_change" and self.assessment_method == "topsis":
            raise ValueError("multi-period TOPSIS requires an explicit shared ideal-point method")
        if self.template == "coastal_impact" and (
            self.weight_method != "manual" or self.assessment_method != "composite"
        ):
            raise ValueError("assessment parameters do not apply to the coastal template")
        return self


class MissingCondition(Contract):
    code: str
    message: str
    node_id: str | None = None
    variable: str | None = None


class RequiredData(Contract):
    target: BindingTarget
    standard_name: str
    selected: VersionReference | None


class TaskGraph(Contract):
    nodes: tuple[WorkflowNode, ...]
    edges: tuple[WorkflowEdge, ...]


class PlanningArtifact(Contract):
    management_goal: ManagementGoal
    scene: VersionReference
    task_graph: TaskGraph
    required_data: tuple[RequiredData, ...]
    required_capabilities: tuple[str, ...]
    candidate_workflow: WorkflowSpec | None
    missing_conditions: tuple[MissingCondition, ...]
    rationale: tuple[str, ...]
    provider_requests: Literal[0] = 0


def parse_template_goal(text: str) -> ManagementGoal:
    """Recognize the ENTIRE documented template, including all explicit parameters.

    Normalizing whitespace and sentence punctuation is safe for these closed
    templates. Place names, extra clauses and alternative methods need structured
    selection or an authorized provider; they are not discarded by keyword search.
    """
    if not text or len(text) > 8000:
        raise CoastMASError("GOAL_INVALID", "goal exceeds the supported template input bound")
    normalized = re.sub(r"[\s，,。；;]", "", text).replace(":", "：")
    number = r"(?P<increment>(?:0|[1-9][0-9]*)(?:\.[0-9]+)?)"
    patterns = (
        rf"海岸影响筛查：海平面上升{number}米",
        rf"分析(?:某|选定)海岸段在{number}米海平面上升情景下"
        r"土地利用和人口受到的影响并按照管理单元统计风险",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, normalized)
        if match:
            return ManagementGoal(
                original_text=text,
                template="coastal_impact",
                sea_level_increment_m=float(match["increment"]),
            )
    match = re.fullmatch(
        r"(可持续性评价|多期变化评价)：(等权|人工权重|熵权)(综合评价|TOPSIS)", normalized
    )
    if match:
        methods: dict[str, Literal["equal", "manual", "entropy"]] = {
            "等权": "equal",
            "人工权重": "manual",
            "熵权": "entropy",
        }
        return ManagementGoal(
            original_text=text,
            template="sustainability" if match[1] == "可持续性评价" else "temporal_change",
            weight_method=methods[match[2]],
            assessment_method="composite" if match[3] == "综合评价" else "topsis",
        )
    raise CoastMASError(
        "GOAL_UNRESOLVED",
        "goal is outside the complete deterministic template grammar",
        {"original_text": text},
    )


def _topology(goal: ManagementGoal) -> tuple[tuple[str, ...], tuple[WorkflowEdge, ...]]:
    components: tuple[str, ...]
    if goal.template == "coastal_impact":
        components = ("screening", "overlay", "statistics")
        links = [
            ("screening", "inundation", "overlay", "inundation"),
            ("overlay", "impacts", "statistics", "impacts"),
        ]
    else:
        assessment = goal.assessment_method
        components = ("normalize", "weight", assessment)
        links = [
            ("normalize", "frame", "weight", "frame"),
            ("normalize", "frame", assessment, "frame"),
            ("weight", "weights", assessment, "weights"),
        ]
        if goal.template == "temporal_change":
            components += ("change",)
            links.append((assessment, "scores", "change", "scores"))
    return components, tuple(
        WorkflowEdge(source_node=a, source_variable=b, target_node=c, target_variable=d)
        for a, b, c, d in links
    )


def build_template_plan(
    goal: ManagementGoal,
    scene: SceneSpec,
    models: tuple[ModelSpec, ...],
    assets: tuple[DataAssetSpec, ...],
    registry: ExecutionRegistry,
    *,
    selected_data: Mapping[str, VersionReference | dict[str, str | int]] | None = None,
) -> PlanningArtifact:
    components, edges = _topology(goal)
    missing: list[MissingCondition] = []
    chosen: dict[str, ModelSpec] = {}
    nodes: list[WorkflowNode] = []
    selectors = {
        key: VersionReference.model_validate(value) for key, value in (selected_data or {}).items()
    }
    if len({(item.id, item.version) for item in assets}) != len(assets):
        raise CoastMASError("CATALOG_INVALID", "duplicate data version in planning snapshot")
    if len({(item.id, item.version) for item in models}) != len(models):
        raise CoastMASError("CATALOG_INVALID", "duplicate model version in planning snapshot")
    for component in components:
        candidates = [item for item in models if item.runtime_config.get("component") == component]
        trusted = []
        for model in candidates:
            if not model.enabled:
                continue
            try:
                registry.resolve(model)
            except CoastMASError:
                continue
            trusted.append(model)
        if len(trusted) != 1:
            missing.append(
                MissingCondition(
                    code="MODEL_MISSING" if not trusted else "MODEL_AMBIGUOUS",
                    message="select exactly one enabled trusted component version",
                    node_id=component,
                )
            )
            continue
        chosen[component] = trusted[0]
        parameters: dict[str, float] = {}
        if component == "screening" and goal.sea_level_increment_m is not None:
            parameters["increment"] = goal.sea_level_increment_m
        if component == "weight":
            parameters["method"] = {"equal": 0, "manual": 1, "entropy": 2}[goal.weight_method]
        nodes.append(
            WorkflowNode(
                id=component,
                model_id=trusted[0].id,
                model_version=trusted[0].version,
                parameters=parameters,
            )
        )
    incoming = {(edge.target_node, edge.target_variable) for edge in edges}
    bindings: list[BindingPlan] = []
    required: list[RequiredData] = []
    consumed: set[str] = set()
    for component, model in chosen.items():
        for variable in model.inputs:
            if (component, variable.name) in incoming:
                continue
            target = BindingTarget(node_id=component, variable=variable.name)
            key = f"{component}.{variable.name}"
            consumed.add(key)
            relevant = [
                item
                for item in assets
                if any(value.standard_name == variable.standard_name for value in item.variables)
            ]
            if key in selectors:
                reference = selectors[key]
                relevant = [
                    item
                    for item in relevant
                    if (item.id, item.version) == (reference.id, reference.version)
                ]
            valid: list[BindingPlan] = []
            failures: list[MissingCondition] = []
            for data in relevant:
                binding = BindingPlan(
                    source=VersionReference(id=data.id, version=data.version),
                    target=target,
                    semantic_mapping="exact_standard_name",
                    unit_conversion=None,
                    crs_transform=None,
                    resampling=None,
                    temporal_transform=None,
                    quality_check=(),
                    status="MANUAL_REVIEW",
                )
                report = validate_asset_binding(data, variable, model, scene, binding)
                if report.valid:
                    valid.extend(report.bindings)
                else:
                    failures.extend(
                        MissingCondition(
                            code=item.code,
                            message=item.message,
                            node_id=component,
                            variable=variable.name,
                        )
                        for item in report.issues
                    )
            selected = valid[0] if len(valid) == 1 else None
            required.append(
                RequiredData(
                    target=target,
                    standard_name=variable.standard_name,
                    selected=selected.source if selected else None,
                )
            )
            if selected:
                bindings.append(selected)
            elif variable.required:
                missing.extend(failures)
                missing.append(
                    MissingCondition(
                        code="DATA_AMBIGUOUS" if len(valid) > 1 else "DATA_MISSING",
                        message="select exactly one scientifically compatible data version",
                        node_id=component,
                        variable=variable.name,
                    )
                )
    for key in selectors.keys() - consumed:
        missing.append(
            MissingCondition(code="SELECTION_UNKNOWN", message=f"unknown input selection: {key}")
        )
    # All intermediate outputs remain addressable, while requested names must resolve
    # unambiguously to a real output. No invented scene output is silently dropped.
    outputs: list[BindingTarget] = []
    for name in scene.required_outputs:
        matches = [
            BindingTarget(node_id=component, variable=output.name)
            for component, model in chosen.items()
            for output in model.outputs
            if name in (output.name, output.standard_name, f"{component}.{output.name}")
        ]
        if len(matches) != 1:
            missing.append(
                MissingCondition(
                    code="OUTPUT_UNSUPPORTED", message=f"output is absent or ambiguous: {name}"
                )
            )
        elif matches[0] not in outputs:
            outputs.append(matches[0])
    # Templates guarantee their principal products even if the scene requests none.
    principal: list[tuple[str, str]] = (
        [("statistics", "statistics"), ("screening", "polygons"), ("screening", "inundation")]
        if goal.template == "coastal_impact"
        else [(goal.assessment_method, "scores")]
    )
    if goal.template == "temporal_change":
        principal.append(("change", "change"))
    for node, output_name in principal:
        target = BindingTarget(node_id=node, variable=output_name)
        if node in chosen and target not in outputs:
            outputs.append(target)
    graph = TaskGraph(
        nodes=tuple(nodes),
        edges=tuple(
            edge for edge in edges if edge.source_node in chosen and edge.target_node in chosen
        ),
    )
    workflow = None
    if len(chosen) == len(components):
        draft = WorkflowSpec(
            id="plan:"
            + hashlib.sha256(
                (
                    scene.model_dump_json()
                    + goal.model_dump_json()
                    + graph.model_dump_json()
                    + "".join(item.model_dump_json() for item in bindings)
                ).encode()
            ).hexdigest(),
            name=goal.template,
            version=1,
            scene_type=goal.template,
            nodes=graph.nodes,
            edges=graph.edges,
            input_bindings=tuple(bindings),
            parameter_bindings=(),
            constraints=(),
            validation_rules=(),
            execution_policy=ExecutionPolicy(timeout_seconds=300, max_retries=0),
            output_definition=tuple(outputs),
        )
        report = validate_workflow(draft, list(chosen.values()), list(assets), scene)
        missing.extend(
            MissingCondition(
                code=item.code, message=item.message, node_id=item.node_id, variable=item.variable
            )
            for item in report.issues
        )
        if not missing:
            workflow = draft.model_copy(update={"input_bindings": report.bindings})
    return PlanningArtifact(
        management_goal=goal,
        scene=VersionReference(id=scene.id, version=scene.version),
        task_graph=graph,
        required_data=tuple(required),
        required_capabilities=components,
        candidate_workflow=workflow,
        missing_conditions=tuple(missing),
        rationale=(
            "Exact declared template; no provider request.",
            "Every executable candidate passed shared scientific preflight.",
            "Template applicability is limited; no claim of global optimality.",
        ),
    )


def validate_provider_proposal(
    proposal: "ProviderProposal",
    scene: SceneSpec,
    models: tuple[ModelSpec, ...],
    assets: tuple[DataAssetSpec, ...],
    registry: ExecutionRegistry,
) -> WorkflowSpec:
    """Materialize typed suggestions only after catalog and scientific validation.

    No text instructions, runtime code, fabricated quality flags or provider-made
    binding validation status are accepted. Natural-language interpretation is
    retained for review; this check does not prove semantic completeness of prose.
    """
    candidate = proposal.candidate_workflow
    if proposal.missing_conditions or candidate is None:
        raise CoastMASError("PLAN_INCOMPLETE", "provider reports missing planning conditions")
    catalog = {(model.id, model.version): model for model in models}
    if len(catalog) != len(models) or len({(a.id, a.version) for a in assets}) != len(assets):
        raise CoastMASError("CATALOG_INVALID", "duplicate version in planning catalog")
    nodes = []
    selected: list[ModelSpec] = []
    for node in candidate.nodes:
        model = catalog.get((node.model.id, node.model.version))
        if model is None:
            raise CoastMASError("MODEL_UNKNOWN", "provider selected an unregistered model version")
        registry.resolve(model)
        if model not in selected:
            selected.append(model)
        parameters = {parameter.name: parameter.value for parameter in node.parameters}
        if len(parameters) != len(node.parameters):
            raise CoastMASError("PARAMETER_DUPLICATE", "provider supplied duplicate parameters")
        nodes.append(
            WorkflowNode(
                id=node.id, model_id=model.id, model_version=model.version, parameters=parameters
            )
        )
    capabilities = {name for model in selected for name in model.capabilities}
    if not set(proposal.required_capabilities).issubset(capabilities):
        raise CoastMASError(
            "CAPABILITY_MISSING", "provider capability is absent from selected models"
        )
    workflow = WorkflowSpec(
        id="provider-plan:"
        + hashlib.sha256(
            (scene.model_dump_json() + proposal.model_dump_json()).encode()
        ).hexdigest(),
        name="Provider candidate requiring review",
        version=1,
        scene_type="provider_candidate",
        nodes=tuple(nodes),
        edges=candidate.edges,
        input_bindings=tuple(
            BindingPlan(
                source=binding.source,
                target=binding.target,
                semantic_mapping="exact_standard_name",
                unit_conversion=None,
                crs_transform=None,
                resampling=None,
                temporal_transform=None,
                quality_check=(),
                status="MANUAL_REVIEW",
            )
            for binding in candidate.input_bindings
        ),
        parameter_bindings=(),
        constraints=(),
        validation_rules=(),
        execution_policy=ExecutionPolicy(timeout_seconds=300, max_retries=0),
        output_definition=candidate.output_definition,
    )
    report = validate_workflow(workflow, selected, list(assets), scene)
    if not report.valid:
        raise CoastMASError(
            "PLAN_PREFLIGHT_FAILED",
            "provider candidate failed scientific preflight",
            {
                "issues": [
                    {
                        "code": item.code,
                        "message": item.message,
                        "node_id": item.node_id,
                        "variable": item.variable,
                    }
                    for item in report.issues
                ]
            },
        )
    node_models = {node.id: catalog[(node.model_id, node.model_version)] for node in workflow.nodes}
    actual_outputs: set[str] = set()
    for target in workflow.output_definition:
        output = next(
            item for item in node_models[target.node_id].outputs if item.name == target.variable
        )
        actual_outputs.update(
            (output.name, output.standard_name, f"{target.node_id}.{output.name}")
        )
    if not set(scene.required_outputs).issubset(actual_outputs):
        raise CoastMASError(
            "OUTPUT_MISSING", "provider omitted an explicitly required scene output"
        )
    return workflow.model_copy(update={"input_bindings": report.bindings})
