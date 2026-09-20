"""Knowledge graph views retain project visibility and immutable contract identity."""

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from coastmas.app.dependencies import CurrentUser, DatabaseSession
from coastmas.core.contracts import DataAssetSpec, ModelSpec, SceneSpec, WorkflowSpec
from coastmas.core.errors import CoastMASError
from coastmas.core.knowledge_graph import GraphSnapshot, KnowledgeGraphService
from coastmas.persistence.resources import read_resource, require_permission
from coastmas.persistence.schema import Resource

router = APIRouter(prefix="/api/v1/knowledge-graph", tags=["knowledge graph"])


@router.get("")
def explore_graph(
    project_id: str,
    response: Response,
    session: DatabaseSession,
    user_id: CurrentUser,
    focus: str | None = Query(default=None, max_length=256),
    depth: int = Query(default=2, ge=0, le=4),
) -> GraphSnapshot:
    require_permission(session, user_id, project_id, "read")
    resources = session.scalars(
        select(Resource)
        .where(
            Resource.project_id == project_id,
            Resource.kind.in_(("model", "data", "scene", "workflow")),
            Resource.archived.is_(False),
            Resource.enabled.is_(True),
        )
        .order_by(Resource.id)
        .limit(501)
    ).all()
    if len(resources) > 500:
        raise CoastMASError("CATALOG_LIMIT", "knowledge graph requires a narrower project catalog")
    models, assets, scenes, workflows = [], [], [], []
    for resource in resources:
        spec = read_resource(
            session, user_id=user_id, identifier=resource.id, version=resource.current_version
        ).spec
        if resource.kind == "model":
            models.append(ModelSpec.model_validate(spec))
        elif resource.kind == "data":
            assets.append(DataAssetSpec.model_validate(spec))
        elif resource.kind == "scene":
            scenes.append(SceneSpec.model_validate(spec))
        else:
            workflows.append(WorkflowSpec.model_validate(spec))
    try:
        graph = KnowledgeGraphService.from_catalog(
            models=tuple(models),
            assets=tuple(assets),
            scenes=tuple(scenes),
            workflows=tuple(workflows),
        )
    except ValueError as exc:
        raise CoastMASError("GRAPH_LIMIT", "knowledge graph exceeds supported bounds") from exc
    response.headers["Cache-Control"] = "no-store"
    if focus is None:
        return graph.snapshot
    if focus not in graph.graph:
        raise CoastMASError("NOT_FOUND", "knowledge graph node unavailable")
    return graph.neighborhood(focus, depth)
