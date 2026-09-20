"""Authenticated model library operations; metadata cannot self-certify execution."""

import hashlib
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from pydantic import Field, FiniteFloat, JsonValue
from sqlalchemy import func, select

from coastmas.app.dependencies import CurrentUser, DatabaseSession
from coastmas.core.contracts import Contract, DataAssetSpec, ModelSpec, Name, SceneSpec
from coastmas.core.decomposition import DecompositionRequest, ModelDecomposition, decompose_model
from coastmas.core.errors import CoastMASError
from coastmas.core.execution import ExecutionRegistry, RegisteredRuntime
from coastmas.core.matching import MatchWeights, match_models
from coastmas.core.model_documents import export_model, import_model
from coastmas.persistence.lifecycle import archive_resource, resource_history
from coastmas.persistence.resources import (
    create_resource,
    read_resource,
    require_permission,
    update_resource,
)
from coastmas.persistence.schema import AuditLog, Resource, ResourceVersion

router = APIRouter(prefix="/api/v1/models", tags=["models"])


class ImportRequest(Contract):
    project_id: Name
    format: Literal["json", "yaml"]
    content: str = Field(min_length=1, max_length=262144)
    identifier: Name | None = None


class CopyRequest(Contract):
    name: Name


class EnabledRequest(Contract):
    expected_version: int = Field(ge=1)
    enabled: bool


def model_resource(session: DatabaseSession, user_id: str, identifier: str) -> Resource:
    resource = session.get(Resource, identifier)
    if resource is None or resource.kind != "model":
        raise CoastMASError("NOT_FOUND", "model unavailable")
    require_permission(session, user_id, resource.project_id, "read", resource.published)
    return resource


@router.post("/decompose")
def decomposition(body: DecompositionRequest, user_id: CurrentUser) -> ModelDecomposition:
    return decompose_model(body)


@router.post("/import", status_code=201)
def import_document(
    body: ImportRequest, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    require_permission(session, user_id, body.project_id, "write")
    source = import_model(body.content, body.format)
    now = datetime.now(UTC)
    model = source.model_copy(
        update={
            "id": body.identifier or source.id,
            "version": 1,
            "created_at": now,
            "updated_at": now,
            "owner": user_id,
        }
    )
    revision = create_resource(
        session,
        user_id=user_id,
        project_id=body.project_id,
        kind="model",
        identifier=model.id,
        name=model.name,
        spec=model.model_dump(mode="json"),
    )
    session.add(
        AuditLog(
            id=str(uuid4()),
            who=user_id,
            action="IMPORT",
            resource=model.id,
            old_value=None,
            new_value={
                "source_model_id": source.id,
                "source_version": source.version,
                "document_sha256": hashlib.sha256(body.content.encode()).hexdigest(),
            },
        )
    )
    session.commit()
    return cast(dict[str, JsonValue], asdict(revision))


@router.get("/search")
def search_models(
    project_id: str,
    response: Response,
    session: DatabaseSession,
    user_id: CurrentUser,
    q: str = Query(default="", max_length=256),
    capability: str | None = None,
    model_type: str | None = None,
    enabled: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, JsonValue]]:
    require_permission(session, user_id, project_id, "read")
    query = select(Resource, ResourceVersion).join(
        ResourceVersion,
        (ResourceVersion.resource_id == Resource.id)
        & (ResourceVersion.version == Resource.current_version),
    )
    query = query.where(
        Resource.project_id == project_id, Resource.kind == "model", Resource.archived.is_(False)
    )
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Resource.name.ilike("%" + escaped + "%", escape="\\"))
    if capability:
        query = query.where(ResourceVersion.spec["capabilities"].contains([capability]))
    if model_type:
        query = query.where(ResourceVersion.spec["model_type"].astext == model_type)
    if enabled is not None:
        query = query.where(Resource.enabled == enabled)
    response.headers["X-Total-Count"] = str(
        session.scalar(select(func.count()).select_from(query.subquery()))
    )
    response.headers["Cache-Control"] = "no-store"
    records = session.execute(
        query.order_by(Resource.name, Resource.id).offset(offset).limit(limit)
    )
    return [
        {
            "id": resource.id,
            "name": resource.name,
            "version": resource.current_version,
            "enabled": resource.enabled,
            "spec": revision.spec,
        }
        for resource, revision in records
    ]


class MatchRequest(Contract):
    project_id: Name
    scene_id: Name
    scene_version: int = Field(ge=1)
    capability: Name
    parameters: dict[str, FiniteFloat] = Field(default_factory=dict, max_length=100)
    weights: MatchWeights = Field(default_factory=MatchWeights)
    preferences: dict[str, Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]] = Field(
        default_factory=dict, max_length=500
    )


@router.post("/match")
def match_catalog(
    body: MatchRequest, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    require_permission(session, user_id, body.project_id, "read")
    context = session.get(Resource, body.scene_id)
    if context is None or context.project_id != body.project_id or context.kind != "scene":
        raise CoastMASError("NOT_FOUND", "scene unavailable in this project")
    if context.archived:
        raise CoastMASError("RESOURCE_ARCHIVED", "archived scene cannot be planned")
    scene = SceneSpec.model_validate(
        read_resource(
            session, user_id=user_id, identifier=body.scene_id, version=body.scene_version
        ).spec
    )
    resources = list(
        session.scalars(
            select(Resource)
            .where(
                Resource.project_id == body.project_id,
                Resource.kind.in_(["model", "data"]),
                Resource.archived.is_(False),
            )
            .order_by(Resource.id)
            .limit(501)
        )
    )
    if len(resources) > 500:
        raise CoastMASError(
            "CATALOG_LIMIT", "matching catalog exceeds 500 resources; narrow project"
        )
    models: list[ModelSpec] = []
    assets: list[DataAssetSpec] = []
    for resource in resources:
        revision = read_resource(session, user_id=user_id, identifier=resource.id)
        if resource.kind == "model":
            candidate = ModelSpec.model_validate(revision.spec)
            # Operational disable always wins over historical metadata.
            if not resource.enabled:
                candidate = candidate.model_copy(update={"enabled": False})
            models.append(candidate)
        elif resource.enabled:
            assets.append(DataAssetSpec.model_validate(revision.spec))
    result = match_models(
        models,
        assets,
        scene,
        capability=body.capability,
        parameters=body.parameters,
        weights=body.weights,
        preferences=body.preferences,
    )
    return cast(dict[str, JsonValue], jsonable_encoder(result))


@router.get("/{identifier}/export")
def export_document(
    identifier: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    format: Literal["json", "yaml"] = "json",
    version: int | None = Query(default=None, ge=1),
) -> Response:
    model_resource(session, user_id, identifier)
    revision = read_resource(session, user_id=user_id, identifier=identifier, version=version)
    content = export_model(ModelSpec.model_validate(revision.spec), format)
    return Response(
        content,
        media_type="application/json" if format == "json" else "application/yaml",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{identifier}/versions")
def history(
    identifier: str, session: DatabaseSession, user_id: CurrentUser
) -> list[dict[str, JsonValue]]:
    model_resource(session, user_id, identifier)
    return [
        cast(dict[str, JsonValue], asdict(revision))
        for revision in resource_history(session, user_id=user_id, identifier=identifier)
    ]


@router.post("/{identifier}/copy", status_code=201)
def copy_model(
    identifier: str, body: CopyRequest, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    resource = model_resource(session, user_id, identifier)
    revision = read_resource(session, user_id=user_id, identifier=identifier)
    source = ModelSpec.model_validate(revision.spec)
    now = datetime.now(UTC)
    model = source.model_copy(
        update={
            "id": str(uuid4()),
            "name": body.name,
            "display_name": body.name,
            "version": 1,
            "created_at": now,
            "updated_at": now,
            "owner": user_id,
            "validation_status": "UNVALIDATED",
            "execution_status": "NOT_EXECUTABLE",
        }
    )
    result = create_resource(
        session,
        user_id=user_id,
        project_id=resource.project_id,
        kind="model",
        identifier=model.id,
        name=model.name,
        spec=model.model_dump(mode="json"),
    )
    session.commit()
    return cast(dict[str, JsonValue], asdict(result))


@router.post("/{identifier}/enabled")
def set_enabled(
    identifier: str,
    body: EnabledRequest,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
) -> dict[str, JsonValue]:
    resource = model_resource(session, user_id, identifier)
    current = read_resource(session, user_id=user_id, identifier=identifier)
    original = ModelSpec.model_validate(current.spec)
    registry = cast(ExecutionRegistry, request.app.state.registry)
    runtime: RegisteredRuntime | None = None
    if original.validation_status == "VALIDATED" and original.execution_status == "EXECUTABLE":
        try:
            runtime = registry.resolve(original)
        except CoastMASError:
            runtime = None
    model = original.model_copy(
        update={
            "version": body.expected_version + 1,
            "enabled": body.enabled,
            "updated_at": datetime.now(UTC),
            "validation_status": "VALIDATED" if runtime else "UNVALIDATED",
            "execution_status": "EXECUTABLE" if runtime else "NOT_EXECUTABLE",
        }
    )
    result = update_resource(
        session,
        user_id=user_id,
        identifier=identifier,
        expected_version=body.expected_version,
        spec=model.model_dump(mode="json"),
    )
    resource.enabled = body.enabled
    session.commit()
    if runtime is not None:
        try:
            registry.resolve(model)
        except CoastMASError:
            registry.register(model, runtime.adapter, runtime.handler)
    return cast(dict[str, JsonValue], asdict(result))


@router.delete("/{identifier}", status_code=204)
def delete_model(identifier: str, session: DatabaseSession, user_id: CurrentUser) -> None:
    model_resource(session, user_id, identifier)
    archive_resource(session, user_id=user_id, identifier=identifier)
    session.commit()
