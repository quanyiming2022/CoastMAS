"""Persisted planning sessions shared by parse, recommend and workflow building."""

from importlib.metadata import version
from typing import Annotated, cast

from fastapi import APIRouter, Header, Request
from pydantic import Field, JsonValue
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from coastmas.app.dependencies import CurrentUser, DatabaseSession
from coastmas.app.run_routes import resource_in_project
from coastmas.core.contracts import (
    Contract,
    DataAssetSpec,
    ModelSpec,
    Name,
    SceneSpec,
    VersionReference,
    WorkflowSpec,
)
from coastmas.core.errors import CoastMASError
from coastmas.core.execution import ExecutionRegistry
from coastmas.core.llm import LLMProvider, PlanningPrompt, ProviderPlanningArtifact
from coastmas.core.model_documents import reject_embedded_credentials
from coastmas.core.planning import (
    ManagementGoal,
    build_template_plan,
    parse_template_goal,
    validate_provider_proposal,
)
from coastmas.core.validation import validate_workflow
from coastmas.persistence.planning import create_trace, read_trace, save_artifact
from coastmas.persistence.resources import (
    create_resource,
    fingerprint,
    read_resource,
    require_permission,
)
from coastmas.persistence.schema import PlanningTrace, ProviderRequest, Resource

router = APIRouter(prefix="/api/v1/plans", tags=["planning"])
IdempotencyKey = Annotated[str, Header(min_length=1, max_length=256)]


class PlanRequest(Contract):
    project_id: Name
    scene: VersionReference
    goal: Annotated[str, Field(min_length=1, max_length=8000)] | ManagementGoal
    selected_data: dict[str, VersionReference] = Field(default_factory=dict)
    allow_external: bool = False


def _snapshots(
    session: Session,
    user: str,
    body: PlanRequest,
    references: list[tuple[str, int, str]] | None = None,
) -> tuple[SceneSpec, tuple[ModelSpec, ...], tuple[DataAssetSpec, ...]]:
    require_permission(session, user, body.project_id, "read")
    resource_in_project(session, user, body.scene.id, "scene", body.project_id)
    scene = SceneSpec.model_validate(
        read_resource(
            session,
            user_id=user,
            identifier=body.scene.id,
            version=body.scene.version,
        ).spec
    )
    if references is None:
        rows = list(
            session.scalars(
                select(Resource)
                .where(
                    Resource.project_id == body.project_id,
                    Resource.kind.in_(("model", "data")),
                    Resource.archived.is_(False),
                    Resource.enabled.is_(True),
                )
                .order_by(Resource.id)
                .limit(501)
            )
        )
        if len(rows) > 500:
            raise CoastMASError("CATALOG_LIMIT", "planning needs a narrower authorized catalog")
        references = [(item.id, item.current_version, item.kind) for item in rows]
    models, assets = [], []
    for identifier, revision, kind in sorted(references):
        resource_in_project(session, user, identifier, kind, body.project_id)
        spec = read_resource(session, user_id=user, identifier=identifier, version=revision).spec
        if kind == "model":
            models.append(ModelSpec.model_validate(spec))
        else:
            assets.append(DataAssetSpec.model_validate(spec))
    return scene, tuple(models), tuple(assets)


def _prompts(
    goal: str,
    scene: SceneSpec,
    models: tuple[ModelSpec, ...],
    assets: tuple[DataAssetSpec, ...],
    registry: ExecutionRegistry,
) -> tuple[PlanningPrompt, PlanningPrompt]:
    trusted = []
    for model in models:
        if not model.enabled or model.validation_status != "VALIDATED":
            continue
        try:
            registry.resolve(model)
        except CoastMASError:
            continue
        trusted.append(model)
    # Backward semantic adjacency prioritizes requested outputs and their producers.
    # The full available count remains visible; truncated retrieval is never "best".
    needed = set(scene.required_outputs)
    scores: dict[str, int] = {}
    for depth in range(4):
        additional: set[str] = set()
        for model in trusted:
            if model.id in scores:
                continue
            if any(
                output.name in needed or output.standard_name in needed for output in model.outputs
            ):
                scores[model.id] = 100 - 10 * depth
                additional.update(variable.standard_name for variable in model.inputs)
        needed.update(additional)
    trusted.sort(key=lambda item: (-scores.get(item.id, 0), item.id, item.version))
    summaries: list[dict[str, JsonValue]] = []
    for model in trusted:
        summaries.append(
            {
                "id": model.id,
                "version": model.version,
                "capabilities": list(model.capabilities),
                "inputs": [item.model_dump(mode="json") for item in model.inputs],
                "outputs": [item.model_dump(mode="json") for item in model.outputs],
                "parameters": [item.model_dump(mode="json") for item in model.parameters],
                "constraints": [item.model_dump(mode="json") for item in model.constraints],
                "supported_crs": list(model.supported_crs),
                "spatial_scale": model.spatial_scale.model_dump(mode="json"),
                "temporal_scale": model.temporal_scale.model_dump(mode="json"),
                "evidence": list(model.references),
            }
        )
    summary: dict[str, JsonValue] = {
        "id": scene.id,
        "version": scene.version,
        "time_range": scene.time_range.model_dump(mode="json"),
        "entity_types": list(scene.entity_types),
        "required_outputs": list(scene.required_outputs),
        "scenario_conditions": scene.scenario_conditions,
        "constraints": [item.model_dump(mode="json") for item in scene.constraints],
        "quality_requirements": scene.quality_requirements,
        "study_area_type": scene.study_area.get("type"),
        "data_policy": {
            key: value
            for key, value in scene.data_policy.items()
            if key in ("target_grid", "study_area_crs")
        },
    }
    reject_embedded_credentials(summary)
    prompts = []
    for count in (6, 12):
        selected = trusted[:count]
        input_names = {item.standard_name for model in selected for item in model.inputs}
        relevant = [
            asset
            for asset in assets
            if any(variable.standard_name in input_names for variable in asset.variables)
        ]
        if len(relevant) > 64:
            raise CoastMASError("CATALOG_LIMIT", "select fewer relevant data versions for planning")
        data: list[dict[str, JsonValue]] = [
            {
                "id": asset.id,
                "version": asset.version,
                "checksum": asset.checksum,
                "type": asset.type,
                "format": asset.format,
                "crs": asset.crs,
                "vertical_datum": asset.vertical_datum,
                "time_start": asset.time_start.isoformat() if asset.time_start else None,
                "time_end": asset.time_end.isoformat() if asset.time_end else None,
                "time_resolution": asset.time_resolution,
                "variables": [item.model_dump(mode="json") for item in asset.variables],
                "quality": {
                    key: value
                    for key, value in asset.quality.items()
                    if key
                    in (
                        "validated",
                        "geometry",
                        "spatial_resolution_m",
                        "spatial_support_m",
                    )
                },
            }
            for asset in relevant
        ]
        prompts.append(
            PlanningPrompt(
                goal=goal,
                scene_summary=summary,
                models=tuple(summaries[:count]),
                data=tuple(data),
                candidate_total=len(trusted),
            )
        )
    return prompts[0], prompts[1]


def _reload(
    session: Session, user: str, trace: PlanningTrace
) -> tuple[
    PlanRequest,
    SceneSpec,
    tuple[ModelSpec, ...],
    tuple[DataAssetSpec, ...],
]:
    body = PlanRequest.model_validate(trace.inputs.get("request"))
    references = trace.inputs.get("references")
    if not isinstance(references, list):
        raise CoastMASError("PLAN_INVALID", "saved planning references are missing")
    values = []
    for item in references:
        if not isinstance(item, dict) or item.get("kind") not in ("model", "data"):
            raise CoastMASError("PLAN_INVALID", "saved planning reference is invalid")
        reference = VersionReference.model_validate(
            {"id": item.get("id"), "version": item.get("version")}
        )
        values.append((reference.id, reference.version, str(item["kind"])))
    scene, models, assets = _snapshots(session, user, body, values)
    return body, scene, models, assets


def _verify_artifact(
    artifact: dict[str, JsonValue],
    scene: SceneSpec,
    models: tuple[ModelSpec, ...],
    assets: tuple[DataAssetSpec, ...],
    registry: ExecutionRegistry,
) -> None:
    if artifact.get("candidate_workflow") is None:
        return
    workflow = WorkflowSpec.model_validate(artifact["candidate_workflow"])
    selected = {(node.model_id, node.model_version) for node in workflow.nodes}
    for model in models:
        if (model.id, model.version) in selected:
            registry.resolve(model)
    report = validate_workflow(workflow, list(models), list(assets), scene)
    if not report.valid:
        raise CoastMASError("PLAN_INVALIDATED", "saved candidate no longer passes preflight")


def _view(trace: PlanningTrace) -> dict[str, JsonValue]:
    body = PlanRequest.model_validate(trace.inputs.get("request"))
    return {
        "id": trace.id,
        "artifact": trace.artifact,
        "unresolved_goal": body.goal
        if isinstance(body.goal, str) and trace.artifact is None
        else None,
        "reserved_requests": trace.reserved_requests,
        "max_provider_requests": trace.max_provider_requests,
        "allow_external": trace.allow_external,
        "usage_policy": "Reservations bound requests; tokens remain null unless reported.",
    }


@router.post("", status_code=201)
def create_plan(
    body: PlanRequest,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
    idempotency_key: IdempotencyKey,
) -> dict[str, JsonValue]:
    require_permission(session, user_id, body.project_id, "write")
    scene, models, assets = _snapshots(session, user_id, body)
    registry = cast(ExecutionRegistry, request.app.state.registry)
    goal = body.goal if isinstance(body.goal, ManagementGoal) else None
    if goal is None:
        try:
            goal = parse_template_goal(cast(str, body.goal))
        except CoastMASError as exc:
            if exc.code != "GOAL_UNRESOLVED":
                raise
    inputs: dict[str, JsonValue] = {
        "request": body.model_dump(mode="json"),
        "software_version": version("coastmas"),
        "references": [
            {"id": item.id, "version": item.version, "kind": kind}
            for kind, items in (("model", models), ("data", assets))
            for item in items
        ],
        "allowed_prompt_fingerprints": [],
    }
    if goal is None and body.allow_external:
        prompts = _prompts(cast(str, body.goal), scene, models, assets, registry)
        inputs["allowed_prompt_fingerprints"] = [
            fingerprint(p.model_dump(mode="json")) for p in prompts
        ]
    trace = create_trace(
        session,
        user_id,
        body.project_id,
        key=idempotency_key,
        inputs=inputs,
        allow_external=body.allow_external,
    )
    if trace.artifact is None and goal is not None:
        plan = build_template_plan(
            goal,
            scene,
            models,
            assets,
            registry,
            selected_data=body.selected_data,
        )
        save_artifact(session, user_id, trace.id, plan.model_dump(mode="json"))
    if trace.artifact is not None:
        _verify_artifact(trace.artifact, scene, models, assets, registry)
    output = _view(trace)
    session.commit()
    return output


@router.get("/{trace_id}")
def get_plan(
    trace_id: str, request: Request, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    trace = read_trace(session, user_id, trace_id)
    _, scene, models, assets = _reload(session, user_id, trace)
    if trace.artifact is not None:
        _verify_artifact(
            trace.artifact,
            scene,
            models,
            assets,
            cast(ExecutionRegistry, request.app.state.registry),
        )
    return _view(trace)


@router.post("/{trace_id}/parse")
@router.post("/{trace_id}/recommend")
@router.post("/{trace_id}/build-workflow")
def resolve_plan(
    trace_id: str, request: Request, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    trace = read_trace(session, user_id, trace_id)
    body, scene, models, assets = _reload(session, user_id, trace)
    require_permission(session, user_id, trace.project_id, "write")
    registry = cast(ExecutionRegistry, request.app.state.registry)
    if trace.artifact is not None:
        _verify_artifact(trace.artifact, scene, models, assets, registry)
        return _view(trace)
    if not trace.allow_external:
        raise CoastMASError("EXTERNAL_NOT_AUTHORIZED", "external planning has not been authorized")
    provider = cast(LLMProvider | None, request.app.state.llm_provider)
    if provider is None:
        raise CoastMASError("PROVIDER_UNCONFIGURED", "external planning provider is not configured")
    prompts = _prompts(cast(str, body.goal), scene, models, assets, registry)
    prompt = prompts[0 if trace.reserved_requests == 0 else 1]
    # Release all resource locks before network IO. Fresh authorization and immutable
    # versions are checked again before accepting the result.
    session.commit()
    result = provider.generate(cast(Engine, request.app.state.engine), user_id, trace_id, prompt)
    trace = read_trace(session, user_id, trace_id)
    _, scene, models, assets = _reload(session, user_id, trace)
    offered = {(item["id"], item["version"]) for item in prompt.models}
    selected = tuple(model for model in models if (model.id, model.version) in offered)
    proposal = result.proposal
    artifact: dict[str, JsonValue] = {
        "origin": "provider_candidate",
        "proposal": proposal.model_dump(mode="json"),
        "candidate_workflow": None,
        "missing_conditions": list(proposal.missing_conditions),
        "request_id": result.request_id,
        "usage": result.usage,
        "interpretation_requires_review": True,
    }
    if not proposal.missing_conditions:
        workflow = validate_provider_proposal(proposal, scene, selected, assets, registry)
        artifact["candidate_workflow"] = workflow.model_dump(mode="json")
    artifact = ProviderPlanningArtifact.model_validate(artifact).model_dump(mode="json")
    save_artifact(session, user_id, trace_id, artifact)
    output = _view(trace)
    session.commit()
    return output


@router.post("/{trace_id}/workflow", status_code=201)
def save_workflow(
    trace_id: str, request: Request, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    trace = read_trace(session, user_id, trace_id)
    require_permission(session, user_id, trace.project_id, "write")
    _, scene, models, assets = _reload(session, user_id, trace)
    if trace.artifact is None or trace.artifact.get("candidate_workflow") is None:
        raise CoastMASError("PLAN_INCOMPLETE", "planning has no validated workflow candidate")
    _verify_artifact(
        trace.artifact, scene, models, assets, cast(ExecutionRegistry, request.app.state.registry)
    )
    workflow = WorkflowSpec.model_validate(trace.artifact["candidate_workflow"])
    existing = session.get(Resource, workflow.id)
    if existing is not None:
        if existing.project_id != trace.project_id or existing.kind != "workflow":
            raise CoastMASError("VERSION_CONFLICT", "workflow identity is already in use")
        revision = read_resource(session, user_id=user_id, identifier=workflow.id, version=1)
        if revision.checksum != fingerprint(workflow.model_dump(mode="json")):
            raise CoastMASError(
                "VERSION_CONFLICT", "workflow content conflicts with existing version"
            )
    else:
        create_resource(
            session,
            user_id=user_id,
            project_id=trace.project_id,
            kind="workflow",
            identifier=workflow.id,
            name=workflow.name,
            spec=workflow.model_dump(mode="json"),
        )
    session.commit()
    return {"id": workflow.id, "version": 1, "planning_trace_id": trace_id}


@router.get("/{trace_id}/requests")
def request_history(
    trace_id: str, session: DatabaseSession, user_id: CurrentUser
) -> list[dict[str, JsonValue]]:
    read_trace(session, user_id, trace_id)
    records = session.scalars(
        select(ProviderRequest)
        .where(
            ProviderRequest.trace_id == trace_id,
        )
        .order_by(ProviderRequest.ordinal)
    )
    return [
        {
            "id": item.id,
            "ordinal": item.ordinal,
            "status": item.status,
            "provider_model": item.provider_model,
            "provider_endpoint": item.provider_endpoint,
            "response_model": item.response_model,
            "http_status": item.http_status,
            "request_fingerprint": item.request_fingerprint,
            "response_fingerprint": item.response_fingerprint,
            "usage": item.usage,
            "error_code": item.error_code,
            "created_at": item.created_at.isoformat(),
            "dispatched_at": item.dispatched_at.isoformat() if item.dispatched_at else None,
            "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        }
        for item in records
    ]
