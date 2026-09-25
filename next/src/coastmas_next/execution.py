"""Freeze, revalidate and enqueue in one operation; each scientific state stays explicit."""

import hashlib
import json
import time

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from pydantic import Field, ValidationError
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    String,
    Table,
    UniqueConstraint,
    case,
    func,
    insert,
    select,
    update,
)

from .contracts import Contract
from .intake import Intake
from .store import Problem, audit_event, identifier, metadata, tasks

jobs = Table(
    "jobs",
    metadata,
    Column("id", String, primary_key=True),
    Column("task_id", ForeignKey("tasks.id"), nullable=False),
    Column("project_id", ForeignKey("projects.id"), nullable=False),
    Column("actor", String, nullable=False),
    Column("idempotency_key", String, nullable=False),
    Column("fingerprint", String, nullable=False),
    Column("status", String, nullable=False),
    Column("manifest", JSON, nullable=False),
    Column("error", JSON),
    Column("output_key", String),
    Column("created", Float, nullable=False),
    Column("started", Float),
    Column("finished", Float),
    Column("lease", String),
    Column("lease_until", Float, nullable=False, default=0),
    Column("cancel_requested", Boolean, nullable=False, default=False),
    UniqueConstraint("task_id", "idempotency_key"),
)


class ExecuteRequest(Contract):
    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def preflight(store, actor, task):
    if task["draft"]["purpose"] == "comparison":
        from .comparison_tasks import preflight as compare_preflight

        return compare_preflight(store, actor, task)
    from .stage_products import effective_task

    task = effective_task(store, actor, task)
    intake = Intake(store)
    issues, sources = [], []
    draft = task["draft"]
    if not draft["selection"]:
        issues.append(
            {"code": "DATA_REQUIRED", "message": "请选择当前任务要使用的资料", "field": "selection"}
        )
    for ref in draft["selection"]:
        asset = intake.read_asset(actor, ref["asset_id"])
        if asset["project_id"] != task["project_id"] or asset["revision"] != ref["revision"]:
            issues.append(
                {
                    "code": "SOURCE_CHANGED",
                    "message": "资产版本或项目不匹配",
                    "asset_id": ref["asset_id"],
                }
            )
        sources.append(asset)
        if draft["purpose"] in {"cluster", "regression", "entities", "optimization", "assessment"}:
            issues.extend(
                issue
                for issue in asset["facts"]["issues"]
                if not ref.get("layer") or not issue.get("layer") or issue["layer"] == ref["layer"]
            )
    # Decision methods validate exactly their declared inputs in decision_preflight.
    # Unused source columns must not become mandatory scientific questions.
    if draft["purpose"] in {"cluster", "regression", "temporal"}:
        for binding in draft["mapping"]:
            if binding["role"] not in {"feature", "response"}:
                continue
            if not binding["unit"]:
                issues.append(
                    {
                        "code": "UNIT_REQUIRED",
                        "field": binding["field"],
                        "message": "计算变量的单位尚无依据",
                    }
                )
            if not binding["concept"]:
                issues.append(
                    {
                        "code": "CONCEPT_REQUIRED",
                        "field": binding["field"],
                        "message": "计算变量的科学含义尚未确定",
                    }
                )
    from .reuse import validate_knowledge

    if draft["purpose"] not in {"inspect", "spatial"}:
        issues.extend(validate_knowledge(store, actor, task["project_id"], draft, sources))
    method = None
    new_planning = (
        draft["purpose"] == "optimization" and draft["options"].get("task_type") == "planning"
    )
    if new_planning:
        issues.append(
            {
                "code": "PLANNING_COMPILER_NOT_READY",
                "message": (
                    "规划配置可保存和复用；完整诊断、问题编译与候选再评价服务尚未接通，"
                    "当前不能提交规划求解。"
                ),
                "category": "engineering_not_implemented",
            }
        )
    if draft["purpose"] in {"assessment", "optimization"} and not new_planning:
        from .decisions import preflight as decision_preflight

        try:
            method = decision_preflight(store, actor, task, sources)
        except Problem as exc:
            issues.append({"code": exc.code, "message": exc.message, "details": exc.details})
        except ValidationError as exc:
            issues.append(
                {
                    "code": "METHOD_INVALID",
                    "message": "认可方法配置不完整或数值无效",
                    "details": str(exc)[:1000],
                }
            )
    runtime = None
    if draft["purpose"] in {"cluster", "regression"}:
        from .models import projection_preflight

        try:
            runtime = projection_preflight(store, actor, task, sources)
        except Problem as exc:
            issues.append({"code": exc.code, "message": exc.message, "details": exc.details})
        except ValidationError:
            issues.append(
                {
                    "code": "METHOD_PARAMETERS",
                    "message": "请选择标准化规则、模型规模和可复现随机种子",
                }
            )
    if draft["purpose"] == "spatial":
        from .spatial import preflight as spatial_preflight

        try:
            method = spatial_preflight(store.settings, draft, sources)
        except Problem as exc:
            issues.append({"code": exc.code, "message": exc.message})
    if draft["purpose"] == "temporal":
        import threading

        from .temporal import compute as temporal_compute

        try:
            temporal_compute(store.settings, {"assets": sources, "draft": draft}, threading.Event())
        except Problem as exc:
            issues.append({"code": exc.code, "message": exc.message, "details": exc.details})
    if draft["purpose"] not in {
        "inspect",
        "spatial",
        "entities",
        "temporal",
        "cluster",
        "regression",
        "assessment",
        "optimization",
    }:
        issues.append(
            {"code": "METHOD_NOT_READY", "message": "此任务的执行方法正在接入，不能提交空任务"}
        )
    return {
        "effective_draft": draft,
        "method": method,
        "runtime": runtime,
        "ready": not issues,
        "issues": issues,
        "sources": sources,
        "states": {
            "data_ingested": bool(sources),
            "technical_quality": "issues"
            if any(a["facts"]["issues"] for a in sources)
            else "checked",
            "method_approved": method is not None,
            "model_approved": runtime is not None
            or method is not None
            or draft["purpose"] in {"inspect", "entities", "temporal"},
            "input_applicable": not issues,
            "execution_succeeded": False,
            "business_validated": False,
        },
    }


class Execution:
    def __init__(self, store):
        self.store = store

    def read_job(self, actor, job_id, write=False, connection=None):
        if connection is None:
            with self.store.engine.connect() as c:
                return self.read_job(actor, job_id, write, c)
        job = connection.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
        if job is None:
            raise Problem(404, "JOB_UNAVAILABLE", "运行不可用")
        self.store.permission(connection, actor, job["project_id"], write=write)
        return dict(job)

    def enqueue(self, actor, task_id, revision, key, *, node_id=None):
        with self.store.engine.begin() as c:
            task = self.store.task(actor, task_id, write=True, connection=c)
            from .management_catalog import require_available

            require_available(c, "projects", task["project_id"])
            require_available(c, "tasks", task_id)
            # Conditional UPDATE locks the task and rules out racing stale saves.
            if (
                c.execute(
                    update(tasks)
                    .where(tasks.c.id == task_id, tasks.c.revision == revision)
                    .values(updated=tasks.c.updated)
                ).rowcount
                != 1
            ):
                raise Problem(409, "DRAFT_CONFLICT", "任务版本已改变；请先保存并核对当前内容")
            if node_id is not None:
                from .research_workspace import read_node

                node = read_node(c, self.store, actor, node_id, task_id)
                task = {**task, "draft": node["draft"]}
            check = preflight(self.store, actor, task)
            if not check["ready"]:
                raise Problem(
                    422,
                    "PREFLIGHT_BLOCKED",
                    "仅需处理当前任务的必要缺口",
                    {"issues": check["issues"]},
                )
            from .resource_catalog import require_active

            # Stable lock order coordinates catalog recycling with new run freezing.
            for source in sorted(check["sources"], key=lambda item: item["id"]):
                require_active(c, source["id"])
            manifest = {
                "contract_version": 1,
                "actor": actor,
                "project_id": task["project_id"],
                "task_id": task_id,
                "draft_revision": revision,
                "draft": check.get("effective_draft", task["draft"]),
                "assets": check["sources"],
                "states": check["states"],
                "runtime": check["runtime"],
                "method": check["method"],
            }
            if task["draft"]["purpose"] == "comparison":
                manifest["comparison_inputs"] = check["comparison_inputs"]
            if node_id is not None:
                manifest["processing_node_id"] = node_id
                manifest["business_role"] = {
                    "valid_mask": "quality_control",
                    "align_grid": "spatial_preparation",
                    "ndvi": "indicator_production",
                    "builtin_indicator": "indicator_production",
                    "score": "normalization",
                    "planning_units": "spatial_preparation",
                }.get(task["draft"]["options"].get("operator"), "processing")
            digest = fingerprint(manifest)
            existing = (
                c.execute(
                    select(jobs).where(jobs.c.task_id == task_id, jobs.c.idempotency_key == key)
                )
                .mappings()
                .first()
            )
            if existing:
                if existing["fingerprint"] != digest:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT", "此提交标识对应不同任务配置")
                return dict(existing)
            row = {
                "id": identifier(),
                "task_id": task_id,
                "project_id": task["project_id"],
                "actor": actor,
                "idempotency_key": key,
                "fingerprint": digest,
                "status": "queued",
                "manifest": manifest,
                "created": time.time(),
                "lease_until": 0,
                "cancel_requested": False,
            }
            c.execute(insert(jobs).values(**row))
            audit_event(c, actor, task["project_id"], "enqueue", row["id"])
            return row

    def cancel(self, actor, job_id):
        with self.store.engine.begin() as c:
            job = self.read_job(actor, job_id, write=True, connection=c)
            if job["status"] in {"queued", "running"}:
                c.execute(
                    update(jobs)
                    .where(jobs.c.id == job_id, jobs.c.status.in_(["queued", "running"]))
                    .values(
                        cancel_requested=True,
                        status=case((jobs.c.status == "queued", "cancelled"), else_=jobs.c.status),
                        finished=case(
                            (jobs.c.status == "queued", time.time()), else_=jobs.c.finished
                        ),
                    )
                )
        return self.read_job(actor, job_id)


def router(store):
    routes, execution = APIRouter(), Execution(store)

    @routes.get("/api/tasks/{task_id}/configuration-review")
    def review_configuration(task_id: str, request: Request, revision: int = Query(ge=1)):
        from .configuration_review import review

        return review(store, request.state.actor["id"], task_id, revision)

    @routes.get("/api/tasks/{task_id}/preflight")
    def check(task_id: str, request: Request):
        actor = request.state.actor["id"]
        return preflight(store, actor, store.task(actor, task_id))

    @routes.post("/api/tasks/{task_id}/execute", status_code=202)
    def execute(task_id: str, body: ExecuteRequest, request: Request):
        return execution.enqueue(
            request.state.actor["id"], task_id, body.expected_revision, body.idempotency_key
        )

    @routes.get("/api/tasks/{task_id}/jobs")
    def history(
        task_id: str,
        request: Request,
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
        query: str = Query("", max_length=128),
        status: str | None = None,
    ):
        store.task(request.state.actor["id"], task_id)
        condition = jobs.c.task_id == task_id
        if query:
            condition &= jobs.c.id.contains(query, autoescape=True)
        if status:
            if status not in {"queued", "running", "succeeded", "failed", "cancelled"}:
                raise Problem(422, "JOB_STATUS", "运行状态筛选无效")
            condition &= jobs.c.status == status
        with store.engine.connect() as c:
            total = c.scalar(select(func.count()).select_from(jobs).where(condition))
            rows = c.execute(
                select(jobs)
                .where(condition)
                .order_by(jobs.c.created.desc(), jobs.c.id.desc())
                .limit(limit)
                .offset(offset)
            ).mappings()
            return {
                "items": [
                    {
                        **{
                            key: row[key]
                            for key in [
                                "id",
                                "task_id",
                                "status",
                                "created",
                                "started",
                                "finished",
                                "error",
                                "cancel_requested",
                            ]
                        },
                        "draft_revision": row["manifest"]["draft_revision"],
                    }
                    for row in rows
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    @routes.get("/api/jobs/{job_id}")
    def read_job(job_id: str, request: Request):
        return execution.read_job(request.state.actor["id"], job_id)

    @routes.get("/api/jobs/{job_id}/result")
    def result(job_id: str, request: Request):
        job = execution.read_job(request.state.actor["id"], job_id)
        if job["status"] != "succeeded":
            raise Problem(409, "RESULT_NOT_READY", "没有已完成的结果")
        return json.loads((store.settings.storage_root / job["output_key"]).read_text())

    @routes.get("/api/jobs/{job_id}/download")
    def download(job_id: str, request: Request):
        job = execution.read_job(request.state.actor["id"], job_id)
        if job["status"] != "succeeded":
            raise Problem(409, "RESULT_NOT_READY", "没有已完成的结果")
        return FileResponse(
            store.settings.storage_root / job["output_key"],
            filename=f"coastmas-{job_id}.json",
            media_type="application/json",
        )

    @routes.get("/api/jobs/{job_id}/files/{index}")
    def output_file(job_id: str, index: int, request: Request):
        job = execution.read_job(request.state.actor["id"], job_id)
        if job["status"] != "succeeded":
            raise Problem(409, "RESULT_NOT_READY", "运行尚未生成完整成果")
        content = json.loads((store.settings.storage_root / job["output_key"]).read_text())
        files = content["data"].get("files", [])
        if index < 0 or index >= len(files):
            raise Problem(404, "ARTIFACT_UNAVAILABLE", "成果文件不存在")
        item = files[index]
        target = (store.settings.storage_root / item["key"]).resolve()
        owned = (store.settings.storage_root / job["output_key"]).with_suffix("").resolve()
        if not target.is_relative_to(owned):
            raise Problem(500, "ARTIFACT_BOUNDARY", "成果路径与运行身份不一致")
        return FileResponse(target, filename=item["name"], media_type=item["media_type"])

    @routes.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str, request: Request):
        actor = request.state.actor["id"]
        return execution.cancel(actor, job_id)

    return routes
