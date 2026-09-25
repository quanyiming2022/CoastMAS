"""Attach fixed asset versions atomically without replacing existing mappings."""

import copy
import hashlib
import json

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import JSON, Column, ForeignKey, String, Table, insert, select

from .contracts import Contract, TaskDraft
from .intake import Intake
from .management_catalog import require_available
from .resource_catalog import require_active
from .store import Problem, audit_event, metadata, revisions

attachment_receipts = Table(
    "input_attachment_receipts",
    metadata,
    Column("task_id", ForeignKey("tasks.id"), primary_key=True),
    Column("actor", ForeignKey("accounts.id"), primary_key=True),
    Column("intent", String, primary_key=True),
    Column("fingerprint", String, nullable=False),
    Column("response", JSON, nullable=False),
)


class InputVersion(Contract):
    asset_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=1)


class AttachInputs(Contract):
    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    inputs: list[InputVersion] = Field(min_length=1, max_length=200)


def revision_conflict(c, task, expected):
    before = c.scalar(
        select(revisions.c.draft).where(
            revisions.c.task_id == task["id"], revisions.c.revision == expected
        )
    )
    changes = [
        {"field": key, "before": (before or {}).get(key), "current": value}
        for key, value in task["draft"].items()
        if before is None or before.get(key) != value
    ]
    return Problem(
        409,
        "DRAFT_CONFLICT",
        "研究配置已更新，请核对变化后重试。",
        {
            "object": {"kind": "task", "id": task["id"], "name": task["draft"]["title"]},
            "action": "attach",
            "current_revision": task["revision"],
            "expected_revision": expected,
            "changes": changes,
            "recoverable": True,
            "allowed_next_actions": ["review_changes", "retry"],
        },
    )


def attach_inputs(store, actor, task_id, body):
    from .reuse import Reuse

    fingerprint = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
    intake, reuse = Intake(store), Reuse(store)
    with store.engine.begin() as c:
        task = store.task(actor, task_id, write=True, connection=c)
        # Lock parent then child before reading the revision/receipt. This also
        # serializes SQLite writers and lifecycle mutations, not only PostgreSQL.
        require_available(c, "projects", task["project_id"])
        require_available(c, "tasks", task_id)
        task = store.task(actor, task_id, write=True, connection=c)
        receipt = (
            c.execute(
                select(attachment_receipts).where(
                    attachment_receipts.c.task_id == task_id,
                    attachment_receipts.c.actor == actor,
                    attachment_receipts.c.intent == body.idempotency_key,
                )
            )
            .mappings()
            .first()
        )
        if receipt:
            if receipt["fingerprint"] != fingerprint:
                raise Problem(409, "ATTACH_INTENT_CONFLICT", "同一加入请求不能用于不同资料。")
            return receipt["response"]
        if task["revision"] != body.expected_revision:
            raise revision_conflict(c, task, body.expected_revision)
        draft = copy.deepcopy(task["draft"])
        results, changed = [], False
        for ref in body.inputs:
            try:
                asset = intake.read_asset(actor, ref.asset_id, connection=c)
                if asset["project_id"] != task["project_id"]:
                    raise Problem(422, "PROJECT_MISMATCH", "资料与研究必须属于同一项目。")
                try:
                    require_active(c, asset["id"])
                except Problem as exc:
                    if exc.code != "RESOURCE_RECYCLED":
                        raise
                    raise Problem(409, "ASSET_UNAVAILABLE", "这份资料已回收，不能新加入。") from exc
                if asset["revision"] != ref.revision:
                    raise Problem(409, "ASSET_VERSION_CHANGED", "资料版本已变化，请重新核对。")
                existing = next(
                    (r for r in draft["selection"] if r["asset_id"] == asset["id"]), None
                )
                if existing:
                    if existing["revision"] != ref.revision:
                        raise Problem(
                            409, "INPUT_VERSION_CONFLICT", "已引用其他版本，请显式修订绑定。"
                        )
                    status = "already_present"
                else:
                    suggested = reuse.suggestions(actor, asset["id"], asset=asset, connection=c)
                    reuse.bind(draft, asset, suggested)
                    changed, status = True, "added"
                results.append({**ref.model_dump(), "status": status, "name": asset["name"]})
            except Problem as exc:
                results.append(
                    {
                        **ref.model_dump(),
                        "status": "rejected",
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    }
                )
        if changed:
            task = store.save_task(
                actor,
                task_id,
                task["revision"],
                TaskDraft.model_validate(draft).model_dump(mode="json"),
                c,
            )
        response = {"task": task, "items": results, "intent": body.idempotency_key}
        c.execute(
            insert(attachment_receipts).values(
                task_id=task_id,
                actor=actor,
                intent=body.idempotency_key,
                fingerprint=fingerprint,
                response=response,
            )
        )
        audit_event(c, actor, task["project_id"], "attach_inputs", task_id)
        return response


def router(store):
    routes = APIRouter()

    @routes.post("/api/tasks/{task_id}/inputs:attach")
    def attach(task_id: str, body: AttachInputs, request: Request):
        return attach_inputs(store, request.state.actor["id"], task_id, body)

    return routes
