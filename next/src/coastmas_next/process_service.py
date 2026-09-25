"""Authenticated OGC API Processes 1.0 subset over the same immutable task jobs.

Async document/reference responses are implemented and tested against official
schemas. Core/Dismiss conformance is deliberately not advertised: arbitrary URL
inputs, raw/value responses, callback and deletion of finished evidence are absent.
"""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import select

from .contracts import Contract
from .execution import Execution, jobs
from .store import Problem, members

ROOT = "/api/ogc/1.0"
REL = "http://www.opengis.net/def/rel/ogc/1.0/"
PROCESSES = {
    "inspect": "资料检查",
    "entities": "地理实体提取",
    "temporal": "时间适配",
    "assessment": "综合评价",
    "optimization": "空间优化",
    "cluster": "投影寻踪聚类",
    "regression": "投影寻踪回归",
}
STATUSES = {
    "queued": "accepted",
    "running": "running",
    "succeeded": "successful",
    "failed": "failed",
    "cancelled": "dismissed",
}


class TaskReference(Contract):
    id: str = Field(min_length=1, max_length=128, strict=True)
    revision: int = Field(ge=1, strict=True)


class QualifiedTask(Contract):
    value: TaskReference
    mediaType: Literal["application/json"] = "application/json"


class Inputs(Contract):
    task: QualifiedTask


class Format(Contract):
    mediaType: Literal["application/json"] = "application/json"


class Output(Contract):
    transmissionMode: Literal["reference"] = "reference"
    format: Format = Field(default_factory=Format)


class ProcessRequest(Contract):
    inputs: Inputs
    # Explicit rather than silently substituting document for OGC's raw default.
    response: Literal["document"]
    outputs: dict[Literal["result"], Output] = Field(
        default_factory=lambda: {"result": Output()}, min_length=1
    )


def exception(problem, request):
    return JSONResponse(
        status_code=problem.status,
        media_type="application/problem+json",
        content={
            "type": "urn:coastmas:problem:" + problem.code,
            "title": problem.message,
            "status": problem.status,
            "detail": problem.message,
            "instance": request.url.path,
            "details": problem.details,
        },
    )


def link(request, path, rel, media="application/json"):
    return {"href": str(request.base_url).rstrip("/") + path, "rel": rel, "type": media}


def query_boundary(request: Request):
    allowed = (
        {"limit", "offset"} if request.url.path in {ROOT + "/processes", ROOT + "/jobs"} else set()
    )
    if set(request.query_params) - allowed:
        raise Problem(400, "UNSUPPORTED_PARAMETER", "此标准服务子集不支持所提供的查询参数")
    accept = request.headers.get("accept", "*/*")
    if not any(value in accept for value in ("application/json", "application/*", "*/*")):
        raise Problem(406, "FORMAT_UNSUPPORTED", "此接口提供JSON表示")


def process(request, process_id, detailed=False):
    if process_id not in PROCESSES:
        raise Problem(404, "NoSuchProcess", "处理方法不存在或尚未实现")
    result = {
        "id": process_id,
        "title": PROCESSES[process_id],
        "version": "1.0.0",
        "description": (
            "执行项目内已保存任务；实际资料、科学缺口、认可方法与模型资格在提交时重新检查。"
        ),
        "jobControlOptions": ["async-execute"],
        "outputTransmission": ["reference"],
        "links": [link(request, ROOT + f"/processes/{process_id}", "self")],
    }
    if detailed:
        result["inputs"] = {
            "task": {
                "title": "已保存任务及固定草稿版本",
                "schema": TaskReference.model_json_schema(),
                "minOccurs": 1,
                "maxOccurs": 1,
            },
        }
        result["outputs"] = {
            "result": {"title": "完整结果及冻结来源", "schema": {"type": "object"}}
        }
    return result


def status(request, job):
    result = {
        "jobID": job["id"],
        "processID": job["manifest"]["draft"]["purpose"],
        "type": "process",
        "status": STATUSES[job["status"]],
        "links": [link(request, ROOT + f"/jobs/{job['id']}", "self")],
    }
    for key in ("created", "started", "finished"):
        if job.get(key) is not None:
            result[key] = datetime.fromtimestamp(job[key], UTC).isoformat().replace("+00:00", "Z")
    if job["status"] == "succeeded":
        result["links"].append(link(request, ROOT + f"/jobs/{job['id']}/results", REL + "results"))
    elif job["status"] == "failed":
        result["links"].append(
            link(request, ROOT + f"/jobs/{job['id']}/results", REL + "exceptions")
        )
    if job.get("cancel_requested") and job["status"] == "running":
        result["message"] = "取消请求已保存，等待实际执行器停止；尚未报告dismissed"
    return result


def page_links(request, path, limit, offset, has_more):
    output = [link(request, path + f"?limit={limit}&offset={offset}", "self")]
    if has_more:
        output.append(link(request, path + f"?limit={limit}&offset={offset + limit}", "next"))
    if offset:
        output.append(
            link(request, path + f"?limit={limit}&offset={max(0, offset - limit)}", "prev")
        )
    return output


def router(store):
    routes = APIRouter(prefix=ROOT, dependencies=[Depends(query_boundary)])
    execution = Execution(store)

    @routes.get("/")
    def landing(request: Request):
        return {
            "title": "CoastMAS scientific task processes",
            "links": [
                link(request, ROOT + "/api", "service-desc"),
                link(request, ROOT + "/conformance", REL + "conformance"),
                link(request, ROOT + "/processes", "processes"),
                link(request, ROOT + "/jobs", "monitor"),
            ],
            "profile": {
                "standard": "OGC API Processes Part 1: Core 1.0",
                "status": "implemented_subset",
                "input": "saved task identity and revision; no remote URL dereferencing",
                "execution": "asynchronous document/reference JSON only",
                "authentication": "CoastMAS session cookie; X-CSRF-Token for writes",
                "cancellation": (
                    "queued: dismissed; running: cancellation pending until worker acknowledges"
                ),
                "preservation": "finished scientific records are immutable; DELETE returns 409",
                "full_conformance_tested": False,
            },
        }

    @routes.get("/api")
    def definition(request: Request):
        return request.app.openapi()

    @routes.get("/conformance")
    def conformance():
        return {"conformsTo": []}

    @routes.get("/processes")
    def list_processes(
        request: Request, limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0)
    ):
        identifiers = list(PROCESSES)
        return {
            "processes": [process(request, name) for name in identifiers[offset : offset + limit]],
            "links": page_links(
                request, ROOT + "/processes", limit, offset, offset + limit < len(identifiers)
            ),
        }

    @routes.get("/processes/{process_id}")
    def describe(process_id: str, request: Request):
        return process(request, process_id, detailed=True)

    @routes.post("/processes/{process_id}/execution", status_code=201)
    def execute(process_id: str, body: ProcessRequest, request: Request):
        process(request, process_id)
        prefer = request.headers.get("Prefer", "respond-async")
        if prefer != "respond-async":
            raise Problem(400, "MODE_UNSUPPORTED", "此方法只提供异步执行，不忽略其他执行偏好")
        actor = request.state.actor["id"]
        task = store.task(actor, body.inputs.task.value.id, write=True)
        if task["draft"]["purpose"] != process_id:
            raise Problem(400, "PROCESS_MISMATCH", "处理方法与保存任务的目标不同")
        key = request.headers.get(
            "Idempotency-Key", f"ogc:{process_id}:{body.inputs.task.value.revision}"
        )
        if not key or len(key) > 128:
            raise Problem(400, "IDEMPOTENCY_INVALID", "提交标识须为1至128个字符")
        job = execution.enqueue(
            actor, body.inputs.task.value.id, body.inputs.task.value.revision, key
        )
        return JSONResponse(
            status_code=201,
            content=status(request, job),
            headers={
                "Location": link(request, ROOT + f"/jobs/{job['id']}", "status")["href"],
                "Preference-Applied": "respond-async",
            },
        )

    @routes.get("/jobs")
    def list_jobs(
        request: Request, limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0)
    ):
        with store.engine.connect() as c:
            rows = list(
                c.execute(
                    select(jobs)
                    .join(members, members.c.project_id == jobs.c.project_id)
                    .where(members.c.account_id == request.state.actor["id"])
                    .order_by(jobs.c.created.desc(), jobs.c.id.desc())
                    .offset(offset)
                    .limit(limit + 1)
                ).mappings()
            )
        return {
            "jobs": [status(request, row) for row in rows[:limit]],
            "links": page_links(request, ROOT + "/jobs", limit, offset, len(rows) > limit),
        }

    @routes.get("/jobs/{job_id}")
    def read(job_id: str, request: Request):
        return status(request, execution.read_job(request.state.actor["id"], job_id))

    @routes.get("/jobs/{job_id}/results")
    def results(job_id: str, request: Request):
        job = execution.read_job(request.state.actor["id"], job_id)
        if job["status"] == "failed":
            error = job.get("error") or {}
            raise Problem(
                500, error.get("code", "EXECUTION_FAILED"), error.get("message", "实际运行失败")
            )
        if job["status"] == "cancelled":
            raise Problem(410, "JobDismissed", "运行已取消，没有生成成果")
        if job["status"] != "succeeded":
            raise Problem(404, "ResultNotReady", "实际成果尚未生成")
        return {
            "result": {
                "href": link(request, f"/api/jobs/{job_id}/download", "item")["href"],
                "type": "application/json",
            }
        }

    @routes.delete("/jobs/{job_id}")
    def dismiss(job_id: str, request: Request):
        actor = request.state.actor["id"]
        job = execution.read_job(actor, job_id, write=True)
        if job["status"] in {"succeeded", "failed"}:
            raise Problem(409, "IMMUTABLE_EVIDENCE", "已完成的运行与证据保留，不通过标准接口删除")
        job = execution.cancel(actor, job_id)
        if job["status"] in {"succeeded", "failed"}:
            raise Problem(409, "IMMUTABLE_EVIDENCE", "运行已经完成，保留实际成果与证据")
        return JSONResponse(
            status_code=202 if job["status"] == "running" else 200, content=status(request, job)
        )

    return routes
