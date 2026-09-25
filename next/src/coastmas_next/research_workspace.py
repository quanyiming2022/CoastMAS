"""Actor-private research continuity and explicit, versioned scientific actions."""

import copy
import time
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import (
    JSON,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from .contracts import Contract, TaskDraft
from .execution import ExecuteRequest, Execution, fingerprint
from .intake import Intake
from .reuse import templates
from .store import Problem, audit_event, identifier, metadata

workspace_states = Table(
    "research_workspace_states",
    metadata,
    Column("project_id", ForeignKey("projects.id"), primary_key=True),
    Column("actor", ForeignKey("accounts.id"), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("state", JSON, nullable=False),
)
processing_nodes = Table(
    "processing_nodes",
    metadata,
    Column("id", String, primary_key=True),
    Column("task_id", ForeignKey("tasks.id"), nullable=False),
    Column("actor", ForeignKey("accounts.id"), nullable=False),
    Column("intent", String, nullable=False),
    Column("fingerprint", String, nullable=False),
    Column("draft", JSON, nullable=False),
    Column("created", Float, nullable=False),
    UniqueConstraint("task_id", "actor", "intent"),
)


class ResearchState(Contract):
    active_task_id: str | None = None
    inspected_asset_id: str | None = None
    viewed_job_id: str | None = None
    panel: Literal["research", "tasks", "data", "methods", "runs", "results", "tools"] = "research"
    central_view: Literal["map", "configuration", "result"] = "map"
    content_tab: Literal["layers", "inputs", "runs"] | None = None
    dock_heights: dict[str, int] | None = None
    drawer: Literal["closed", "open", "maximized"] = "closed"


class SaveResearch(Contract):
    expected_revision: int = Field(ge=0)
    state: ResearchState


class ApplyMethod(Contract):
    expected_revision: int = Field(ge=1)
    method_id: str
    method_revision: int = Field(ge=1)


class NewProcessingNode(Contract):
    expected_revision: int = Field(ge=1)
    operator: Literal["valid_mask", "align_grid", "ndvi", "score", "planning_units"]
    asset_id: str
    parameters: dict = Field(default_factory=dict)
    band: int = Field(default=1, ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


def read_node(c, store, actor, node_id, task_id=None):
    row = (
        c.execute(select(processing_nodes).where(processing_nodes.c.id == node_id))
        .mappings()
        .first()
    )
    if not row or (task_id is not None and row["task_id"] != task_id):
        raise Problem(404, "NODE_UNAVAILABLE", "处理节点不可用")
    store.task(actor, row["task_id"], write=True, connection=c)
    return dict(row)


def router(store):
    routes = APIRouter()

    @routes.get("/api/projects/{project}/workspace-state")
    def read(project: str, request: Request):
        actor = request.state.actor["id"]
        with store.engine.connect() as c:
            store.permission(c, actor, project)
            row = (
                c.execute(
                    select(workspace_states).where(
                        workspace_states.c.project_id == project, workspace_states.c.actor == actor
                    )
                )
                .mappings()
                .first()
            )
            if row:
                # Recheck referenced objects; permission changes never reuse a hidden cache.
                state = ResearchState.model_validate(row["state"])
                validate(c, actor, project, state)
                saved = state.model_dump()
                if saved["dock_heights"] is None:
                    saved.pop("dock_heights")
                if saved["content_tab"] is None:
                    saved.pop("content_tab")
                return {"revision": row["revision"], "state": saved}
            return {"revision": 0, "state": None}

    def validate(c, actor, project, state):
        if state.active_task_id:
            task = store.task(actor, state.active_task_id, connection=c)
            if task["project_id"] != project:
                raise Problem(404, "TASK_UNAVAILABLE", "任务不属于当前可访问项目")
        if state.inspected_asset_id:
            asset = Intake(store).read_asset(actor, state.inspected_asset_id, c)
            if asset["project_id"] != project:
                raise Problem(404, "ASSET_UNAVAILABLE", "资料不属于当前可访问项目")
        if state.viewed_job_id:
            job = Execution(store).read_job(actor, state.viewed_job_id, connection=c)
            if job["project_id"] != project or job["task_id"] != state.active_task_id:
                raise Problem(422, "RESULT_TASK", "所查看运行必须属于当前研究任务")

    @routes.put("/api/projects/{project}/workspace-state")
    def save(project: str, body: SaveResearch, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            store.permission(c, actor, project)
            validate(c, actor, project, body.state)
            state = body.state.model_dump(mode="json")
            if state["dock_heights"] is None:
                state.pop("dock_heights")
            if state["content_tab"] is None:
                state.pop("content_tab")
            try:
                if body.expected_revision == 0:
                    c.execute(
                        insert(workspace_states).values(
                            project_id=project, actor=actor, revision=1, state=state
                        )
                    )
                elif (
                    c.execute(
                        update(workspace_states)
                        .where(
                            workspace_states.c.project_id == project,
                            workspace_states.c.actor == actor,
                            workspace_states.c.revision == body.expected_revision,
                        )
                        .values(revision=body.expected_revision + 1, state=state)
                    ).rowcount
                    != 1
                ):
                    raise Problem(
                        409, "WORKSPACE_CONFLICT", "另一窗口已切换研究现场，请重新读取后继续"
                    )
            except IntegrityError as exc:
                raise Problem(409, "WORKSPACE_CONFLICT", "研究现场已有更新，请重新读取") from exc
            return {"revision": body.expected_revision + 1, "state": state}

    @routes.post("/api/tasks/{task_id}/apply-method")
    def apply(task_id: str, body: ApplyMethod, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            task = store.task(actor, task_id, write=True, connection=c)
            row = (
                c.execute(
                    select(templates).where(
                        templates.c.id == body.method_id,
                        templates.c.project_id == task["project_id"],
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise Problem(404, "METHOD_UNAVAILABLE", "方法不可用")
            from .method_library import method_version

            row = method_version(c, body.method_id, body.method_revision, approved=True)
            from .management_catalog import require_available

            require_available(c, "methods", row["id"])
            spec = row["spec"]
            config = spec["configuration"]
            if spec["purpose"] != "method" or config.get("task") != task["draft"]["purpose"]:
                raise Problem(422, "METHOD_TASK", "方法用途与当前研究不符，请以此方法新建适用任务")
            draft = copy.deepcopy(task["draft"])
            draft["method_id"] = row["id"]
            draft["options"]["method_revision"] = row["revision"]
            requirements = config.get("indicators", list(config.get("quantities", {}).values()))
            draft["options"]["indicator_requirements"] = requirements
            draft["options"]["processing_plan"] = [
                {"id": key, "name": name, "state": "needs_check"}
                for key, name in [
                    ("sources", "资料装配"),
                    ("spatial", "空间统一"),
                    ("spatialization", "统计空间化"),
                    ("indicators", "指标生产"),
                    ("normalization", "指标标准化"),
                    ("weights", "权重配置"),
                    ("synthesis", "综合计算"),
                    ("validation", "验证与交付"),
                ]
            ]
            saved = store.save_task(
                actor,
                task_id,
                body.expected_revision,
                TaskDraft.model_validate(draft).model_dump(mode="json"),
                c,
            )
            audit_event(c, actor, task["project_id"], "apply_method", row["id"])
            return saved

    @routes.get("/api/tasks/{task_id}/processing-nodes")
    def nodes(task_id: str, request: Request):
        with store.engine.connect() as c:
            store.task(request.state.actor["id"], task_id, connection=c)
            return [
                dict(row)
                for row in c.execute(
                    select(processing_nodes)
                    .where(processing_nodes.c.task_id == task_id)
                    .order_by(processing_nodes.c.created, processing_nodes.c.id)
                ).mappings()
            ]

    @routes.post("/api/tasks/{task_id}/processing-nodes", status_code=201)
    def create_node(task_id: str, body: NewProcessingNode, request: Request):
        actor = request.state.actor["id"]
        digest = fingerprint(body.model_dump(exclude={"expected_revision", "idempotency_key"}))
        with store.engine.begin() as c:
            task = store.task(actor, task_id, write=True, connection=c)
            existing = (
                c.execute(
                    select(processing_nodes).where(
                        processing_nodes.c.task_id == task_id,
                        processing_nodes.c.actor == actor,
                        processing_nodes.c.intent == body.idempotency_key,
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                if existing["fingerprint"] != digest:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT", "提交标识已用于另一处理配置")
                return dict(existing)
            if task["revision"] != body.expected_revision:
                raise Problem(409, "DRAFT_CONFLICT", "任务已更新，请核对当前输入")
            source = next(
                (ref for ref in task["draft"]["selection"] if ref["asset_id"] == body.asset_id),
                None,
            )
            if not source:
                from .stage_products import read_products

                product = next(
                    (
                        p
                        for p in read_products(c, store, actor, task)
                        if p["asset_id"] == body.asset_id and p["applicable"]
                    ),
                    None,
                )
                if product:
                    source = {"asset_id": product["asset_id"], "revision": 1, "layer": "raster"}
            if not source:
                raise Problem(422, "NODE_INPUT", "仅可处理本研究输入或仍适用的阶段产物")
            sources = [source]
            if body.operator == "planning_units":
                from .planning_units import validate_options

                validate_options(body.parameters)
            elif body.operator != "valid_mask":
                from .preparation import options as preparation_options

                parameters = preparation_options(body.operator, body.parameters)
                if body.operator == "align_grid" and parameters.reference_asset_id != body.asset_id:
                    reference = next(
                        (
                            ref
                            for ref in task["draft"]["selection"]
                            if ref["asset_id"] == parameters.reference_asset_id
                        ),
                        None,
                    )
                    if reference is None:
                        raise Problem(422, "REFERENCE_REQUIRED", "参考栅格必须已加入本研究。")
                    sources.append(reference)
            node_options = {"operator": body.operator, "band": body.band}
            if body.operator != "valid_mask":
                node_options["parameters"] = body.parameters
            if body.operator == "planning_units" and task["draft"]["options"].get(
                "spatial_reference"
            ):
                node_options["spatial_reference"] = task["draft"]["options"]["spatial_reference"]
            draft = TaskDraft(
                title={
                    "valid_mask": "有效覆盖",
                    "align_grid": "空间统一",
                    "ndvi": "NDVI指标生产",
                    "score": "指标标准化",
                    "planning_units": "规划单元准备",
                }[body.operator],
                purpose="spatial",
                selection=sources,
                mapping=[b for b in task["draft"]["mapping"] if b["asset_id"] == body.asset_id]
                if body.operator == "planning_units"
                else [],
                options=node_options,
            )
            node = {
                "id": identifier(),
                "task_id": task_id,
                "actor": actor,
                "intent": body.idempotency_key,
                "fingerprint": digest,
                "draft": draft.model_dump(mode="json"),
                "created": time.time(),
            }
            c.execute(insert(processing_nodes).values(**node))
            audit_event(c, actor, task["project_id"], "create_processing_node", node["id"])
            return node

    @routes.post("/api/processing-nodes/{node_id}/execute", status_code=202)
    def execute(node_id: str, body: ExecuteRequest, request: Request):
        actor = request.state.actor["id"]
        with store.engine.connect() as c:
            node = read_node(c, store, actor, node_id)
        return Execution(store).enqueue(
            actor, node["task_id"], body.expected_revision, body.idempotency_key, node_id=node_id
        )

    return routes
