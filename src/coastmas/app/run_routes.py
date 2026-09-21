"""Server-built run snapshots and durable queue, job and result endpoints."""

import hashlib
import os
import platform
from datetime import UTC, datetime
from importlib.metadata import version
from typing import Annotated, cast
from uuid import uuid4

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from pydantic import Field, JsonValue
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from coastmas.adapters.storage import ArtifactRecord
from coastmas.app.dependencies import CurrentUser, DatabaseSession, artifact_store
from coastmas.core.contracts import (
    Contract,
    DataAssetSpec,
    ModelSpec,
    Name,
    RunManifest,
    SceneSpec,
    VersionReference,
    WorkflowSpec,
)
from coastmas.core.errors import CoastMASError, ConstraintError
from coastmas.core.execution import ExecutionRegistry
from coastmas.core.research_planning import ResearchManifest
from coastmas.core.scene_workspace import inspect_scene
from coastmas.core.validation import ValidationIssue, ValidationReport, validate_workflow
from coastmas.persistence.jobs import cancel_job, read_job, read_result, snapshot, submit_job
from coastmas.persistence.lifecycle import archive_resource
from coastmas.persistence.research import verify_research_inputs
from coastmas.persistence.resources import fingerprint, read_resource, require_permission
from coastmas.persistence.scenes import scene_resources
from coastmas.persistence.schema import AuditLog, Job, Resource, ResultBundle

router = APIRouter(prefix="/api/v1", tags=["runs"])
IdempotencyKey = Annotated[str, Header(min_length=1, max_length=256)]


class RunSelection(Contract):
    workflow_version: int = Field(ge=1)
    scene_id: Name
    scene_version: int = Field(ge=1)
    random_seed: int = Field(default=42, ge=0, le=2**32 - 1)


class WorkflowDraftSelection(Contract):
    project_id: Name
    workflow: WorkflowSpec
    scene: VersionReference
    random_seed: int = Field(default=42, ge=0, le=2**32 - 1)


def encode(value: object) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], jsonable_encoder(value))


def resource_in_project(
    session: Session, user: str, identifier: str, kind: str, project: str | None = None
) -> Resource:
    resource = session.scalar(
        select(Resource)
        .where(Resource.id == identifier)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if resource is None or resource.kind != kind or (project and resource.project_id != project):
        raise CoastMASError("AUTHORIZATION_ERROR", "resource unavailable in this project")
    require_permission(session, user, resource.project_id, "read")
    if resource.archived or not resource.enabled:
        raise CoastMASError("RESOURCE_UNAVAILABLE", "run resource is archived or disabled")
    return resource


def load_manifest(
    session: Session, user: str, workflow_id: str, selection: RunSelection
) -> tuple[str, RunManifest, ValidationReport]:
    record = resource_in_project(session, user, workflow_id, "workflow")
    workflow = WorkflowSpec.model_validate(
        read_resource(
            session, user_id=user, identifier=workflow_id, version=selection.workflow_version
        ).spec
    )
    manifest, report = candidate_manifest(session, user, record.project_id, workflow, selection)
    return record.project_id, manifest, report


def candidate_manifest(
    session: Session, user: str, project: str, workflow: WorkflowSpec, selection: RunSelection
) -> tuple[RunManifest, ValidationReport]:
    require_permission(session, user, project, "read")
    resource_in_project(session, user, selection.scene_id, "scene", project)
    scene = SceneSpec.model_validate(
        read_resource(
            session, user_id=user, identifier=selection.scene_id, version=selection.scene_version
        ).spec
    )
    models: list[ModelSpec] = []
    assets: list[DataAssetSpec] = []
    references = {(node.model_id, node.model_version, "model") for node in workflow.nodes}
    references.update(
        (binding.source.id, binding.source.version, "data") for binding in workflow.input_bindings
    )
    for identifier, revision, kind in sorted(references):
        resource_in_project(session, user, identifier, kind, project)
        content = read_resource(session, user_id=user, identifier=identifier, version=revision).spec
        if kind == "model":
            models.append(ModelSpec.model_validate(content))
        else:
            assets.append(DataAssetSpec.model_validate(content))
    selected_assets, entities = scene_resources(session, user, project, scene)
    known_assets = {(asset.id, asset.version) for asset in assets}
    assets.extend(
        asset for asset in selected_assets if (asset.id, asset.version) not in known_assets
    )
    report = validate_workflow(workflow, models, assets, scene)
    if entities:
        inspection = inspect_scene(scene, [], entities)
        if not inspection.valid:
            report = ValidationReport(
                report.issues
                + tuple(ValidationIssue("SCENE_ENTITY", issue) for issue in inspection.issues),
                report.bindings,
            )
    manifest = RunManifest(
        scene=scene,
        workflow=workflow,
        models=tuple(models),
        data_assets=tuple(assets),
        parameters=workflow.parameter_bindings,
        bindings=workflow.input_bindings,
        software_version=version("coastmas"),
        container_image=os.environ.get("COASTMAS_IMAGE_DIGEST", "local-python-not-containerized"),
        timestamp=datetime.now(UTC),
        random_seed=selection.random_seed,
        environment={"python": platform.python_version(), "platform": platform.system()},
    )
    return manifest, report


def check_execution(request: Request, manifest: RunManifest, report: ValidationReport) -> None:
    if not report.valid:
        raise ConstraintError(
            "workflow preflight rejected execution",
            {"issues": [encode(issue) for issue in report.issues]},
        )
    registry = cast(ExecutionRegistry, request.app.state.registry)
    for model in manifest.models:
        registry.resolve(model)


def lock_submission(session: Session, project: str, user: str, key: str) -> None:
    # Serialize the scope before timestamps are created. Hash collisions only serialize
    # unrelated requests; the database's full idempotency tuple still defines identity.
    digest = hashlib.sha256(f"{project}\0{user}\0{key}".encode()).digest()
    lock_id = int.from_bytes(digest[:8], byteorder="big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})


def existing_submission(session: Session, project: str, user: str, key: str) -> Job | None:
    return session.scalar(
        select(Job).where(
            Job.project_id == project, Job.submitted_by == user, Job.idempotency_key == key
        )
    )


def preflight_response(
    request: Request, manifest: RunManifest, report: ValidationReport
) -> dict[str, JsonValue]:
    issues = list(report.issues)
    registry = cast(ExecutionRegistry, request.app.state.registry)
    for model in manifest.models:
        try:
            registry.resolve(model)
        except CoastMASError as exc:
            for node in manifest.workflow.nodes:
                if (node.model_id, node.model_version) == (model.id, model.version):
                    issues.append(ValidationIssue(exc.code, exc.message, node.id))
    return {
        "valid": not issues,
        "issues": [encode(item) for item in issues],
        "bindings": [item.model_dump(mode="json") for item in report.bindings],
    }


@router.post("/workflow-drafts/validate")
def preflight_draft(
    body: WorkflowDraftSelection, request: Request, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    selection = RunSelection(
        workflow_version=body.workflow.version,
        scene_id=body.scene.id,
        scene_version=body.scene.version,
        random_seed=body.random_seed,
    )
    manifest, report = candidate_manifest(
        session, user_id, body.project_id, body.workflow, selection
    )
    return preflight_response(request, manifest, report)


@router.post("/workflows/{identifier}/validate")
def preflight(
    identifier: str,
    body: RunSelection,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
) -> dict[str, JsonValue]:
    _, manifest, report = load_manifest(session, user_id, identifier, body)
    return preflight_response(request, manifest, report)


@router.post("/workflows/{identifier}/run", status_code=202)
def run_workflow(
    identifier: str,
    body: RunSelection,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
    idempotency_key: IdempotencyKey,
) -> dict[str, JsonValue]:
    record = session.get(Resource, identifier)
    if record is None or record.kind != "workflow":
        raise CoastMASError("AUTHORIZATION_ERROR", "workflow unavailable")
    require_permission(session, user_id, record.project_id, "write")
    lock_submission(session, record.project_id, user_id, idempotency_key)
    existing = existing_submission(session, record.project_id, user_id, idempotency_key)
    if existing is not None:
        original = RunManifest.model_validate(existing.manifest)
        if (
            original.workflow.id != identifier
            or original.workflow.version != body.workflow_version
            or original.scene.id != body.scene_id
            or original.scene.version != body.scene_version
            or original.random_seed != body.random_seed
        ):
            raise CoastMASError(
                "IDEMPOTENCY_CONFLICT", "idempotency key has different run selection"
            )
        return encode(snapshot(existing))
    project, manifest, report = load_manifest(session, user_id, identifier, body)
    check_execution(request, manifest, report)
    job = submit_job(
        session,
        user_id=user_id,
        project_id=project,
        idempotency_key=idempotency_key,
        manifest=manifest.model_dump(mode="json"),
    )
    session.commit()
    # QUEUED is durable before responding. The independent dispatcher consumes it.
    return encode(job)


@router.get("/jobs")
def list_jobs(
    project_id: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, JsonValue]]:
    require_permission(session, user_id, project_id, "read")
    records = session.scalars(
        select(Job)
        .where(Job.project_id == project_id)
        .order_by(Job.created_at.desc(), Job.id)
        .offset(offset)
        .limit(limit)
    )
    return [encode(snapshot(job)) for job in records]


@router.get("/jobs/{identifier}")
def get_job(
    identifier: str, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    return encode(read_job(session, user_id=user_id, job_id=identifier))


@router.post("/jobs/{identifier}/cancel")
def cancel(identifier: str, session: DatabaseSession, user_id: CurrentUser) -> dict[str, JsonValue]:
    cancel_job(session, user_id=user_id, job_id=identifier)
    result = read_job(session, user_id=user_id, job_id=identifier)
    session.commit()
    return encode(result)


@router.post("/jobs/{identifier}/retry", status_code=202)
def retry(
    identifier: str,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
    idempotency_key: IdempotencyKey,
) -> dict[str, JsonValue]:
    original = read_job(session, user_id=user_id, job_id=identifier)
    require_permission(session, user_id, original.project_id, "write")
    if original.status not in {"FAILED", "CANCELLED"}:
        raise CoastMASError("JOB_STATE", "only failed or cancelled jobs can be retried")
    if original.error and original.error.get("error_code") == "REMOTE_STATUS_UNKNOWN":
        raise CoastMASError("REMOTE_RETRY_UNSAFE", "remote status must be reconciled before retry")
    lock_submission(session, original.project_id, user_id, idempotency_key)
    existing = existing_submission(session, original.project_id, user_id, idempotency_key)
    if existing is not None:
        origin = session.scalar(
            select(AuditLog).where(
                AuditLog.resource == existing.id,
                AuditLog.action == "RETRY",
                AuditLog.old_value["job_id"].astext == identifier,
            )
        )
        if existing.fingerprint != fingerprint(original.manifest) or origin is None:
            raise CoastMASError("IDEMPOTENCY_CONFLICT", "retry key refers to different run inputs")
        return encode(snapshot(existing))
    if original.manifest.get("kind") == "research_evaluation":
        research = ResearchManifest.model_validate(original.manifest)
        verify_research_inputs(session, user_id, original.project_id, research)
    else:
        manifest = RunManifest.model_validate(original.manifest)
        # Preserve the exact scientific snapshot, including seed, across explicit retries.
        _, current, report = load_manifest(
            session,
            user_id,
            manifest.workflow.id,
            RunSelection(
                workflow_version=manifest.workflow.version,
                scene_id=manifest.scene.id,
                scene_version=manifest.scene.version,
                random_seed=manifest.random_seed,
            ),
        )
        check_execution(request, current, report)
    job = submit_job(
        session,
        user_id=user_id,
        project_id=original.project_id,
        idempotency_key=idempotency_key,
        manifest=original.manifest,
    )
    session.add(
        AuditLog(
            id=str(uuid4()),
            who=user_id,
            action="RETRY",
            resource=job.id,
            old_value={"job_id": identifier},
            new_value={"job_id": job.id},
        )
    )
    session.commit()
    return encode(job)


def published_result_type(manifest: dict[str, JsonValue]) -> str:
    descriptor = manifest.get("result_manifest")
    if isinstance(descriptor, dict):
        kind = descriptor.get("result_type")
        if isinstance(kind, str):
            return kind
    return "workflow_bundle"


@router.get("/results")
def list_results(
    project_id: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, JsonValue]]:
    require_permission(session, user_id, project_id, "read")
    records = session.scalars(
        select(ResultBundle)
        .join(Job)
        .where(Job.project_id == project_id)
        .order_by(ResultBundle.created_at.desc(), ResultBundle.id)
        .offset(offset)
        .limit(limit)
    )
    return [
        {
            "id": item.id,
            "job_id": item.job_id,
            "checksum": item.checksum,
            "created_at": item.created_at.isoformat(),
            "result_type": published_result_type(item.manifest),
        }
        for item in records
    ]


def result_record(session: Session, user: str, identifier: str) -> ResultBundle:
    result = session.get(ResultBundle, identifier)
    if result is None:
        raise CoastMASError("AUTHORIZATION_ERROR", "result unavailable")
    read_result(session, user_id=user, job_id=result.job_id)
    return result


@router.get("/results/{identifier}")
def get_result(
    identifier: str,
    session: DatabaseSession,
    user_id: CurrentUser,
) -> dict[str, JsonValue]:
    result = result_record(session, user_id, identifier)
    return {
        "id": result.id,
        "job_id": result.job_id,
        "manifest": result.manifest,
        "checksum": result.checksum,
    }


@router.get("/results/{identifier}/provenance")
def provenance(
    identifier: str,
    session: DatabaseSession,
    user_id: CurrentUser,
) -> dict[str, JsonValue]:
    result = result_record(session, user_id, identifier)
    job = session.get(Job, result.job_id)
    if job is None or fingerprint(job.manifest) != job.fingerprint:
        raise CoastMASError("CHECKSUM_ERROR", "run manifest integrity check failed")
    return job.manifest


@router.get("/results/{identifier}/content")
def result_content(
    identifier: str,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
) -> Response:
    result = result_record(session, user_id, identifier)
    manifest = result.manifest
    key, bucket, checksum, size = (
        manifest.get("key"),
        manifest.get("bucket"),
        manifest.get("sha256"),
        manifest.get("size"),
    )
    if (
        not isinstance(key, str)
        or not isinstance(bucket, str)
        or not isinstance(checksum, str)
        or not isinstance(size, int)
        or isinstance(size, bool)
    ):
        raise CoastMASError("RESULT_FORMAT", "published artifact descriptor is invalid")
    store = artifact_store(request)
    content = store.read(ArtifactRecord(bucket, key, checksum, size))
    return Response(
        content,
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "ETag": '"' + checksum + '"',
        },
    )


@router.delete("/workflows/{identifier}", status_code=204)
def archive_workflow(identifier: str, session: DatabaseSession, user_id: CurrentUser) -> None:
    record = session.get(Resource, identifier)
    if record is None or record.kind != "workflow":
        raise CoastMASError("NOT_FOUND", "workflow unavailable")
    archive_resource(session, user_id=user_id, identifier=identifier)
    session.commit()
