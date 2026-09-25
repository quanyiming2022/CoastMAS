"""Durable task-scoped intake intent; bytes and scientific attachment stay separate."""

import hashlib
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import JSON, Column, ForeignKey, Integer, String, Table, insert, select, update

from .contracts import Contract
from .group_sessions import group_sessions
from .input_transactions import AttachInputs, attach_inputs, revision_conflict
from .intake import assets
from .management_catalog import require_available
from .source_snapshots import snapshots
from .store import Problem, accounts, metadata
from .upload_sessions import uploads

targets = Table(
    "task_import_targets",
    metadata,
    Column("id", String, primary_key=True),
    Column("task_id", ForeignKey("tasks.id"), nullable=False),
    Column("project_id", ForeignKey("projects.id"), nullable=False),
    Column("actor", ForeignKey("accounts.id"), nullable=False),
    Column("initial_revision", Integer, nullable=False),
    Column("expected_revision", Integer, nullable=False),
    Column("resources", JSON, nullable=False),
    Column("receipts", JSON, nullable=False),
)


class Start(Contract):
    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=100)


class Resource(Contract):
    kind: Literal["upload", "group", "source"]
    id: str = Field(min_length=1, max_length=128)


class Bind(Contract):
    asset_id: str = Field(min_length=1, max_length=128)
    reviewed_revision: int | None = Field(default=None, ge=1)


TABLES = {"upload": uploads, "group": group_sessions, "source": snapshots}


def router(store):
    routes = APIRouter()

    def read(c, actor, key, lock=False):
        if lock:
            c.execute(update(accounts).where(accounts.c.id == actor).values(id=actor))
        row = (
            c.execute(select(targets).where(targets.c.id == key, targets.c.actor == actor))
            .mappings()
            .first()
        )
        if not row:
            raise Problem(404, "IMPORT_TARGET", "导入目标不可用")
        store.task(actor, row["task_id"], write=True, connection=c)
        return dict(row)

    def transport(c, actor, project, ref):
        table = TABLES[ref["kind"]]
        row = (
            c.execute(
                select(table).where(
                    table.c.id == ref["id"], table.c.actor == actor, table.c.project_id == project
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise Problem(404, "IMPORT_RESOURCE", "接收记录不属于当前导入目标")
        return row

    def view(c, row):
        entries = []
        for ref in row["resources"]:
            item = transport(c, row["actor"], row["project_id"], ref)
            asset_id = item["asset_id"]
            name = (
                c.scalar(select(assets.c.name).where(assets.c.id == asset_id)) if asset_id else None
            )
            receipt = row["receipts"].get(asset_id, {}) if asset_id else {}
            entries.append(
                {
                    **ref,
                    "asset_id": asset_id,
                    "name": name,
                    "status": receipt.get("status", "ready_to_attach" if asset_id else "receiving"),
                    "error": receipt.get("error"),
                }
            )
        return {k: v for k, v in row.items() if k not in ("receipts", "resources", "actor")} | {
            "entries": entries
        }

    @routes.post("/api/tasks/{task_id}/import-targets", status_code=201)
    def start(task_id: str, body: Start, request: Request):
        actor = request.state.actor["id"]
        key = hashlib.sha256(f"{actor}:{task_id}:{body.idempotency_key}".encode()).hexdigest()[:32]
        with store.engine.begin() as c:
            c.execute(update(accounts).where(accounts.c.id == actor).values(id=actor))
            task = store.task(actor, task_id, write=True, connection=c)
            require_available(c, "projects", task["project_id"])
            require_available(c, "tasks", task_id)
            old = c.execute(select(targets).where(targets.c.id == key)).mappings().first()
            if old:
                if old["initial_revision"] != body.expected_revision:
                    raise Problem(409, "IMPORT_TARGET_CHANGED", "同一导入请求不能更改原目标版本")
                return view(c, dict(old))
            if task["revision"] != body.expected_revision:
                raise revision_conflict(c, task, body.expected_revision)
            row = {
                "id": key,
                "actor": actor,
                "task_id": task_id,
                "project_id": task["project_id"],
                "initial_revision": body.expected_revision,
                "expected_revision": body.expected_revision,
                "resources": [],
                "receipts": {},
            }
            c.execute(insert(targets).values(**row))
            return view(c, row)

    @routes.get("/api/tasks/{task_id}/import-targets")
    def listing(task_id: str, request: Request):
        actor = request.state.actor["id"]
        with store.engine.connect() as c:
            store.task(actor, task_id, write=True, connection=c)
            rows = c.execute(
                select(targets).where(targets.c.task_id == task_id, targets.c.actor == actor)
            ).mappings()
            return [view(c, dict(row)) for row in rows]

    @routes.post("/api/import-targets/{key}/resources")
    def register(key: str, body: Resource, request: Request):
        with store.engine.begin() as c:
            row = read(c, request.state.actor["id"], key, True)
            ref = body.model_dump()
            transport(c, row["actor"], row["project_id"], ref)
            for existing in c.execute(
                select(targets).where(
                    targets.c.actor == row["actor"], targets.c.project_id == row["project_id"]
                )
            ).mappings():
                if ref in existing["resources"]:
                    if existing["task_id"] != row["task_id"]:
                        raise Problem(
                            409,
                            "IMPORT_ORIGINAL_TARGET",
                            "此接收记录已有原研究目标，请在原研究继续；入库后也可从资料库明确加入其他研究",
                        )
                    return view(c, dict(existing))
            if ref not in row["resources"]:
                row["resources"] = [*row["resources"], ref]
                c.execute(
                    update(targets).where(targets.c.id == key).values(resources=row["resources"])
                )
            return view(c, row)

    @routes.post("/api/import-targets/{key}/bind")
    def bind(key: str, body: Bind, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            row = read(c, actor, key, True)
            if not any(
                transport(c, actor, row["project_id"], ref)["asset_id"] == body.asset_id
                for ref in row["resources"]
            ):
                raise Problem(
                    409, "IMPORT_RESOURCE", "资料不是此导入批次的受管产物，请从资料库明确加入"
                )
            old = row["receipts"].get(body.asset_id)
            if old and old["status"] == "attached":
                return old
            expected = row["expected_revision"]
            if body.reviewed_revision is not None:
                task = store.task(actor, row["task_id"], write=True, connection=c)
                if task["revision"] != body.reviewed_revision:
                    raise revision_conflict(c, task, body.reviewed_revision)
                expected = body.reviewed_revision
            revision = c.scalar(select(assets.c.revision).where(assets.c.id == body.asset_id))
        try:
            receipt = attach_inputs(
                store,
                actor,
                row["task_id"],
                AttachInputs(
                    expected_revision=expected,
                    idempotency_key=f"import:{key}:{body.asset_id}:{expected}",
                    inputs=[{"asset_id": body.asset_id, "revision": revision}],
                ),
            )
            item = receipt["items"][0]
            result = {
                "status": "attached" if item["status"] != "rejected" else "not_attached",
                "asset_id": body.asset_id,
                "task": receipt["task"],
                "error": None
                if item["status"] != "rejected"
                else {"code": item["code"], "message": item["message"]},
            }
        except Problem as exc:
            result = {
                "status": "not_attached",
                "asset_id": body.asset_id,
                "error": {"code": exc.code, "message": exc.message, "details": exc.details},
            }
        with store.engine.begin() as c:
            current = read(c, actor, key, True)
            # Receipt replay makes a crash between attachment and this bookkeeping safe.
            receipts = {**current["receipts"], body.asset_id: result}
            next_revision = (
                max(current["expected_revision"], result["task"]["revision"])
                if result["status"] == "attached"
                else current["expected_revision"]
            )
            c.execute(
                update(targets)
                .where(targets.c.id == key)
                .values(receipts=receipts, expected_revision=next_revision)
            )
        return result

    return routes
