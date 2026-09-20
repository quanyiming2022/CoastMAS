"""Load pinned scene references without trusting client-provided entity or data metadata."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from coastmas.core.contracts import DataAssetSpec, SceneSpec
from coastmas.core.errors import CoastMASError
from coastmas.core.geography import GeographicEntity
from coastmas.persistence.resources import read_resource, require_permission
from coastmas.persistence.schema import Resource


def scene_resources(
    session: Session, user: str, project: str, scene: SceneSpec
) -> tuple[list[DataAssetSpec], list[GeographicEntity]]:
    require_permission(session, user, project, "read")
    assets: list[DataAssetSpec] = []
    entities: list[GeographicEntity] = []
    references = [(reference, "data") for reference in scene.data_references]
    references.extend((reference, "entity") for reference in scene.entity_references)
    for reference, kind in sorted(references, key=lambda item: (item[0].id, item[0].version)):
        resource = session.scalar(
            select(Resource)
            .where(Resource.id == reference.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            resource is None
            or resource.project_id != project
            or resource.kind != kind
            or resource.archived
            or not resource.enabled
        ):
            raise CoastMASError(
                "AUTHORIZATION_ERROR", "scene reference unavailable in this project"
            )
        spec = read_resource(
            session, user_id=user, identifier=reference.id, version=reference.version
        ).spec
        if kind == "entity":
            entities.append(GeographicEntity.model_validate(spec))
        else:
            assets.append(DataAssetSpec.model_validate(spec))
    return assets, entities
