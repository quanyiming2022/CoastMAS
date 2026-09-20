"""Project-scoped, bounded spatial queries over versioned geographic entities."""

import json
from typing import Annotated

from fastapi import APIRouter, Query, Response
from pydantic import AwareDatetime, JsonValue
from sqlalchemy import text

from coastmas.app.dependencies import CurrentUser, DatabaseSession
from coastmas.core.errors import CoastMASError
from coastmas.persistence.resources import require_permission

router = APIRouter(prefix="/api/v1/entities", tags=["geography"])


@router.get("/spatial")
def spatial_query(
    project_id: str,
    response: Response,
    session: DatabaseSession,
    user_id: CurrentUser,
    west: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
    south: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
    east: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
    north: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
    at: AwareDatetime | None = None,
    include_history: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, JsonValue]:
    require_permission(session, user_id, project_id, "read")
    if west >= east or south >= north:
        raise CoastMASError("VALIDATION_ERROR", "query bounds must have positive width and height")
    conditions = """
      r.project_id=:project AND r.kind='entity' AND NOT r.archived AND r.enabled
      AND ST_Intersects(g.geometry,ST_MakeEnvelope(:west,:south,:east,:north,4326))
    """
    if not include_history:
        conditions += " AND g.version=r.current_version"
    if at is not None:
        conditions += " AND g.valid_from <= :at AND (g.valid_to IS NULL OR :at < g.valid_to)"
    # Only fixed application clauses are interpolated; every request value is bound.
    rows = (
        session.execute(
            text(
                """
        SELECT g.resource_id,g.version,ST_AsGeoJSON(g.geometry,15) AS geometry,v.spec
        FROM geographic_entities g JOIN resources r ON r.id=g.resource_id
        JOIN resource_versions v ON v.resource_id=g.resource_id AND v.version=g.version
        WHERE """
                + conditions
                + " ORDER BY g.resource_id,g.version LIMIT :limit OFFSET :offset"
            ),
            {
                "project": project_id,
                "west": west,
                "south": south,
                "east": east,
                "north": north,
                "at": at,
                "limit": limit + 1,
                "offset": offset,
            },
        )
        .mappings()
        .all()
    )
    features: list[JsonValue] = [
        {
            "type": "Feature",
            "id": row["resource_id"],
            "geometry": json.loads(row["geometry"]),
            "properties": {
                **row["spec"]["properties"],
                "entity_id": row["resource_id"],
                "version": row["version"],
                "name": row["spec"]["name"],
                "type": row["spec"]["type"],
                "management_unit_id": row["spec"].get("management_unit_id"),
                "source_crs": row["spec"]["crs"],
                "valid_from": row["spec"]["valid_from"],
                "valid_to": row["spec"]["valid_to"],
            },
        }
        for row in rows[:limit]
    ]
    response.headers["Cache-Control"] = "no-store"
    return {
        "type": "FeatureCollection",
        "features": features,
        "has_more": len(rows) > limit,
        "offset": offset,
    }
