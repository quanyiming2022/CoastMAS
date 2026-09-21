"""Freeze explicit optimization inputs and execute through the normal audited worker path."""

import hashlib
import json
from typing import Annotated, cast
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Query, Request
from pydantic import Field, JsonValue
from sqlalchemy import select

from coastmas.app.data_routes import data_resource, inspect_isolated, stored_content
from coastmas.app.dependencies import CurrentUser, DatabaseSession, artifact_store
from coastmas.app.run_routes import (
    IdempotencyKey,
    RunSelection,
    candidate_manifest,
    check_execution,
    encode,
    lock_submission,
    resource_in_project,
    run_workflow,
)
from coastmas.core.contracts import (
    Contract,
    DataAssetSpec,
    ModelSpec,
    Name,
    SceneSpec,
    Version,
    VersionReference,
    WorkflowSpec,
)
from coastmas.core.errors import CoastMASError
from coastmas.core.execution import ExecutionRegistry
from coastmas.core.optimization import Number, OptimizationFrame, OptimizationSpec
from coastmas.core.validation import validate_workflow
from coastmas.persistence.jobs import snapshot
from coastmas.persistence.lifecycle import archive_resource
from coastmas.persistence.resources import (
    add_dependencies,
    create_resource,
    fingerprint,
    read_resource,
    require_permission,
)
from coastmas.persistence.schema import Job, Resource, ResultBundle

router = APIRouter(prefix="/api/v1/optimizations", tags=["optimization"])


class SaveOptimizationRequest(Contract):
    project_id: Name
    name: Name
    scene: VersionReference
    frame: OptimizationFrame
    time_limit: Annotated[Number, Field(ge=0.01, le=120)]
    idempotency_key: Name


class RunOptimizationRequest(Contract):
    optimization_version: Version
    random_seed: int = Field(default=42, ge=0, le=2**32 - 1)


def record_spec(
    identifier: str, session: DatabaseSession, user_id: str, version: int | None = None
) -> OptimizationSpec:
    resource = session.get(Resource, identifier)
    if resource is None or resource.kind != "optimization":
        raise CoastMASError("NOT_FOUND", "optimization record unavailable")
    return OptimizationSpec.model_validate(
        read_resource(session, user_id=user_id, identifier=identifier, version=version).spec
    )


@router.post("", status_code=201)
def save(
    body: SaveOptimizationRequest, request: Request, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    require_permission(session, user_id, body.project_id, "write")
    lock_submission(session, body.project_id, user_id, "optimization:" + body.idempotency_key)
    identifier = str(
        uuid5(
            NAMESPACE_URL,
            json.dumps(["coastmas:optimization", body.project_id, user_id, body.idempotency_key]),
        )
    )
    checksum = fingerprint(body.model_dump(mode="json"))
    existing = session.get(Resource, identifier)
    if existing is not None:
        record = record_spec(identifier, session, user_id, 1)
        if existing.project_id != body.project_id or record.request_checksum != checksum:
            raise CoastMASError("IDEMPOTENCY_CONFLICT", "optimization key has different inputs")
        return encode(read_resource(session, user_id=user_id, identifier=identifier, version=1))
    resource_in_project(session, user_id, body.scene.id, "scene", body.project_id)
    original = SceneSpec.model_validate(
        read_resource(
            session, user_id=user_id, identifier=body.scene.id, version=body.scene.version
        ).spec
    )
    model_id = f"builtin:{body.project_id}:spatial_optimization"
    resource_in_project(session, user_id, model_id, "model", body.project_id)
    model = ModelSpec.model_validate(
        read_resource(session, user_id=user_id, identifier=model_id, version=1).spec
    )
    cast(ExecutionRegistry, request.app.state.registry).resolve(model)
    data_id = str(uuid5(NAMESPACE_URL, identifier + ":data"))
    scene_id = str(uuid5(NAMESPACE_URL, identifier + ":scene"))
    workflow_id = str(uuid5(NAMESPACE_URL, identifier + ":workflow"))
    payload = json.dumps(
        {"candidates": body.frame.model_dump(mode="json")}, sort_keys=True, allow_nan=False
    ).encode()
    data_sha = hashlib.sha256(payload).hexdigest()
    store = artifact_store(request)
    key = f"{body.project_id}/data/{data_id}/{data_sha}"
    horizon_seconds = (original.time_range.end - original.time_range.start).total_seconds()
    data = DataAssetSpec(
        id=data_id,
        name=body.name[:225] + " / optimization inputs",
        version=1,
        type="json",
        format="JSON",
        uri=f"s3://{store.bucket}/{key}",
        checksum=data_sha,
        crs=None,
        vertical_datum=None,
        spatial_extent=None,
        time_start=original.time_range.start,
        time_end=original.time_range.end,
        time_resolution=f"{horizon_seconds} s",
        variables=model.inputs,
        quality={},
        source=body.frame.data_label,
        license="User supplied; license not specified",
    )
    inspected = inspect_isolated(payload, data)
    data = data.model_copy(update={"quality": inspected.metadata})
    derived = SceneSpec.model_validate(
        {
            **original.model_dump(mode="json"),
            "id": scene_id,
            "name": body.name[:225] + " / fixed optimization scene",
            "version": 1,
            "management_goal": "Spatial allocation: " + body.name[:225],
            "required_outputs": ["allocation"],
            "data_references": [
                *(item.model_dump(mode="json") for item in original.data_references),
                {"id": data_id, "version": 1},
            ],
        }
    )
    workflow = WorkflowSpec.model_validate(
        {
            "id": workflow_id,
            "name": body.name[:225] + " / optimization workflow",
            "version": 1,
            "scene_type": "spatial_optimization",
            "nodes": [
                {
                    "id": "optimize",
                    "model_id": model_id,
                    "model_version": 1,
                    "parameters": {"time_limit": body.time_limit},
                }
            ],
            "edges": [],
            "input_bindings": [
                {
                    "source": {"id": data_id, "version": 1},
                    "target": {"node_id": "optimize", "variable": "candidates"},
                    "semantic_mapping": "exact_standard_name",
                    "unit_conversion": None,
                    "crs_transform": None,
                    "resampling": None,
                    "temporal_transform": None,
                    "quality_check": [],
                    "status": "MANUAL_REVIEW",
                }
            ],
            "parameter_bindings": [],
            "constraints": [],
            "validation_rules": [],
            "execution_policy": {
                "timeout_seconds": max(30, body.time_limit + 15),
                "max_retries": 0,
            },
            "output_definition": [{"node_id": "optimize", "variable": "allocation"}],
        }
    )
    validation = validate_workflow(workflow, [model], [data], derived)
    if not validation.valid:
        raise CoastMASError(
            "CONSTRAINT_ERROR",
            "optimization configuration failed scientific preflight",
            {"issues": [encode(issue) for issue in validation.issues]},
        )
    workflow = workflow.model_copy(update={"input_bindings": validation.bindings})
    # Content-addressed project key makes a retry safe if file write precedes a DB rollback.
    stored = store.put(key, payload)
    if stored.sha256 != data_sha:
        raise CoastMASError(
            "CHECKSUM_ERROR", "optimization input write differs from supplied bytes"
        )
    for kind, spec in (("data", data), ("scene", derived), ("workflow", workflow)):
        create_resource(
            session,
            user_id=user_id,
            project_id=body.project_id,
            kind=kind,
            identifier=spec.id,
            name=spec.name,
            spec=spec.model_dump(mode="json"),
        )
    add_dependencies(session, data.id, 1, [(original.id, original.version)])
    add_dependencies(session, derived.id, 1, [(original.id, original.version)])
    manifest, report = candidate_manifest(
        session,
        user_id,
        body.project_id,
        workflow,
        RunSelection(workflow_version=1, scene_id=derived.id, scene_version=1),
    )
    check_execution(request, manifest, report)
    record = OptimizationSpec(
        id=identifier,
        name=body.name,
        version=1,
        source_scene=body.scene,
        scene=VersionReference(id=scene_id, version=1),
        data=VersionReference(id=data_id, version=1),
        workflow=VersionReference(id=workflow_id, version=1),
        request_checksum=checksum,
    )
    revision = create_resource(
        session,
        user_id=user_id,
        project_id=body.project_id,
        kind="optimization",
        identifier=identifier,
        name=record.name,
        spec=record.model_dump(mode="json"),
    )
    session.commit()
    return encode(revision)


@router.get("")
def records(
    project_id: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, JsonValue]]:
    require_permission(session, user_id, project_id, "read")
    query = (
        select(Resource)
        .where(
            Resource.project_id == project_id,
            Resource.kind == "optimization",
            Resource.archived.is_(False),
        )
        .order_by(Resource.name, Resource.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        encode(read_resource(session, user_id=user_id, identifier=row.id))
        for row in session.scalars(query)
    ]


@router.get("/{identifier}")
def get_record(
    identifier: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    version: int | None = Query(default=None, ge=1),
) -> dict[str, JsonValue]:
    record_spec(identifier, session, user_id, version)
    return encode(read_resource(session, user_id=user_id, identifier=identifier, version=version))


@router.get("/{identifier}/input", response_model=OptimizationFrame)
def inputs(
    identifier: str,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
    version: int | None = Query(default=None, ge=1),
) -> OptimizationFrame:
    record = record_spec(identifier, session, user_id, version)
    data = data_resource(record.data.id, session, user_id, record.data.version)
    document = json.loads(stored_content(request, session, data))
    return OptimizationFrame.model_validate(document.get("candidates"))


@router.post("/{identifier}/run", status_code=202)
def run(
    identifier: str,
    body: RunOptimizationRequest,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
    idempotency_key: IdempotencyKey,
) -> dict[str, JsonValue]:
    resource_in_project(session, user_id, identifier, "optimization")
    record = record_spec(identifier, session, user_id, body.optimization_version)
    return run_workflow(
        record.workflow.id,
        RunSelection(
            workflow_version=record.workflow.version,
            scene_id=record.scene.id,
            scene_version=record.scene.version,
            random_seed=body.random_seed,
        ),
        request,
        session,
        user_id,
        idempotency_key,
    )


@router.get("/{identifier}/runs")
def runs(
    identifier: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    version: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, JsonValue]]:
    record = record_spec(identifier, session, user_id, version)
    resource = session.get(Resource, identifier)
    assert resource is not None
    query = (
        select(Job, ResultBundle.id)
        .outerjoin(ResultBundle, ResultBundle.job_id == Job.id)
        .where(
            Job.project_id == resource.project_id,
            Job.manifest.contains(
                {
                    "workflow": record.workflow.model_dump(mode="json"),
                    "scene": record.scene.model_dump(mode="json"),
                }
            ),
        )
        .order_by(Job.created_at.desc(), Job.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        {"job": encode(snapshot(job)), "result_id": result_id}
        for job, result_id in session.execute(query)
    ]


@router.delete("/{identifier}", status_code=204)
def archive(identifier: str, session: DatabaseSession, user_id: CurrentUser) -> None:
    record_spec(identifier, session, user_id)
    archive_resource(session, user_id=user_id, identifier=identifier)
    session.commit()
