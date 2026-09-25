"""Result comparison uses ordinary durable tasks and immutable input run references."""

import hashlib
import json

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from .comparison import compare
from .execution import Execution, jobs
from .store import Problem

SUPPORTED = ["assessment", "optimization", "temporal"]
MAX_RESULT_BYTES = 256 * 1024**2


def read_input(store, actor, project, job_id, expected=None):
    if not isinstance(job_id, str) or not job_id:
        raise Problem(
            422, "COMPARISON_INPUT_REQUIRED", "请选择基准成果和对照成果，无需重新导入资料。"
        )
    job = Execution(store).read_job(actor, job_id)
    if job["project_id"] != project:
        raise Problem(422, "RESULT_PROJECT_MISMATCH", "所选成果不属于当前项目。")
    if job["status"] != "succeeded":
        raise Problem(422, "RESULT_NOT_READY", "只能比较实际执行成功的不可变成果。")
    if job["manifest"]["draft"]["purpose"] not in SUPPORTED:
        raise Problem(422, "COMPARISON_NOT_READY", "此类成果尚无数值可比性规则。")
    path = (store.settings.storage_root / job["output_key"]).resolve()
    if not path.is_relative_to(store.settings.storage_root.resolve()):
        raise Problem(500, "ARTIFACT_BOUNDARY", "成果路径不属于当前存储空间。")
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_RESULT_BYTES + 1)
    except OSError as exc:
        raise Problem(422, "COMPARISON_INPUT_MISSING", "原始成果文件不可读取。") from exc
    if len(raw) > MAX_RESULT_BYTES:
        raise Problem(422, "COMPARISON_SIZE", "成果超过当前256MiB比较读取上限，原成果仍可下载。")
    digest = hashlib.sha256(raw).hexdigest()
    if expected is not None and digest != expected["sha256"]:
        raise Problem(422, "COMPARISON_INPUT_CHANGED", "固定成果字节发生变化，不能继续比较。")
    try:
        result = json.loads(raw)
        if result["manifest"] != job["manifest"]:
            raise ValueError("manifest mismatch")
    except (ValueError, KeyError, TypeError) as exc:
        raise Problem(422, "RESULT_CONTRACT_INVALID", "成果与固定运行来源不一致。") from exc
    return (
        {
            "job_id": job_id,
            "sha256": digest,
            "size": len(raw),
            "title": job["manifest"]["draft"]["title"],
            "task_id": job["task_id"],
            "draft_revision": job["manifest"]["draft_revision"],
            "purpose": job["manifest"]["draft"]["purpose"],
        },
        result,
        raw,
    )


def prepare(store, actor, task):
    options = task["draft"]["options"]
    left, a, _ = read_input(store, actor, task["project_id"], options.get("left_job_id"))
    right, b, _ = read_input(store, actor, task["project_id"], options.get("right_job_id"))
    if left["job_id"] == right["job_id"]:
        raise Problem(422, "SAME_RESULT", "请选择两次不同运行的成果。")
    report = compare(a, b)
    return [left, right], report


def preflight(store, actor, task):
    references, report, issues = [], None, []
    try:
        references, report = prepare(store, actor, task)
        issues = report["issues"]
    except Problem as exc:
        issues = [{"code": exc.code, "message": exc.message}]
    return {
        "ready": not issues,
        "issues": issues,
        "sources": [],
        "method": None,
        "runtime": None,
        "comparison_inputs": references,
        "comparison": {k: v for k, v in report.items() if k != "rows"} if report else None,
        "states": {
            "data_ingested": bool(references),
            "technical_quality": "issues" if issues else "checked",
            "method_approved": False,
            "model_approved": False,
            "input_applicable": not issues,
            "execution_succeeded": False,
            "business_validated": False,
        },
    }


def compute(store, manifest, cancelled):
    refs = manifest["comparison_inputs"]
    if len(refs) != 2:
        raise Problem(422, "COMPARISON_INPUT_REQUIRED", "比较必须绑定两项实际成果。")
    results = []
    for ref in refs:
        if cancelled.is_set():
            raise Problem(409, "CANCELLED", "比较已取消。")
        _, result, _ = read_input(
            store, manifest["actor"], manifest["project_id"], ref["job_id"], ref
        )
        results.append(result)
    report = compare(*results)
    if not report["comparable"]:
        raise Problem(
            422, "COMPARISON_BLOCKED", "成果不满足可比性条件。", {"issues": report["issues"]}
        )
    return {**report, "inputs": refs}


def router(store):
    routes = APIRouter()

    @routes.get("/api/projects/{project}/completed-results")
    def listing(
        project: str,
        request: Request,
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        with store.engine.connect() as c:
            store.permission(c, request.state.actor["id"], project)
            condition = (
                (jobs.c.project_id == project)
                & (jobs.c.status == "succeeded")
                & (jobs.c.manifest["draft"]["purpose"].as_string().in_(SUPPORTED))
            )
            total = c.scalar(select(func.count()).select_from(jobs).where(condition))
            rows = c.execute(
                select(jobs)
                .where(condition)
                .order_by(jobs.c.created.desc(), jobs.c.id.desc())
                .limit(limit)
                .offset(offset)
            ).mappings()
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": [
                    {
                        "id": j["id"],
                        "task_id": j["task_id"],
                        "title": j["manifest"]["draft"]["title"],
                        "purpose": j["manifest"]["draft"]["purpose"],
                        "draft_revision": j["manifest"]["draft_revision"],
                        "created": j["created"],
                    }
                    for j in rows
                ],
            }

    return routes
