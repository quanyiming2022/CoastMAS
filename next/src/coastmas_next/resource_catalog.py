"""Revisioned catalog metadata and replayable, frozen soft-delete operations.

File facts and scientific revisions are immutable. Recycle is discoverability and
new-use state; historical authorized reads continue to resolve original bytes.
"""

import time
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field, model_validator
from sqlalchemy import (
    JSON,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    func,
    insert,
    or_,
    select,
    update,
)

from .contracts import Contract
from .intake import Intake, assets
from .store import Problem, audit_event, identifier, metadata, projects, tasks

asset_metadata = Table(
    "asset_metadata",
    metadata,
    Column("asset_id", ForeignKey("assets.id"), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("display_name", String, nullable=False),
    Column("description", String, nullable=False),
    Column("tags", JSON, nullable=False),
    Column("state", String, nullable=False),
    Column("updated", Float, nullable=False),
    Column("actor", ForeignKey("accounts.id"), nullable=False),
)
operations = Table(
    "catalog_operations",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", ForeignKey("projects.id"), nullable=False),
    Column("actor", ForeignKey("accounts.id"), nullable=False),
    Column("action", String, nullable=False),
    Column("selection", JSON, nullable=False),
    Column("created", Float, nullable=False),
    Column("expires", Float, nullable=False),
    Column("result", JSON),
)


class CatalogQuery(Contract):
    query: str = Field(default="", max_length=200)
    state: Literal["active", "recycled"] = "active"
    profile: str = Field(default="", max_length=40)
    sort: Literal["newest", "name", "size"] = "newest"


class MetadataEdit(Contract):
    expected_revision: int = Field(ge=0)
    display_name: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_text(self):
        self.display_name = self.display_name.strip()
        self.tags = list(dict.fromkeys(t.strip() for t in self.tags if t.strip()))
        if not self.display_name or any(len(t) > 80 for t in self.tags):
            raise ValueError("名称不能为空，标签不超过80字符")
        return self


class Selection(Contract):
    ids: list[str] | None = Field(default=None, min_length=1, max_length=1000)
    query: CatalogQuery | None = None
    excluded_ids: list[str] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.ids is None) == (self.query is None):
            raise ValueError("选择记录或冻结筛选全集，两者必选其一")
        if self.ids is not None and self.excluded_ids:
            raise ValueError("明确记录选择不能另设排除列表")
        return self


class Operation(Contract):
    action: Literal["recycle", "restore"]
    selection: Selection


def row_metadata(c, asset):
    row = (
        c.execute(select(asset_metadata).where(asset_metadata.c.asset_id == asset["id"]))
        .mappings()
        .first()
    )
    return (
        dict(row)
        if row
        else {
            "asset_id": asset["id"],
            "revision": 0,
            "display_name": asset["name"],
            "description": "",
            "tags": [],
            "state": "active",
            "updated": asset["created"],
        }
    )


def lock_asset(c, asset_id):
    # A harmless UPDATE also acquires the SQLite write lock; PG uses the same row
    # lock as enqueue. No file/scientific version is changed by metadata edits.
    c.execute(update(assets).where(assets.c.id == asset_id).values(revision=assets.c.revision))


def require_active(c, asset_id):
    lock_asset(c, asset_id)
    if (
        c.scalar(select(asset_metadata.c.state).where(asset_metadata.c.asset_id == asset_id))
        == "recycled"
    ):
        raise Problem(409, "RESOURCE_RECYCLED", "资料已在回收站，请先恢复再用于新的分析")


def catalog_statement(c, project, query):
    joined = assets.outerjoin(asset_metadata, assets.c.id == asset_metadata.c.asset_id)
    display = func.coalesce(asset_metadata.c.display_name, assets.c.name)
    conditions = [
        assets.c.project_id == project,
        func.coalesce(asset_metadata.c.state, "active") == query.state,
    ]
    if query.query:
        pattern = query.query.lower()
        tag_values = (func.json_each(asset_metadata.c.tags).table_valued("value")
                      if c.dialect.name == "sqlite" else
                      func.json_array_elements_text(asset_metadata.c.tags).table_valued("value").render_derived())
        tag_match = select(1).select_from(tag_values).where(
            func.lower(tag_values.c.value).contains(pattern, autoescape=True)).exists()
        conditions.append(
            or_(tag_match,
                *[
                    func.lower(col).contains(pattern, autoescape=True)
                    for col in [
                        assets.c.name,
                        display,
                        asset_metadata.c.description,
                        
                    ]
                ]
            )
        )
    if query.profile:
        conditions.append(assets.c.facts["profile"].as_string() == query.profile)
    ordering = {
        "newest": assets.c.created.desc(),
        "name": display.asc(),
        "size": assets.c.size.desc(),
    }[query.sort]
    return joined, conditions, ordering


def list_assets(c, project, query, offset, limit):
    joined, conditions, ordering = catalog_statement(c, project, query)
    total = c.scalar(select(func.count()).select_from(joined).where(*conditions))
    rows = c.execute(
        select(
            assets,
            func.coalesce(asset_metadata.c.display_name, assets.c.name).label("display_name"),
            func.coalesce(asset_metadata.c.revision, 0).label("metadata_revision"),
            func.coalesce(asset_metadata.c.state, "active").label("catalog_state"),
        )
        .select_from(joined)
        .where(*conditions)
        .order_by(ordering, assets.c.id)
        .offset(offset)
        .limit(limit)
    ).mappings()
    return {"items": [dict(row) for row in rows], "total": total, "offset": offset, "limit": limit}


class CatalogOperations:
    def __init__(self, store):
        self.store = store

    def authorize(self, c, actor, project):
        # Membership changes use this same lock, preventing a revoked role from
        # applying an operation after the final authorization check.
        c.execute(select(projects.c.id).where(projects.c.id == project).with_for_update()).first()
        self.store.permission(c, actor, project, write=True)

    def write_metadata(self, c, actor, asset, current, changes):
        values = {
            **current,
            **changes,
            "revision": current["revision"] + 1,
            "updated": time.time(),
            "actor": actor,
        }
        if current["revision"] == 0:
            c.execute(insert(asset_metadata).values(**values))
        else:
            c.execute(
                update(asset_metadata)
                .where(asset_metadata.c.asset_id == asset["id"])
                .values(**values)
            )
        return values

    def edit(self, actor, asset_id, body):
        with self.store.engine.begin() as c:
            asset = Intake(self.store).read_asset(actor, asset_id, c)
            self.authorize(c, actor, asset["project_id"])
            lock_asset(c, asset_id)
            current = row_metadata(c, asset)
            if current["revision"] != body.expected_revision:
                raise Problem(409, "METADATA_CONFLICT", "目录信息已改变，请读取最新版本后修改")
            if current["state"] != "active":
                raise Problem(409, "RESOURCE_RECYCLED", "请先恢复资料再修改目录信息")
            result = self.write_metadata(
                c, actor, asset, current, body.model_dump(exclude={"expected_revision"})
            )
            audit_event(c, actor, asset["project_id"], "edit_asset_metadata", asset_id)
            return result

    def references(self, c, project, asset_id):
        from .execution import jobs

        running = []
        for row in c.execute(
            select(jobs.c.id, jobs.c.manifest).where(
                jobs.c.project_id == project, jobs.c.status.in_(["queued", "running"])
            )
        ).mappings():
            if any(item["id"] == asset_id for item in row["manifest"].get("assets", [])):
                running.append(row["id"])
        drafts = sum(
            any(ref["asset_id"] == asset_id for ref in draft.get("selection", []))
            for draft in c.scalars(select(tasks.c.draft).where(tasks.c.project_id == project))
        )
        return {"active_runs": running, "task_references": drafts}

    def preview(self, actor, project, body):
        with self.store.engine.begin() as c:
            self.authorize(c, actor, project)
            selection = body.selection
            if selection.ids is not None:
                ids = list(dict.fromkeys(selection.ids))
            else:
                page = list_assets(c, project, selection.query, 0, 10001)
                if page["total"] > 10000:
                    raise Problem(
                        422, "SELECTION_BUDGET", "当前批量事务最多10000项，请缩小筛选；未截断选择"
                    )
                ids = [
                    item["id"] for item in page["items"] if item["id"] not in selection.excluded_ids
                ]
            snapshot = []
            for asset_id in ids:
                asset = Intake(self.store).read_asset(actor, asset_id, c)
                if asset["project_id"] != project:
                    raise Problem(404, "ASSET_UNAVAILABLE", "资料不可用")
                current = row_metadata(c, asset)
                snapshot.append(
                    {
                        "id": asset_id,
                        "revision": current["revision"],
                        "display_name": current["display_name"],
                        "state": current["state"],
                        "references": self.references(c, project, asset_id),
                    }
                )
            now = time.time()
            row = {
                "id": identifier(),
                "project_id": project,
                "actor": actor,
                "action": body.action,
                "selection": snapshot,
                "created": now,
                "expires": now + 600,
                "result": None,
            }
            c.execute(insert(operations).values(**row))
            return {
                "id": row["id"],
                "action": body.action,
                "total": len(snapshot),
                "items": snapshot,
                "expires": row["expires"],
            }

    def apply(self, actor, project, operation_id):
        with self.store.engine.begin() as c:
            self.authorize(c, actor, project)
            row = (
                c.execute(
                    select(operations)
                    .where(
                        operations.c.id == operation_id,
                        operations.c.project_id == project,
                        operations.c.actor == actor,
                    )
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if row is None:
                raise Problem(404, "OPERATION_UNAVAILABLE", "操作预检不可用")
            if row["result"] is not None:
                return row["result"]
            if row["expires"] < time.time():
                raise Problem(409, "OPERATION_EXPIRED", "操作预检已过期，请重新核对影响")
            results = []
            for selected in row["selection"]:
                try:
                    with c.begin_nested():
                        asset = Intake(self.store).read_asset(actor, selected["id"], c)
                        lock_asset(c, asset["id"])
                        current = row_metadata(c, asset)
                        if current["revision"] != selected["revision"]:
                            raise Problem(409, "METADATA_CONFLICT", "预检后信息已改变，未执行此项")
                        target = "recycled" if row["action"] == "recycle" else "active"
                        if current["state"] == target:
                            raise Problem(409, "RESOURCE_STATE", "当前状态不适用此操作")
                        if (
                            target == "recycled"
                            and self.references(c, project, asset["id"])["active_runs"]
                        ):
                            raise Problem(409, "RESOURCE_IN_USE", "运行正在引用资料，未回收")
                        self.write_metadata(c, actor, asset, current, {"state": target})
                        audit_event(c, actor, project, row["action"] + "_asset", asset["id"])
                        results.append({"id": asset["id"], "status": "applied"})
                except Problem as exc:
                    results.append(
                        {
                            "id": selected["id"],
                            "status": "blocked",
                            "code": exc.code,
                            "message": exc.message,
                        }
                    )
            result = {"id": operation_id, "action": row["action"], "items": results}
            c.execute(
                update(operations).where(operations.c.id == operation_id).values(result=result)
            )
            return result


def router(store):
    routes = APIRouter()
    service = CatalogOperations(store)

    @routes.get("/api/assets/{asset_id}/metadata")
    def read_metadata(asset_id: str, request: Request):
        with store.engine.connect() as c:
            return row_metadata(c, Intake(store).read_asset(request.state.actor["id"], asset_id, c))

    @routes.patch("/api/assets/{asset_id}/metadata")
    def edit(asset_id: str, body: MetadataEdit, request: Request):
        return service.edit(request.state.actor["id"], asset_id, body)

    @routes.post("/api/projects/{project}/catalog/operations", status_code=201)
    def preview(project: str, body: Operation, request: Request):
        return service.preview(request.state.actor["id"], project, body)

    @routes.post("/api/projects/{project}/catalog/operations/{operation_id}/apply")
    def apply(project: str, operation_id: str, request: Request):
        return service.apply(request.state.actor["id"], project, operation_id)

    return routes
