"""Prepare immutable temporal inputs and a normal, permission-checked workflow."""

import hashlib
import json
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Request
from pydantic import JsonValue

from coastmas.app.dependencies import CurrentUser, DatabaseSession, artifact_store
from coastmas.app.run_routes import lock_submission, resource_in_project
from coastmas.core.contracts import (
    Contract,
    DataAssetSpec,
    ModelSpec,
    Name,
    SceneSpec,
    VersionReference,
    WorkflowSpec,
)
from coastmas.core.data_inspection import inspect_data
from coastmas.core.errors import CoastMASError, ConstraintError
from coastmas.core.execution import ExecutionRegistry
from coastmas.core.temporal_adaptation import TemporalRequest, adapt_time_series
from coastmas.core.validation import validate_workflow
from coastmas.domain.adaptation_catalog import adaptation_catalog
from coastmas.persistence.resources import (
    add_dependencies,
    create_resource,
    fingerprint,
    read_resource,
    require_permission,
)
from coastmas.persistence.schema import Resource

router = APIRouter(prefix="/api/v1/adaptations", tags=["adaptation"])


class SaveTemporalRequest(Contract):
    project_id: Name
    name: Name
    scene: VersionReference
    source: Name
    license: Name
    request: TemporalRequest
    idempotency_key: Name


@router.post("/temporal", status_code=201)
def prepare_temporal(
    body: SaveTemporalRequest, request: Request, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    require_permission(session, user_id, body.project_id, "write")
    lock_submission(session, body.project_id, user_id, "temporal:" + body.idempotency_key)
    base = str(
        uuid5(
            NAMESPACE_URL,
            json.dumps(["coastmas:temporal", body.project_id, user_id, body.idempotency_key]),
        )
    )
    identities = {
        kind: str(uuid5(NAMESPACE_URL, base + ":" + kind)) for kind in ("data", "scene", "workflow")
    }
    references: dict[str, JsonValue] = {
        kind: {"id": identifier, "version": 1} for kind, identifier in identities.items()
    }
    checksum = fingerprint(body.model_dump(mode="json"))
    if session.get(Resource, identities["data"]) is not None:
        old = DataAssetSpec.model_validate(
            read_resource(session, user_id=user_id, identifier=identities["data"], version=1).spec
        )
        if old.quality.get("preparation_checksum") != checksum:
            raise CoastMASError("IDEMPOTENCY_CONFLICT", "temporal key has different inputs")
        for kind in ("scene", "workflow"):
            resource_in_project(session, user_id, identities[kind], kind, body.project_id)
        return references
    resource_in_project(session, user_id, body.scene.id, "scene", body.project_id)
    original = SceneSpec.model_validate(
        read_resource(
            session, user_id=user_id, identifier=body.scene.id, version=body.scene.version
        ).spec
    )
    try:
        checked = adapt_time_series(body.request)
    except (ValueError, OverflowError) as exc:
        raise ConstraintError(str(exc)) from exc
    # Serialize fixed builtin registration across users and preparation keys.
    lock_submission(session, body.project_id, "builtin-registry", "temporal_adaptation")
    model = adaptation_catalog(body.project_id).models[0]
    if session.get(Resource, model.id) is None:
        create_resource(
            session,
            user_id=user_id,
            project_id=body.project_id,
            kind="model",
            identifier=model.id,
            name=model.name,
            spec=model.model_dump(mode="json"),
        )
    else:
        resource_in_project(session, user_id, model.id, "model", body.project_id)
        model = ModelSpec.model_validate(
            read_resource(session, user_id=user_id, identifier=model.id).spec
        )
    cast(ExecutionRegistry, request.app.state.registry).resolve(model)
    payload = json.dumps(
        {"request": body.request.model_dump(mode="json")}, sort_keys=True, allow_nan=False
    ).encode()
    digest = hashlib.sha256(payload).hexdigest()
    store = artifact_store(request)
    key = f"{body.project_id}/data/{identities['data']}/{digest}"
    data = DataAssetSpec(
        id=identities["data"],
        name=body.name[:220] + " / 时间适配输入",
        version=1,
        type="json",
        format="JSON",
        uri=f"s3://{store.bucket}/{key}",
        checksum=digest,
        crs=None,
        vertical_datum=None,
        spatial_extent=None,
        time_start=body.request.observations[0].start,
        time_end=body.request.observations[-1].end,
        time_resolution="explicit_support",
        variables=model.inputs,
        quality={"size_bytes": len(payload), "preparation_checksum": checksum},
        source=body.source,
        license=body.license,
    )
    inspection = inspect_data(payload, data)
    data = data.model_copy(update={"quality": {**data.quality, **inspection.metadata}})
    derived = SceneSpec.model_validate(
        {
            **original.model_dump(mode="json"),
            "id": identities["scene"],
            "version": 1,
            "name": body.name[:220] + " / 时间适配场景",
            "management_goal": "时间适配：" + body.name[:220],
            "required_outputs": ["result"],
            "time_range": {"start": checked.start, "end": checked.end},
            "data_references": [references["data"]],
        }
    )
    graph = WorkflowSpec.model_validate(
        {
            "id": identities["workflow"],
            "version": 1,
            "name": body.name[:220] + " / 时间适配工作流",
            "scene_type": "temporal_adaptation",
            "nodes": [
                {
                    "id": "adapt",
                    "model_id": model.id,
                    "model_version": model.version,
                    "parameters": {},
                }
            ],
            "edges": [],
            "input_bindings": [
                {
                    "source": references["data"],
                    "target": {"node_id": "adapt", "variable": "request"},
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
            "execution_policy": {"timeout_seconds": 30, "max_retries": 0},
            "output_definition": [{"node_id": "adapt", "variable": "result"}],
        }
    )
    validation = validate_workflow(graph, [model], [data], derived)
    if not validation.valid:
        raise ConstraintError(
            "temporal workflow preflight rejected preparation",
            {
                "issues": [
                    {"code": issue.code, "message": issue.message} for issue in validation.issues
                ]
            },
        )
    graph = graph.model_copy(update={"input_bindings": validation.bindings})
    stored = store.put(key, payload)
    if stored.sha256 != digest:
        raise CoastMASError("CHECKSUM_ERROR", "temporal write differs from supplied bytes")
    for kind, spec in (("data", data), ("scene", derived), ("workflow", graph)):
        create_resource(
            session,
            user_id=user_id,
            project_id=body.project_id,
            kind=kind,
            identifier=spec.id,
            name=spec.name,
            spec=spec.model_dump(mode="json"),
        )
    add_dependencies(session, derived.id, 1, [(original.id, original.version)])
    session.commit()
    return references
