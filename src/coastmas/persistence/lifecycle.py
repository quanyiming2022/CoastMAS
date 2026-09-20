"""Protected resource archive: historical versions and provenance are retained."""

from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from coastmas.core.errors import CoastMASError
from coastmas.persistence.resources import Revision, read_resource, require_permission
from coastmas.persistence.schema import AuditLog, Job, Resource, ResourceDependency, ResourceVersion


def resource_history(session: Session, *, user_id: str, identifier: str) -> list[Revision]:
    read_resource(session, user_id=user_id, identifier=identifier)
    versions = session.scalars(
        select(ResourceVersion.version)
        .where(ResourceVersion.resource_id == identifier)
        .order_by(ResourceVersion.version)
    )
    return [
        read_resource(session, user_id=user_id, identifier=identifier, version=version)
        for version in versions
    ]


def archive_resource(session: Session, *, user_id: str, identifier: str) -> None:
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
        return
    referenced = session.scalar(
        select(ResourceDependency.source_id)
        .where(ResourceDependency.target_id == identifier)
        .limit(1)
    )
    job = session.scalar(
        select(Job.id)
        .where(
            or_(
                Job.manifest.contains({"models": [{"id": identifier}]}),
                Job.manifest.contains({"data_assets": [{"id": identifier}]}),
                Job.manifest.contains({"workflow": {"id": identifier}}),
                Job.manifest.contains({"scene": {"id": identifier}}),
            )
        )
        .limit(1)
    )
    if referenced is not None or job is not None:
        raise CoastMASError(
            "DEPENDENCY_CONFLICT", "resource is referenced by a workflow or run; disable it instead"
        )
    resource.archived = True
    resource.enabled = False
    session.add(
        AuditLog(
            id=str(uuid4()),
            who=user_id,
            action="ARCHIVE",
            resource=identifier,
            old_value={"archived": False},
            new_value={"archived": True},
        )
    )
    session.flush()
