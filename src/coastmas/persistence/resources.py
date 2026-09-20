"""Resource updates append revisions inside the caller's database transaction."""

import hashlib
import json
from dataclasses import dataclass
from uuid import uuid4

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from coastmas.core.contracts import WorkflowSpec
from coastmas.core.errors import CoastMASError
from coastmas.core.geography import GeographicEntity
from coastmas.persistence.geography import materialize_entity
from coastmas.persistence.schema import (
    AuditLog,
    Membership,
    Resource,
    ResourceDependency,
    ResourceVersion,
    User,
)

KINDS = {
    "model",
    "data",
    "entity",
    "scene",
    "workflow",
    "binding",
    "indicator_framework",
    "assessment",
    "proposal",
    "experiment",
    "graph_node",
    "graph_edge",
}


@dataclass(frozen=True)
class Revision:
    resource_id: str
    version: int
    spec: dict[str, JsonValue]
    checksum: str


def require_permission(
    session: Session, user_id: str, project_id: str, action: str, published: bool = False
) -> None:
    user = session.scalar(
        select(User).where(User.id == user_id).execution_options(populate_existing=True)
    )
    if user is None or not user.active:
        raise CoastMASError("AUTHORIZATION_ERROR", "permission denied")
    if user.is_admin:
        return
    member = session.scalar(
        select(Membership)
        .where(Membership.project_id == project_id, Membership.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    allowed = {
        "read": {"ADMIN", "RESEARCHER", "MANAGER", "VIEWER"},
        "write": {"ADMIN", "RESEARCHER", "MANAGER"},
        "publish": {"ADMIN", "MANAGER"},
        "admin": {"ADMIN"},
    }
    if member is not None:
        if member.role in allowed.get(action, set()):
            return
        if member.role == "PUBLIC" and action == "read" and published:
            return
    raise CoastMASError("AUTHORIZATION_ERROR", "permission denied")


def fingerprint(spec: dict[str, JsonValue]) -> str:
    content = json.dumps(
        spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    return hashlib.sha256(content).hexdigest()


def workflow_references(
    session: Session, *, project_id: str, kind: str, spec: dict[str, JsonValue]
) -> list[tuple[str, int]]:
    if kind != "workflow":
        return []
    workflow = WorkflowSpec.model_validate(spec)
    references = {(node.model_id, node.model_version, "model") for node in workflow.nodes}
    references.update(
        (binding.source.id, binding.source.version, "data") for binding in workflow.input_bindings
    )
    for identifier, version, expected_kind in sorted(references):
        resource = session.scalar(
            select(Resource)
            .where(Resource.id == identifier)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        revision = session.get(ResourceVersion, (identifier, version))
        if (
            resource is None
            or revision is None
            or resource.project_id != project_id
            or resource.kind != expected_kind
            or resource.archived
            or not resource.enabled
        ):
            raise CoastMASError(
                "DEPENDENCY_CONFLICT", "workflow reference is unavailable in this project"
            )
    return sorted({(identifier, version) for identifier, version, _ in references})


def add_dependencies(
    session: Session, identifier: str, version: int, references: list[tuple[str, int]]
) -> None:
    for target, target_version in references:
        session.add(
            ResourceDependency(
                source_id=identifier,
                source_version=version,
                target_id=target,
                target_version=target_version,
            )
        )
    session.flush()


def create_resource(
    session: Session,
    *,
    user_id: str,
    project_id: str,
    kind: str,
    identifier: str,
    name: str,
    spec: dict[str, JsonValue],
) -> Revision:
    require_permission(session, user_id, project_id, "write")
    if kind not in KINDS or spec.get("id") != identifier or spec.get("version") != 1:
        raise CoastMASError(
            "VALIDATION_ERROR", "invalid resource identity, kind or initial version"
        )
    if session.get(Resource, identifier) is not None:
        raise CoastMASError("VERSION_CONFLICT", "resource identity conflict")
    enabled = spec.get("enabled", True) if kind == "model" else True
    if not isinstance(enabled, bool):
        raise CoastMASError("VALIDATION_ERROR", "enabled must be boolean")
    references = workflow_references(session, project_id=project_id, kind=kind, spec=spec)
    checksum = fingerprint(spec)
    session.add(
        Resource(
            id=identifier,
            project_id=project_id,
            kind=kind,
            name=name,
            owner_id=user_id,
            current_version=1,
            enabled=enabled,
        )
    )
    session.flush()
    session.add(
        ResourceVersion(
            resource_id=identifier, version=1, spec=spec, checksum=checksum, created_by=user_id
        )
    )
    session.add(
        AuditLog(
            id=str(uuid4()),
            who=user_id,
            action="CREATE",
            resource=identifier,
            old_value=None,
            new_value={"version": 1, "checksum": checksum},
        )
    )
    session.flush()
    add_dependencies(session, identifier, 1, references)
    if kind == "entity":
        materialize_entity(session, GeographicEntity.model_validate(spec))
    return Revision(identifier, 1, spec, checksum)


def read_resource(
    session: Session, *, user_id: str, identifier: str, version: int | None = None
) -> Revision:
    resource = session.scalar(
        select(Resource).where(Resource.id == identifier).execution_options(populate_existing=True)
    )
    if resource is None:
        raise CoastMASError("AUTHORIZATION_ERROR", "permission denied or resource unavailable")
    require_permission(session, user_id, resource.project_id, "read", resource.published)
    revision = session.get(ResourceVersion, (identifier, version or resource.current_version))
    if revision is None:
        raise CoastMASError("NOT_FOUND", "resource version unavailable")
    # Detach nested JSON so a caller cannot mutate a cached ORM identity value.
    spec: dict[str, JsonValue] = json.loads(json.dumps(revision.spec, allow_nan=False))
    if fingerprint(spec) != revision.checksum:
        raise CoastMASError("CHECKSUM_ERROR", "resource revision integrity check failed")
    return Revision(identifier, revision.version, spec, revision.checksum)


def update_resource(
    session: Session,
    *,
    user_id: str,
    identifier: str,
    expected_version: int,
    spec: dict[str, JsonValue],
) -> Revision:
    resource = session.scalar(
        select(Resource)
        .where(Resource.id == identifier)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if resource is None:
        raise CoastMASError("AUTHORIZATION_ERROR", "permission denied or resource unavailable")
    require_permission(session, user_id, resource.project_id, "write")
    if resource.archived:
        raise CoastMASError("RESOURCE_ARCHIVED", "archived resource cannot be edited")
    if resource.current_version != expected_version:
        raise CoastMASError("VERSION_CONFLICT", "version conflict; reload current revision")
    next_version = expected_version + 1
    if spec.get("id") != identifier or spec.get("version") != next_version:
        raise CoastMASError("VALIDATION_ERROR", "revision identity or version invalid")
    enabled = spec.get("enabled", resource.enabled)
    if resource.kind == "model" and not isinstance(enabled, bool):
        raise CoastMASError("VALIDATION_ERROR", "enabled must be boolean")
    references = workflow_references(
        session, project_id=resource.project_id, kind=resource.kind, spec=spec
    )
    checksum = fingerprint(spec)
    session.add(
        ResourceVersion(
            resource_id=identifier,
            version=next_version,
            spec=spec,
            checksum=checksum,
            created_by=user_id,
        )
    )
    resource.current_version = next_version
    name = spec.get("name")
    if isinstance(name, str):
        resource.name = name
    if resource.kind == "model" and isinstance(enabled, bool):
        resource.enabled = enabled
    session.add(
        AuditLog(
            id=str(uuid4()),
            who=user_id,
            action="UPDATE",
            resource=identifier,
            old_value={"version": expected_version},
            new_value={"version": next_version, "checksum": checksum},
        )
    )
    session.flush()
    add_dependencies(session, identifier, next_version, references)
    if resource.kind == "entity":
        materialize_entity(session, GeographicEntity.model_validate(spec))
    return Revision(identifier, next_version, spec, checksum)
