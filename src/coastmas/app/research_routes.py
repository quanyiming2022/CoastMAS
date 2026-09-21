"""Freeze authorized case selections and submit research to the shared durable worker."""

import json
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from pydantic import Field, JsonValue
from sqlalchemy import select

from coastmas.app.dependencies import CurrentUser, DatabaseSession
from coastmas.app.run_routes import (
    IdempotencyKey,
    encode,
    existing_submission,
    lock_submission,
    resource_in_project,
    result_content,
)
from coastmas.core.contracts import (
    Contract,
    DataAssetSpec,
    ModelSpec,
    Name,
    SceneSpec,
    VersionReference,
)
from coastmas.core.errors import CoastMASError
from coastmas.core.llm import OpenAICompatibleProvider
from coastmas.core.research import Experiment
from coastmas.core.research_planning import ResearchCase, ResearchManifest
from coastmas.core.research_provider import provider_identity, research_prompt
from coastmas.persistence.jobs import read_job, snapshot, submit_job
from coastmas.persistence.resources import fingerprint, read_resource, require_permission
from coastmas.persistence.schema import Job, ResultBundle

router = APIRouter(prefix="/api/v1/research", tags=["research"])


class ResearchCaseSelection(Contract):
    id: Name
    goal: Annotated[str, Field(min_length=1, max_length=8000)]
    scene: VersionReference
    models: Annotated[tuple[VersionReference, ...], Field(min_length=1, max_length=12)]
    assets: Annotated[tuple[VersionReference, ...], Field(max_length=64)]
    selected_data: dict[str, VersionReference] = Field(default_factory=dict, max_length=64)


class ResearchRequest(Contract):
    project_id: Name
    cases: Annotated[tuple[ResearchCaseSelection, ...], Field(min_length=1, max_length=20)]
    experiments: Annotated[tuple[Experiment, ...], Field(min_length=1, max_length=3)]
    repetitions: Annotated[int, Field(strict=True, ge=1, le=5)] = 1
    allow_provider: bool = False


@router.post("", status_code=202)
def submit(
    body: ResearchRequest,
    request: Request,
    session: DatabaseSession,
    user: CurrentUser,
    idempotency_key: IdempotencyKey,
) -> dict[str, JsonValue]:
    require_permission(session, user, body.project_id, "write")
    lock_submission(session, body.project_id, user, "research:" + idempotency_key)
    checksum = fingerprint(body.model_dump(mode="json"))
    existing = existing_submission(session, body.project_id, user, idempotency_key)
    if existing is not None:
        if (
            existing.manifest.get("kind") != "research_evaluation"
            or existing.manifest.get("request_checksum") != checksum
        ):
            raise CoastMASError("IDEMPOTENCY_CONFLICT", "research key has different inputs")
        return encode(snapshot(existing))

    def load(reference: VersionReference, kind: str) -> dict[str, JsonValue]:
        resource_in_project(session, user, reference.id, kind, body.project_id)
        return read_resource(
            session, user_id=user, identifier=reference.id, version=reference.version
        ).spec

    cases = tuple(
        ResearchCase(
            id=case.id,
            goal=case.goal,
            scene=SceneSpec.model_validate(load(case.scene, "scene")),
            models=tuple(ModelSpec.model_validate(load(ref, "model")) for ref in case.models),
            assets=tuple(DataAssetSpec.model_validate(load(ref, "data")) for ref in case.assets),
            selected_data=case.selected_data,
        )
        for case in body.cases
    )
    provider = request.app.state.llm_provider
    identity = (
        provider_identity(provider)
        if body.allow_provider and isinstance(provider, OpenAICompatibleProvider)
        else None
    )
    # Build prompts before queuing: oversize or credential-bearing metadata is not dispatched.
    if identity is not None:
        for case in cases:
            for experiment in body.experiments:
                if experiment != "A":
                    research_prompt(case, experiment)
    manifest = ResearchManifest(
        cases=cases,
        experiments=body.experiments,
        repetitions=body.repetitions,
        request_checksum=checksum,
        evaluation_id=str(uuid4()),
        provider=identity,
    )
    job = submit_job(
        session,
        user_id=user,
        project_id=body.project_id,
        idempotency_key=idempotency_key,
        manifest=manifest.model_dump(mode="json"),
    )
    session.commit()
    return encode(job)


@router.get("")
def list_research(
    project_id: str,
    session: DatabaseSession,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, JsonValue]]:
    require_permission(session, user, project_id, "read")
    jobs = session.scalars(
        select(Job)
        .where(Job.project_id == project_id, Job.manifest["kind"].astext == "research_evaluation")
        .order_by(Job.created_at.desc(), Job.id)
        .offset(offset)
        .limit(limit)
    )
    return [encode(snapshot(job)) for job in jobs]


@router.get("/{identifier}/report")
def report(
    identifier: str, request: Request, session: DatabaseSession, user: CurrentUser
) -> dict[str, JsonValue]:
    job = read_job(session, user_id=user, job_id=identifier)
    if job.manifest.get("kind") != "research_evaluation":
        raise CoastMASError("NOT_FOUND", "research task unavailable")
    if job.status != "SUCCEEDED":
        raise CoastMASError("RESULT_NOT_READY", "research report is not published")
    result = session.scalar(select(ResultBundle).where(ResultBundle.job_id == identifier))
    if result is None:
        raise CoastMASError("RESULT_FORMAT", "research result missing")
    response = result_content(result.id, request, session, user)
    value = json.loads(bytes(response.body))
    if not isinstance(value, dict) or value.get("kind") != "research_evaluation":
        raise CoastMASError("RESULT_FORMAT", "research report has invalid type")
    return value
