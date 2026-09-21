"""Recheck research snapshots and current scope without treating candidates as runs."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from coastmas.core.contracts import DataAssetSpec, ModelSpec, SceneSpec
from coastmas.core.errors import ConstraintError
from coastmas.core.research_planning import ResearchManifest
from coastmas.persistence.data_access import require_project_object
from coastmas.persistence.resources import fingerprint, read_resource, require_permission
from coastmas.persistence.schema import Resource


def verify_research_inputs(
    session: Session, user: str, project: str, manifest: ResearchManifest
) -> None:
    require_permission(session, user, project, "write")
    for case in manifest.cases:
        objects: tuple[SceneSpec | ModelSpec | DataAssetSpec, ...] = (
            case.scene,
            *case.models,
            *case.assets,
        )
        for item in objects:
            record = session.scalar(
                select(Resource)
                .where(Resource.id == item.id)
                .execution_options(populate_existing=True)
            )
            if (
                record is None
                or record.project_id != project
                or record.archived
                or not record.enabled
            ):
                raise ConstraintError("research input is not an active resource in this project")
            if isinstance(item, DataAssetSpec):
                require_project_object(item.uri, project)
            revision = read_resource(
                session, user_id=user, identifier=item.id, version=item.version
            )
            normalized = type(item).model_validate(revision.spec).model_dump(mode="json")
            if fingerprint(normalized) != fingerprint(item.model_dump(mode="json")):
                raise ConstraintError("research input differs from immutable resource version")
