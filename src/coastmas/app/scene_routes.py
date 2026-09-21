"""Scene inspection and protected lifecycle for immutable resource versions."""

from fastapi import APIRouter, Response

from coastmas.app.dependencies import CurrentUser, DatabaseSession
from coastmas.core.contracts import Contract, Name, SceneSpec
from coastmas.core.errors import CoastMASError
from coastmas.core.scene_workspace import SceneInspection, inspect_scene
from coastmas.persistence.lifecycle import archive_resource
from coastmas.persistence.scenes import scene_resources
from coastmas.persistence.schema import Resource

router = APIRouter(prefix="/api/v1", tags=["scenes"])


class SceneDraft(Contract):
    project_id: Name
    scene: SceneSpec


@router.post("/scene-drafts/inspect")
def inspect_draft(
    body: SceneDraft, response: Response, session: DatabaseSession, user_id: CurrentUser
) -> SceneInspection:
    assets, entities = scene_resources(session, user_id, body.project_id, body.scene)
    response.headers["Cache-Control"] = "no-store"
    return inspect_scene(body.scene, assets, entities)


@router.delete("/scenes/{identifier}", status_code=204)
def archive_scene(identifier: str, session: DatabaseSession, user_id: CurrentUser) -> None:
    record = session.get(Resource, identifier)
    if record is None or record.kind != "scene":
        raise CoastMASError("NOT_FOUND", "scene unavailable")
    archive_resource(session, user_id=user_id, identifier=identifier)
    session.commit()
