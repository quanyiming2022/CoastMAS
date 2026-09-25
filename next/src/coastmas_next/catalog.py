"""Project catalog and actor-private view preferences; no analysis mutation."""

from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import Field
from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    Integer,
    Table,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from .contracts import Contract
from .intake import Intake
from .resource_catalog import CatalogQuery, list_assets
from .store import Problem, metadata

view_states = Table(
    "personal_view_states",
    metadata,
    Column("project_id", ForeignKey("projects.id"), primary_key=True),
    Column("actor", ForeignKey("accounts.id"), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("state", JSON, nullable=False),
)


task_view_states = Table(
    "task_view_states",
    metadata,
    Column("task_id", ForeignKey("tasks.id"), primary_key=True),
    Column("actor", ForeignKey("accounts.id"), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("state", JSON, nullable=False),
)


job_view_states = Table(
    "job_view_states",
    metadata,
    Column("job_id", ForeignKey("jobs.id"), primary_key=True),
    Column("actor", ForeignKey("accounts.id"), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("state", JSON, nullable=False),
)


class Camera(Contract):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-85.05112878, le=85.05112878)
    zoom: float = Field(ge=0, le=22)


class MapLayerState(Contract):
    artifact_id: str
    visible: bool = True
    opacity: float = Field(default=0.9, ge=0, le=1)


class ViewState(Contract):
    vector_present: bool | None = None
    selected_feature_id: str | None = Field(default=None, max_length=1000)
    legend_visible: bool | None = None
    layers: list[MapLayerState] | None = Field(default=None, max_length=256)
    artifact_id: str | None = None
    asset_id: str | None = None
    band: int = Field(default=1, ge=1)
    camera: Camera | None = None
    visible: bool = True
    opacity: float = Field(default=0.9, ge=0, le=1)


class SaveView(Contract):
    expected_revision: int = Field(ge=0)
    state: ViewState


def router(store):
    routes = APIRouter()

    def context(c, actor, project=None, task=None, job=None):
        if job is not None:
            from .execution import Execution

            record = Execution(store).read_job(actor, job, connection=c)
            return job_view_states, {"job_id": job, "actor": actor}, record["project_id"], None
        if task is not None:
            record = store.task(actor, task, connection=c)
            return task_view_states, {"task_id": task, "actor": actor}, record["project_id"], record
        store.permission(c, actor, project)
        return view_states, {"project_id": project, "actor": actor}, project, None

    def read(c, table, key):
        row = c.execute(select(table).filter_by(**key)).mappings().first()
        return (
            {"revision": row["revision"], "state": row["state"]}
            if row
            else {"revision": 0, "state": None}
        )

    def save_view(actor, body, *, project=None, task=None, job=None):
        state = body.state.model_dump(mode="json")
        if state["vector_present"] is None:
            state.pop("vector_present")
        if state["selected_feature_id"] is None:
            state.pop("selected_feature_id")
        if state["legend_visible"] is None:
            state.pop("legend_visible")
        if state["layers"] is None:
            state.pop("layers")
        if state["artifact_id"] is None:
            state.pop("artifact_id")
        with store.engine.begin() as c:
            table, key, project, record = context(c, actor, project, task, job)
            if state.get("artifact_id") is not None or "layers" in state:
                if job is None:
                    raise Problem(422, "RESULT_VIEW", "成果图层必须归属固定运行")
                from .outputs import owned_result

                _, output, _ = owned_result(store, actor, job)
                files = output["data"].get("files", [])
                identifiers = {str(i) for i in range(len(files))}
                if state.get("artifact_id") is not None and state["artifact_id"] not in identifiers:
                    raise Problem(422, "RESULT_VIEW", "成果图层不属于本次运行")
                layer_ids = [layer["artifact_id"] for layer in state.get("layers", [])]
                if len(set(layer_ids)) != len(layer_ids) or any(
                    identifier not in identifiers for identifier in layer_ids
                ):
                    raise Problem(422, "RESULT_VIEW", "图层重复或不属于本次固定运行")
            if "vector_present" in state and job is None:
                raise Problem(422, "RESULT_VIEW", "矢量成果显示状态必须属于固定运行")
            if state.get("selected_feature_id") is not None:
                if job is None:
                    raise Problem(422, "RESULT_FEATURE", "成果要素选择必须属于固定运行")
                from .outputs import owned_result

                _, result, _ = owned_result(store, actor, job)
                collection = result["data"].get("spatial_result", {})
                if state["selected_feature_id"] not in {
                    str(f["id"]) for f in collection.get("features", [])
                }:
                    raise Problem(422, "RESULT_FEATURE", "此要素不属于本次运行")
            if job is not None and state["asset_id"] is not None:
                raise Problem(422, "RESULT_VIEW", "成果视图不能切换成输入资料")
            if state["asset_id"]:
                asset = Intake(store).read_asset(actor, state["asset_id"], c)
                if asset["project_id"] != project:
                    raise Problem(422, "VIEW_PROJECT", "视图资料必须属于当前项目")
                if record is not None and state["asset_id"] not in {
                    ref["asset_id"] for ref in record["draft"]["selection"]
                }:
                    raise Problem(
                        422, "VIEW_SELECTION", "资料不在当前任务中；查看不自动改变分析选择"
                    )
                if asset["facts"]["profile"] in {"geotiff", "cog"} and state["band"] > len(
                    asset["facts"]["layers"][0]["fields"]
                ):
                    raise Problem(422, "BAND_UNAVAILABLE", "所选波段不存在")
            try:
                with c.begin_nested():
                    if body.expected_revision == 0:
                        c.execute(insert(table).values(**key, revision=1, state=state))
                    else:
                        changed = c.execute(
                            update(table)
                            .filter_by(**key)
                            .where(table.c.revision == body.expected_revision)
                            .values(revision=body.expected_revision + 1, state=state)
                        ).rowcount
                        if changed != 1:
                            raise Problem(
                                409, "VIEW_CONFLICT", "另一窗口已更新个人视图，请核对服务器版本"
                            )
            except IntegrityError as exc:
                raise Problem(
                    409, "VIEW_CONFLICT", "另一窗口已更新个人视图，请核对服务器版本"
                ) from exc
            return read(c, table, key)

    @routes.get("/api/projects/{project}/catalog")
    def catalog(
        project: str,
        request: Request,
        query: str = Query("", max_length=200),
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        sort: Literal["newest", "name", "size"] = "newest",
        state: Literal["active", "recycled"] = "active",
        profile: str = Query("", max_length=40),
    ):
        with store.engine.connect() as c:
            store.permission(c, request.state.actor["id"], project)
            return list_assets(
                c,
                project,
                CatalogQuery(query=query, sort=sort, state=state, profile=profile),
                offset,
                limit,
            )

    @routes.get("/api/projects/{project}/view-state")
    def current(project: str, request: Request):
        with store.engine.connect() as c:
            table, key, _, _ = context(c, request.state.actor["id"], project=project)
            return read(c, table, key)

    @routes.put("/api/projects/{project}/view-state")
    def save(project: str, body: SaveView, request: Request):
        return save_view(request.state.actor["id"], body, project=project)

    @routes.get("/api/tasks/{task}/view-state")
    def current_task(task: str, request: Request):
        with store.engine.connect() as c:
            table, key, _, _ = context(c, request.state.actor["id"], task=task)
            return read(c, table, key)

    @routes.put("/api/tasks/{task}/view-state")
    def save_task_view(task: str, body: SaveView, request: Request):
        return save_view(request.state.actor["id"], body, task=task)

    @routes.get("/api/tasks/{task}/assets")
    def selected_assets(task: str, request: Request):
        actor = request.state.actor["id"]
        with store.engine.connect() as c:
            record = store.task(actor, task, connection=c)
            return [
                Intake(store).read_asset(actor, ref["asset_id"], c)
                for ref in record["draft"]["selection"]
            ]

    @routes.get("/api/jobs/{job}/view-state")
    def current_job(job: str, request: Request):
        with store.engine.connect() as c:
            table, key, _, _ = context(c, request.state.actor["id"], job=job)
            return read(c, table, key)

    @routes.put("/api/jobs/{job}/view-state")
    def save_job_view(job: str, body: SaveView, request: Request):
        return save_view(request.state.actor["id"], body, job=job)

    return routes
