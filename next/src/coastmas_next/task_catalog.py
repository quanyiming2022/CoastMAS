"""Task management queries use the whole authorized collection, not loaded UI rows."""

from typing import Literal

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from .contracts import Purpose
from .store import tasks


def router(store):
    routes = APIRouter()

    @routes.get("/api/projects/{project}/task-catalog")
    def listing(
        project: str,
        request: Request,
        query: str = Query("", max_length=200),
        purpose: Purpose | None = None,
        sort: Literal["updated", "name"] = "updated",
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        with store.engine.connect() as c:
            store.permission(c, request.state.actor["id"], project)
            conditions = [tasks.c.project_id == project]
            title = tasks.c.draft["title"].as_string()
            if query:
                conditions.append(func.lower(title).contains(query.lower(), autoescape=True))
            if purpose:
                conditions.append(tasks.c.draft["purpose"].as_string() == purpose)
            total = c.scalar(select(func.count()).select_from(tasks).where(*conditions))
            order = title.asc() if sort == "name" else tasks.c.updated.desc()
            rows = c.execute(
                select(tasks)
                .where(*conditions)
                .order_by(order, tasks.c.id)
                .offset(offset)
                .limit(limit)
            ).mappings()
            return {
                "items": [dict(row) for row in rows],
                "total": total,
                "offset": offset,
                "limit": limit,
            }

    return routes
