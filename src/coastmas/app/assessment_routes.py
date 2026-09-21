"""Frozen assessment records reuse the authenticated planning and job execution paths."""

from dataclasses import asdict
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Query, Request
from pydantic import Field, JsonValue
from sqlalchemy import select

from coastmas.app.dependencies import CurrentUser, DatabaseSession
from coastmas.app.planning_routes import persist_planned_workflow
from coastmas.app.run_routes import (
    IdempotencyKey,
    RunSelection,
    encode,
    resource_in_project,
    run_workflow,
)
from coastmas.core.contracts import Contract, Name, Version, VersionReference
from coastmas.core.errors import CoastMASError
from coastmas.core.indicators import AssessmentSpec, IndicatorFrameworkSpec
from coastmas.core.planning import PlanningArtifact
from coastmas.persistence.jobs import snapshot
from coastmas.persistence.lifecycle import archive_resource
from coastmas.persistence.planning import read_trace
from coastmas.persistence.resources import (
    create_resource,
    fingerprint,
    read_resource,
    require_permission,
)
from coastmas.persistence.schema import Job, Resource, ResourceDependency, ResultBundle

router = APIRouter(prefix="/api/v1/assessments", tags=["assessment"])


class SaveAssessmentRequest(Contract):
    planning_trace_id: Name
    name: Name | None = None


class RunAssessmentRequest(Contract):
    assessment_version: Version
    random_seed: int = Field(default=42, ge=0, le=2**32 - 1)


def record_spec(
    identifier: str, session: DatabaseSession, user_id: str, version: int | None = None
) -> AssessmentSpec:
    record = session.get(Resource, identifier)
    if record is None or record.kind != "assessment":
        raise CoastMASError("NOT_FOUND", "assessment unavailable")
    return AssessmentSpec.model_validate(
        read_resource(session, user_id=user_id, identifier=identifier, version=version).spec
    )


@router.post("", status_code=201)
def save(
    body: SaveAssessmentRequest, request: Request, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    trace = read_trace(session, user_id, body.planning_trace_id, lock=True)
    plan = PlanningArtifact.model_validate(trace.artifact)
    workflow = plan.candidate_workflow
    if workflow is None or plan.management_goal.template == "coastal_impact":
        raise CoastMASError(
            "PLAN_INCOMPLETE", "assessment requires a validated evaluation workflow"
        )
    bindings = [
        item
        for item in workflow.input_bindings
        if item.target.node_id == "normalize" and item.target.variable == "frame"
    ]
    if len(bindings) != 1:
        raise CoastMASError("DEPENDENCY_CONFLICT", "assessment requires exactly one prepared frame")
    data = bindings[0].source
    origins = list(
        session.execute(
            select(ResourceDependency.target_id, ResourceDependency.target_version)
            .join(Resource, Resource.id == ResourceDependency.target_id)
            .where(
                ResourceDependency.source_id == data.id,
                ResourceDependency.source_version == data.version,
                Resource.kind == "indicator_framework",
            )
        )
    )
    if len(origins) != 1:
        raise CoastMASError(
            "DEPENDENCY_CONFLICT", "assessment input has no unique framework origin"
        )
    framework_id, framework_version = origins[0]
    resource_in_project(session, user_id, framework_id, "indicator_framework", trace.project_id)
    framework = IndicatorFrameworkSpec.model_validate(
        read_resource(
            session, user_id=user_id, identifier=framework_id, version=framework_version
        ).spec
    )
    method = framework.indicators[0].weight_method
    weight_nodes = [node for node in workflow.nodes if node.id == "weight"]
    if (
        plan.management_goal.weight_method != method
        or len(weight_nodes) != 1
        or weight_nodes[0].parameters.get("method")
        != {"equal": 0, "manual": 1, "entropy": 2}[method]
    ):
        raise CoastMASError(
            "DEPENDENCY_CONFLICT", "assessment weighting differs from its framework"
        )
    # One transaction and the planning-row lock make retries/concurrent saves atomic.
    persist_planned_workflow(trace.id, request, session, user_id)
    spec = AssessmentSpec(
        id=str(uuid5(NAMESPACE_URL, "coastmas:assessment:" + trace.id)),
        name=body.name or framework.name[:230] + " / assessment",
        version=1,
        framework=VersionReference(id=framework_id, version=framework_version),
        data=data,
        scene=plan.scene,
        workflow=VersionReference(id=workflow.id, version=workflow.version),
    )
    existing = session.get(Resource, spec.id)
    if existing is not None:
        revision = read_resource(session, user_id=user_id, identifier=spec.id, version=1)
        if (
            existing.kind != "assessment"
            or existing.project_id != trace.project_id
            or revision.checksum != fingerprint(spec.model_dump(mode="json"))
        ):
            raise CoastMASError(
                "VERSION_CONFLICT", "assessment save differs from the original request"
            )
    else:
        revision = create_resource(
            session,
            user_id=user_id,
            project_id=trace.project_id,
            kind="assessment",
            identifier=spec.id,
            name=spec.name,
            spec=spec.model_dump(mode="json"),
        )
    session.commit()
    return cast(dict[str, JsonValue], asdict(revision))


@router.get("")
def list_assessments(
    project_id: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, JsonValue]]:
    require_permission(session, user_id, project_id, "read")
    records = session.scalars(
        select(Resource)
        .where(
            Resource.project_id == project_id,
            Resource.kind == "assessment",
            Resource.archived.is_(False),
        )
        .order_by(Resource.name, Resource.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        cast(
            dict[str, JsonValue],
            asdict(read_resource(session, user_id=user_id, identifier=item.id)),
        )
        for item in records
    ]


@router.get("/{identifier}")
def get_record(
    identifier: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    version: int | None = Query(default=None, ge=1),
) -> dict[str, JsonValue]:
    record_spec(identifier, session, user_id, version)
    return cast(
        dict[str, JsonValue],
        asdict(read_resource(session, user_id=user_id, identifier=identifier, version=version)),
    )


@router.delete("/{identifier}", status_code=204)
def archive(identifier: str, session: DatabaseSession, user_id: CurrentUser) -> None:
    record_spec(identifier, session, user_id)
    archive_resource(session, user_id=user_id, identifier=identifier)
    session.commit()


@router.post("/{identifier}/run", status_code=202)
def run(
    identifier: str,
    body: RunAssessmentRequest,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
    idempotency_key: IdempotencyKey,
) -> dict[str, JsonValue]:
    resource_in_project(session, user_id, identifier, "assessment")
    spec = record_spec(identifier, session, user_id, body.assessment_version)
    return run_workflow(
        spec.workflow.id,
        RunSelection(
            workflow_version=spec.workflow.version,
            scene_id=spec.scene.id,
            scene_version=spec.scene.version,
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
    spec = record_spec(identifier, session, user_id, version)
    record = session.get(Resource, identifier)
    assert record is not None
    # This is a factual configuration match, including jobs launched from Workflow.
    # No synthetic result or user-editable status is stored in the assessment.
    query = (
        select(Job, ResultBundle.id)
        .outerjoin(ResultBundle, ResultBundle.job_id == Job.id)
        .where(
            Job.project_id == record.project_id,
            Job.manifest.contains(
                {
                    "workflow": {"id": spec.workflow.id, "version": spec.workflow.version},
                    "scene": {"id": spec.scene.id, "version": spec.scene.version},
                    "data_assets": [{"id": spec.data.id, "version": spec.data.version}],
                }
            ),
        )
        .order_by(Job.created_at.desc(), Job.id)
        .offset(offset)
        .limit(limit)
    )
    return [
        {"job": encode(snapshot(job)), "result_id": result_id}
        for job, result_id in session.execute(query)
    ]
