"""Authenticated source registration and idempotent imports with fixed provenance."""

import hashlib
import json
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Query, Request
from pydantic import Field, JsonValue
from sqlalchemy import or_, select

from coastmas.adapters.source_connectors import fetch_source
from coastmas.adapters.source_registry import RegisteredSource
from coastmas.app.data_routes import data_resource, inspect_isolated
from coastmas.app.dependencies import CurrentUser, DatabaseSession, artifact_store
from coastmas.core.contracts import Contract, DataAssetSpec, Name
from coastmas.core.errors import CoastMASError
from coastmas.core.source_catalog import DataSourceSpec, SourceSnapshotRequest
from coastmas.persistence.lifecycle import archive_resource, resource_history
from coastmas.persistence.resources import (
    add_dependencies,
    create_resource,
    read_resource,
    require_permission,
    update_resource,
)
from coastmas.persistence.schema import Resource, ResourceDependency, ResourceVersion

router = APIRouter(prefix="/api/v1/data-sources", tags=["data sources"])


class CreateSourceRequest(Contract):
    project_id: Name
    spec: DataSourceSpec


class UpdateSourceRequest(Contract):
    expected_version: int = Field(ge=1)
    spec: DataSourceSpec


def source_resource(session: DatabaseSession, user_id: str, identifier: str) -> Resource:
    record = session.get(Resource, identifier)
    if record is None or record.kind != "data_source":
        raise CoastMASError("NOT_FOUND", "data source unavailable")
    require_permission(session, user_id, record.project_id, "read", record.published)
    return record


def configured(request: Request, project: str, spec: DataSourceSpec) -> RegisteredSource:
    registry = cast(dict[str, RegisteredSource], request.app.state.source_registry)
    source = registry.get(spec.connector_id)
    if source is None or source.kind != spec.kind:
        raise CoastMASError("SOURCE_CONFIGURATION", "source connector is not registered")
    if project not in source.projects:
        raise CoastMASError(
            "AUTHORIZATION_ERROR", "source connector is unavailable in this project"
        )
    return source


@router.get("/connectors")
def connectors(
    project_id: str, request: Request, session: DatabaseSession, user_id: CurrentUser
) -> list[dict[str, JsonValue]]:
    require_permission(session, user_id, project_id, "read")
    registry = cast(dict[str, RegisteredSource], request.app.state.source_registry)
    return [
        {"id": name, "name": value.label, "kind": value.kind, "revision": value.revision}
        for name, value in sorted(registry.items())
        if project_id in value.projects
    ]


@router.get("")
def list_sources(
    project_id: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    q: str = Query(default="", max_length=256),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, JsonValue]]:
    require_permission(session, user_id, project_id, "read")
    query = select(Resource).where(
        Resource.project_id == project_id,
        Resource.kind == "data_source",
        Resource.archived.is_(False),
    )
    if q.strip():
        query = query.where(
            or_(
                Resource.name.contains(q.strip(), autoescape=True),
                Resource.id.contains(q.strip(), autoescape=True),
            )
        )
    return [
        cast(
            dict[str, JsonValue],
            asdict(read_resource(session, user_id=user_id, identifier=record.id)),
        )
        for record in session.scalars(
            query.order_by(Resource.name, Resource.id).offset(offset).limit(limit)
        )
    ]


@router.post("", status_code=201)
def create_source(
    body: CreateSourceRequest, request: Request, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    require_permission(session, user_id, body.project_id, "write")
    configured(request, body.project_id, body.spec)
    revision = create_resource(
        session,
        user_id=user_id,
        project_id=body.project_id,
        kind="data_source",
        identifier=body.spec.id,
        name=body.spec.name,
        spec=body.spec.model_dump(mode="json"),
    )
    session.commit()
    return cast(dict[str, JsonValue], asdict(revision))


@router.get("/for-asset/{identifier}")
def source_lineage(
    identifier: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    version: int | None = Query(default=None, ge=1),
) -> list[dict[str, JsonValue]]:
    data = data_resource(identifier, session, user_id, version)
    # Metadata revisions of the same file preserve its actual import origin. Never
    # trust a user-editable quality field as evidence of a source relationship.
    file_versions = select(ResourceVersion.version).where(
        ResourceVersion.resource_id == data.id,
        ResourceVersion.version <= data.version,
        ResourceVersion.spec["uri"].astext == data.uri,
        ResourceVersion.spec["checksum"].astext == data.checksum,
    )
    references = session.execute(
        select(ResourceDependency.target_id, ResourceDependency.target_version)
        .join(Resource, Resource.id == ResourceDependency.target_id)
        .where(
            ResourceDependency.source_id == data.id,
            ResourceDependency.source_version.in_(file_versions),
            Resource.kind == "data_source",
        )
        .distinct()
    )
    return [
        cast(
            dict[str, JsonValue],
            asdict(read_resource(session, user_id=user_id, identifier=reference, version=revision)),
        )
        for reference, revision in references
    ]


@router.get("/{identifier}")
def get_source(
    identifier: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    version: int | None = Query(default=None, ge=1),
) -> dict[str, JsonValue]:
    source_resource(session, user_id, identifier)
    return cast(
        dict[str, JsonValue],
        asdict(read_resource(session, user_id=user_id, identifier=identifier, version=version)),
    )


@router.get("/{identifier}/versions")
def history(
    identifier: str, session: DatabaseSession, user_id: CurrentUser
) -> list[dict[str, JsonValue]]:
    source_resource(session, user_id, identifier)
    return [
        cast(dict[str, JsonValue], asdict(row))
        for row in resource_history(session, user_id=user_id, identifier=identifier)
    ]


@router.put("/{identifier}")
def revise_source(
    identifier: str,
    body: UpdateSourceRequest,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
) -> dict[str, JsonValue]:
    record = source_resource(session, user_id, identifier)
    require_permission(session, user_id, record.project_id, "write")
    configured(request, record.project_id, body.spec)
    revision = update_resource(
        session,
        user_id=user_id,
        identifier=identifier,
        expected_version=body.expected_version,
        spec=body.spec.model_dump(mode="json"),
    )
    session.commit()
    return cast(dict[str, JsonValue], asdict(revision))


@router.delete("/{identifier}", status_code=204)
def archive(identifier: str, session: DatabaseSession, user_id: CurrentUser) -> None:
    source_resource(session, user_id, identifier)
    archive_resource(session, user_id=user_id, identifier=identifier)
    session.commit()


@router.post("/{identifier}/snapshots", status_code=201)
def import_snapshot(
    identifier: str,
    body: SourceSnapshotRequest,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
) -> dict[str, JsonValue]:
    record = source_resource(session, user_id, identifier)
    require_permission(session, user_id, record.project_id, "write")
    # Serialize duplicate imports and source lifecycle changes before external I/O.
    session.execute(
        select(Resource)
        .where(Resource.id == identifier)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    if record.archived or not record.enabled:
        raise CoastMASError("RESOURCE_ARCHIVED", "source is not active")
    if record.current_version != body.expected_version:
        raise CoastMASError("VERSION_CONFLICT", "source version changed; reload before importing")
    spec = DataSourceSpec.model_validate(
        read_resource(session, user_id=user_id, identifier=identifier).spec
    )
    connector = configured(request, record.project_id, spec)
    identity = str(
        uuid5(NAMESPACE_URL, json.dumps([record.project_id, identifier, body.idempotency_key]))
    )
    existing = session.get(Resource, identity)
    if existing is not None:
        previous = read_resource(session, user_id=user_id, identifier=identity, version=1)
        linked = session.get(ResourceDependency, (identity, 1, identifier, spec.version))
        if existing.kind != "data" or existing.project_id != record.project_id or linked is None:
            raise CoastMASError(
                "VERSION_CONFLICT", "import key was used with a different source version"
            )
        return cast(dict[str, JsonValue], asdict(previous))
    with tempfile.TemporaryDirectory(prefix="coastmas-source-") as directory:
        content = fetch_source(connector.source, work_root=Path(directory))
    digest = hashlib.sha256(content).hexdigest()
    data = DataAssetSpec.model_validate(
        {
            **spec.output.model_dump(mode="json"),
            "id": identity,
            "version": 1,
            "uri": "import:pending",
            "checksum": digest,
            "quality": {},
        }
    )
    report = inspect_isolated(content, data)
    require_permission(session, user_id, record.project_id, "write")
    stored = artifact_store(request).put(f"{record.project_id}/data/{identity}/{digest}", content)
    data = data.model_copy(
        update={
            "uri": stored.uri,
            "quality": {
                **report.metadata,
                "imported_at": datetime.now(UTC).isoformat(),
                "connector_id": spec.connector_id,
                "connector_revision": connector.revision,
            },
        }
    )
    revision = create_resource(
        session,
        user_id=user_id,
        project_id=record.project_id,
        kind="data",
        identifier=identity,
        name=data.name,
        spec=data.model_dump(mode="json"),
    )
    add_dependencies(session, identity, 1, [(identifier, spec.version)])
    session.commit()
    return cast(dict[str, JsonValue], asdict(revision))
