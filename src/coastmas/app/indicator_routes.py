"""Indicator framework lifecycle and immutable, project-scoped derived input files."""

import hashlib
import json
from dataclasses import asdict
from typing import Literal, cast
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Query, Request
from pydantic import JsonValue
from sqlalchemy import select

from coastmas.adapters.projection_pursuit import ProjectionFrame
from coastmas.app.data_routes import data_resource, inspect_isolated, stored_content
from coastmas.app.dependencies import CurrentUser, DatabaseSession, artifact_store
from coastmas.app.planning_routes import PlanRequest, create_plan
from coastmas.app.run_routes import resource_in_project
from coastmas.core.contracts import Contract, Name, Version, VersionReference
from coastmas.core.errors import CoastMASError, ConstraintError
from coastmas.core.indicators import DEMO_CATEGORIES, IndicatorFrameworkSpec
from coastmas.core.planning import ManagementGoal
from coastmas.domain.indicator_frames import IndicatorFrame
from coastmas.domain.indicator_framework import apply_framework
from coastmas.persistence.lifecycle import archive_resource, resource_history
from coastmas.persistence.resources import (
    add_dependencies,
    create_resource,
    read_resource,
    require_permission,
)
from coastmas.persistence.schema import Resource, ResourceDependency, ResourceVersion

router = APIRouter(prefix="/api/v1/indicator-frameworks", tags=["assessment"])


class PrepareIndicatorsRequest(Contract):
    expected_version: Version
    data: VersionReference
    idempotency_key: Name


def framework_resource(session: DatabaseSession, user_id: str, identifier: str) -> Resource:
    record = session.get(Resource, identifier)
    if record is None or record.kind != "indicator_framework":
        raise CoastMASError("NOT_FOUND", "indicator framework unavailable")
    require_permission(session, user_id, record.project_id, "read", record.published)
    return record


@router.get("/demo-categories")
def demo_categories(user_id: CurrentUser) -> dict[str, JsonValue]:
    return {"label": "DEMO FRAMEWORK", "categories": list(DEMO_CATEGORIES)}


@router.get("/for-asset/{identifier}")
def lineage(
    identifier: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    version: int | None = Query(default=None, ge=1),
) -> dict[str, list[dict[str, JsonValue]]]:
    data = data_resource(identifier, session, user_id, version)
    # Reinspection and metadata-only revisions retain the same original bytes.
    origins = (
        select(ResourceVersion.version)
        .join(
            ResourceDependency,
            (ResourceDependency.source_id == ResourceVersion.resource_id)
            & (ResourceDependency.source_version == ResourceVersion.version),
        )
        .join(Resource, Resource.id == ResourceDependency.target_id)
        .where(
            ResourceVersion.resource_id == identifier,
            ResourceVersion.version <= data.version,
            ResourceVersion.spec["uri"].astext == data.uri,
            ResourceVersion.spec["checksum"].astext == data.checksum,
            Resource.kind == "indicator_framework",
        )
    )
    rows = session.execute(
        select(ResourceDependency.target_id, ResourceDependency.target_version, Resource.kind)
        .join(Resource, Resource.id == ResourceDependency.target_id)
        .where(
            ResourceDependency.source_id == identifier,
            ResourceDependency.source_version.in_(origins),
            Resource.kind.in_(("indicator_framework", "data")),
        )
        .distinct()
        .order_by(ResourceDependency.target_id, ResourceDependency.target_version)
    )
    output: dict[str, list[dict[str, JsonValue]]] = {"frameworks": [], "observations": []}
    for target, target_version, kind in rows:
        key = "frameworks" if kind == "indicator_framework" else "observations"
        output[key].append(
            cast(
                dict[str, JsonValue],
                asdict(
                    read_resource(
                        session, user_id=user_id, identifier=target, version=target_version
                    )
                ),
            )
        )
    return output


@router.get("/{identifier}/versions")
def versions(
    identifier: str, session: DatabaseSession, user_id: CurrentUser
) -> list[dict[str, JsonValue]]:
    framework_resource(session, user_id, identifier)
    return [
        cast(dict[str, JsonValue], asdict(row))
        for row in resource_history(session, user_id=user_id, identifier=identifier)
    ]


@router.delete("/{identifier}", status_code=204)
def archive(identifier: str, session: DatabaseSession, user_id: CurrentUser) -> None:
    framework_resource(session, user_id, identifier)
    archive_resource(session, user_id=user_id, identifier=identifier)
    session.commit()


@router.post("/{identifier}/prepare", status_code=201)
def prepare(
    identifier: str,
    body: PrepareIndicatorsRequest,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
) -> dict[str, JsonValue]:
    record = framework_resource(session, user_id, identifier)
    require_permission(session, user_id, record.project_id, "write")
    # Lock both identities in a stable order so archive/revision cannot race the import.
    records = list(
        session.scalars(
            select(Resource)
            .where(Resource.id.in_([identifier, body.data.id]))
            .order_by(Resource.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if any(item.archived or not item.enabled for item in records):
        raise CoastMASError("RESOURCE_ARCHIVED", "framework or observations are not active")
    source = next((item for item in records if item.id == body.data.id), None)
    if source is None or source.kind != "data" or source.project_id != record.project_id:
        raise CoastMASError("AUTHORIZATION_ERROR", "observations are unavailable in this project")
    if record.current_version != body.expected_version:
        raise CoastMASError("VERSION_CONFLICT", "framework changed; reload before preparing")
    framework = IndicatorFrameworkSpec.model_validate(
        read_resource(session, user_id=user_id, identifier=identifier).spec
    )
    data = data_resource(body.data.id, session, user_id, body.data.version)
    identity = str(
        uuid5(
            NAMESPACE_URL,
            json.dumps(
                [record.project_id, "indicator-framework", identifier, body.idempotency_key]
            ),
        )
    )
    existing = session.get(Resource, identity)
    references = [(identifier, framework.version), (data.id, data.version)]
    if existing is not None:
        if (
            existing.kind != "data"
            or existing.project_id != record.project_id
            or any(
                session.get(ResourceDependency, (identity, 1, target, version)) is None
                for target, version in references
            )
        ):
            raise CoastMASError(
                "VERSION_CONFLICT", "preparation key belongs to different input versions"
            )
        return cast(
            dict[str, JsonValue],
            asdict(read_resource(session, user_id=user_id, identifier=identity, version=1)),
        )
    variables = [
        item
        for item in data.variables
        if item.name == "frame"
        and item.standard_name in {"indicator_frame", "projection_pursuit_frame"}
        and item.data_type == "json"
    ]
    if (
        data.format != "JSON"
        or data.type != "json"
        or data.quality.get("validated") is not True
        or len(variables) != 1
    ):
        raise ConstraintError(
            "select validated indicator observations or prepared raster observations"
        )
    raster_observations = variables[0].standard_name == "projection_pursuit_frame"
    if raster_observations and framework.spatial_support != "grid":
        raise ConstraintError("raster cells require a grid indicator framework")
    if not raster_observations and variables[0].spatial_support != framework.spatial_support:
        raise ConstraintError("framework and observations have different spatial supports")
    size = data.quality.get("size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= 16_777_216:
        raise ConstraintError("indicator input exceeds 16 MiB")
    content = stored_content(request, session, data)
    document = json.loads(content)
    if not isinstance(document, dict) or "frame" not in document:
        raise ConstraintError("stored observations lack an indicator frame")
    observations: IndicatorFrame | ProjectionFrame = (
        ProjectionFrame.model_validate(document["frame"])
        if raster_observations
        else IndicatorFrame.model_validate(document["frame"])
    )
    derived = apply_framework(framework, observations)
    payload = json.dumps(
        {
            "frame": derived.model_dump(mode="json"),
            "framework": {"id": identifier, "version": framework.version},
            "observations": body.data.model_dump(mode="json"),
            "weight_method": framework.indicators[0].weight_method,
            "locations": observations.model_dump(mode="json").get("locations"),
            "observation_scope": data.quality.get("scope"),
        },
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
    ).encode()
    digest = hashlib.sha256(payload).hexdigest()
    prepared = data.model_copy(
        update={
            "id": identity,
            "version": 1,
            "name": framework.name[:230] + " / prepared indicators",
            "checksum": digest,
            "quality": {},
            "variables": (
                variables[0].model_copy(
                    update={
                        "standard_name": "indicator_frame",
                        "spatial_support": framework.spatial_support,
                        "description": (
                            "Indicators derived from explicit framework formulas "
                            "and source observations"
                        ),
                    }
                ),
            ),
        }
    )
    report = inspect_isolated(payload, prepared)
    require_permission(session, user_id, record.project_id, "write")
    stored = artifact_store(request).put(f"{record.project_id}/data/{identity}/{digest}", payload)
    prepared = prepared.model_copy(
        update={
            "uri": stored.uri,
            "quality": {
                **data.quality,
                **report.metadata,
                "source_values": "raw_before_model_standardization",
                "framework_id": identifier,
                "framework_version": framework.version,
                "weight_method": framework.indicators[0].weight_method,
            },
        }
    )
    revision = create_resource(
        session,
        user_id=user_id,
        project_id=record.project_id,
        kind="data",
        identifier=identity,
        name=prepared.name,
        spec=prepared.model_dump(mode="json"),
    )
    add_dependencies(session, identity, 1, references)
    session.commit()
    return cast(dict[str, JsonValue], asdict(revision))


class FrameworkPlanRequest(Contract):
    framework_version: Version
    data: VersionReference
    scene: VersionReference
    assessment_method: Literal["composite", "topsis"] = "composite"
    idempotency_key: Name


@router.post("/{identifier}/plan", status_code=201)
def plan_assessment(
    identifier: str,
    body: FrameworkPlanRequest,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
) -> dict[str, JsonValue]:
    record = resource_in_project(session, user_id, identifier, "indicator_framework")
    require_permission(session, user_id, record.project_id, "write")
    resource_in_project(session, user_id, body.data.id, "data", record.project_id)
    dependency = session.get(
        ResourceDependency, (body.data.id, body.data.version, identifier, body.framework_version)
    )
    if dependency is None:
        raise CoastMASError(
            "DEPENDENCY_CONFLICT", "selected file was not prepared by this framework version"
        )
    framework = IndicatorFrameworkSpec.model_validate(
        read_resource(
            session, user_id=user_id, identifier=identifier, version=body.framework_version
        ).spec
    )
    data = data_resource(body.data.id, session, user_id, body.data.version)
    document = json.loads(stored_content(request, session, data))
    observations = IndicatorFrame.model_validate(document["frame"])
    temporal = observations.years is not None and len(observations.years) > 1
    goal = ManagementGoal(
        original_text=f"Indicator framework {identifier} v{body.framework_version}",
        template="temporal_change" if temporal else "sustainability",
        weight_method=framework.indicators[0].weight_method,
        assessment_method=body.assessment_method,
    )
    return create_plan(
        PlanRequest(
            project_id=record.project_id,
            scene=body.scene,
            goal=goal,
            selected_data={"normalize.frame": body.data},
            allow_external=False,
        ),
        request,
        session,
        user_id,
        body.idempotency_key,
    )
