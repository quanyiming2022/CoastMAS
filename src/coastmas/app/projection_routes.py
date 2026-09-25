"""Registration and explicit administrative approval of fixed provided-source runtimes."""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from fastapi import APIRouter
from pydantic import Field, JsonValue

from coastmas.app.dependencies import CurrentUser, DatabaseSession
from coastmas.core.contracts import Contract, ModelSpec, Name
from coastmas.core.errors import CoastMASError
from coastmas.domain.projection_catalog import (
    METHODS,
    Method,
    projection_model,
    release,
    verified_runtime,
)
from coastmas.persistence.resources import (
    create_resource,
    read_resource,
    require_permission,
    update_resource,
)
from coastmas.persistence.schema import AuditLog, Resource

router = APIRouter(prefix="/api/v1/models", tags=["models"])


class ProvidedModelRequest(Contract):
    project_id: Name
    method: Method


class ApproveProvidedRequest(Contract):
    expected_version: int = Field(strict=True, ge=1)


@router.get("/provided-packages")
def packages(
    project_id: str, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    require_permission(session, user_id, project_id, "read")
    can_register = True
    try:
        require_permission(session, user_id, project_id, "write")
    except CoastMASError:
        can_register = False
    can_approve = True
    try:
        require_permission(session, user_id, project_id, "admin")
    except CoastMASError:
        can_approve = False
    try:
        installed = release()
    except CoastMASError as exc:
        return {
            "available": False,
            "reason": exc.message,
            "can_approve": can_approve,
            "can_register": can_register,
            "models": [],
        }
    return {
        "available": True,
        "reason": None,
        "can_approve": can_approve,
        "can_register": can_register,
        "models": [
            {
                "method": method,
                "name": name,
                "license": license,
                "image": installed.image,
                "id": f"business:{project_id}:{method}",
                "registered": session.get(Resource, f"business:{project_id}:{method}") is not None,
            }
            for method, (name, license) in METHODS.items()
        ],
    }


@router.post("/provided-packages", status_code=201)
def register(
    body: ProvidedModelRequest, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    require_permission(session, user_id, body.project_id, "write")
    model = projection_model(body.project_id, body.method)
    revision = create_resource(
        session,
        user_id=user_id,
        project_id=body.project_id,
        kind="model",
        identifier=model.id,
        name=model.name,
        spec=model.model_dump(mode="json"),
    )
    session.commit()
    return cast(dict[str, JsonValue], asdict(revision))


@router.post("/{identifier}/approve-provided-runtime")
def approve(
    identifier: str, body: ApproveProvidedRequest, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    resource = session.get(Resource, identifier)
    if resource is None or resource.kind != "model":
        raise CoastMASError("NOT_FOUND", "model unavailable")
    require_permission(session, user_id, resource.project_id, "admin")
    if resource.current_version != body.expected_version:
        raise CoastMASError("VERSION_CONFLICT", "reload current model version")
    original = ModelSpec.model_validate(
        read_resource(session, user_id=user_id, identifier=identifier).spec
    )
    runtime = verified_runtime(original, allow_unapproved=True)
    updated = projection_model(
        resource.project_id, cast(Method, runtime.handler), approved=True
    ).model_copy(
        update={
            "version": original.version + 1,
            "enabled": original.enabled,
            "updated_at": datetime.now(UTC),
        }
    )
    revision = update_resource(
        session,
        user_id=user_id,
        identifier=identifier,
        expected_version=body.expected_version,
        spec=updated.model_dump(mode="json"),
    )
    session.add(
        AuditLog(
            id=uuid4().hex,
            who=user_id,
            action="APPROVE_PROVIDED_RUNTIME",
            resource=identifier,
            old_value={"version": original.version},
            new_value={"version": updated.version, **release().model_dump(mode="json")},
        )
    )
    session.commit()
    return cast(dict[str, JsonValue], asdict(revision))
