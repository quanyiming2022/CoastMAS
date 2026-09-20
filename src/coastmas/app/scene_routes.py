"""Read-only scene draft inspection against authorized immutable resource versions."""

from fastapi import APIRouter, Response

from coastmas.app.dependencies import CurrentUser, DatabaseSession
from coastmas.core.contracts import Contract, Name, SceneSpec
from coastmas.core.scene_workspace import SceneInspection, inspect_scene
from coastmas.persistence.scenes import scene_resources

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
