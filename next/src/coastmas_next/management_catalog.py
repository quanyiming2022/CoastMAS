"""Authorized catalog queries and replayable lifecycle mutations, retaining evidence."""

import copy
import time
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import Field, model_validator
from sqlalchemy import (
    JSON,
    Column,
    Float,
    Integer,
    String,
    Table,
    and_,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from .administration import require_admin
from .contracts import Contract, TaskDraft
from .execution import fingerprint, jobs
from .reuse import templates
from .store import (
    Problem,
    accounts,
    audit_event,
    identifier,
    members,
    metadata,
    projects,
    sessions,
    tasks,
)

Kind = Literal["users", "projects", "tasks", "methods", "runs", "results"]
record_meta = Table(
    "managed_record_metadata",
    metadata,
    Column("kind", String, primary_key=True),
    Column("record_id", String, primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("state", String, nullable=False),
    Column("classification", String, nullable=False),
    Column("display_name", String, nullable=False),
    Column("note", String, nullable=False),
    Column("updated", Float, nullable=False),
)
frozen_sets = Table(
    "managed_catalog_selections",
    metadata,
    Column("id", String, primary_key=True),
    Column("actor", String, nullable=False),
    Column("kind", String, nullable=False),
    Column("project", String),
    Column("action", String, nullable=False),
    Column("items", JSON, nullable=False),
    Column("created", Float, nullable=False),
    Column("result", JSON),
)


class CatalogFilter(Contract):
    query: str = Field(default="", max_length=200)
    state: Literal["active", "archived", "recycled", "all"] = "active"
    classification: str = Field(default="", max_length=100)
    status: str = Field(default="", max_length=40)
    sort: Literal["name", "updated"] = "updated"


class Selection(Contract):
    ids: list[str] | None = Field(default=None, min_length=1, max_length=1000)
    query: CatalogFilter | None = None
    excluded_ids: list[str] = Field(default_factory=list, max_length=1000)
    action: Literal["archive", "recycle", "restore", "disable", "enable"]

    @model_validator(mode="after")
    def one_source(self):
        if (self.ids is None) == (self.query is None):
            raise ValueError("选择明确记录或当前筛选，两者必选其一")
        return self


class Mutation(Contract):
    expected_revision: int = Field(ge=0)
    changes: dict = Field(min_length=1, max_length=6)


def require_available(c, kind, record_id, *, lock=True):
    # Coordinate lifecycle with scientific writers on the same parent record.
    table = projects if kind == "projects" else tasks if kind == "tasks" else templates
    column = table.c.name if kind == "projects" else table.c.revision
    if lock:
        c.execute(update(table).where(table.c.id == record_id).values({column.key: column}))
    state = c.scalar(
        select(record_meta.c.state).where(
            record_meta.c.kind == kind, record_meta.c.record_id == record_id
        )
    )
    if state in {"archived", "recycled"}:
        row = c.execute(select(table).where(table.c.id == record_id)).mappings().one()
        name = row["name"] if kind == "projects" else (
            row["draft"]["title"] if kind == "tasks" else row["spec"]["title"])
        label = {"projects": "项目", "tasks": "研究", "methods": "方法"}[kind]
        code = "PROJECT_READ_ONLY" if kind == "projects" else (
            "TASK_RECYCLED" if kind == "tasks" and state == "recycled" else "RECORD_INACTIVE")
        raise Problem(409, code, f"{label}“{name}”已{'回收' if state == 'recycled' else '归档'}。", {
            "object": {"kind": kind, "id": record_id, "name": name, "state": state},
            "recoverable": True, "allowed_next_actions": ["restore_if_authorized", "choose_other"],
        })


def table_for(kind):
    return {
        "users": accounts,
        "projects": projects,
        "tasks": tasks,
        "methods": templates,
        "runs": jobs,
        "results": jobs,
    }[kind]


def record_permission(c, store, actor, kind, row, write=False):
    if kind == "users":
        require_admin(store, actor, c)
    elif kind == "projects":
        if not c.scalar(
            select(accounts.c.system_admin).where(
                accounts.c.id == actor, accounts.c.active.is_(True)
            )
        ):
            store.permission(c, actor, row["id"], manage=write)
    else:
        store.permission(c, actor, row["project_id"], write=write)


def get_record(c, store, actor, kind, record_id, write=False):
    row = (
        c.execute(select(table_for(kind)).where(table_for(kind).c.id == record_id))
        .mappings()
        .first()
    )
    if not row:
        raise Problem(404, "RECORD_UNAVAILABLE", "记录不可用")
    record_permission(c, store, actor, kind, row, write)
    if kind == "results" and row["status"] != "succeeded":
        raise Problem(404, "RESULT_UNAVAILABLE", "成果尚不存在")
    return dict(row)


def meta(c, kind, row):
    stored = (
        c.execute(
            select(record_meta).where(
                record_meta.c.kind == kind, record_meta.c.record_id == row["id"]
            )
        )
        .mappings()
        .first()
    )
    return (
        dict(stored)
        if stored
        else {
            "kind": kind,
            "record_id": row["id"],
            "revision": 0,
            "state": "active",
            "classification": "",
            "display_name": "",
            "note": "",
            "updated": row.get("updated", row.get("created", 0)),
        }
    )


def source_version(row):
    return fingerprint(
        {
            k: row[k]
            for k in ["revision", "email", "system_admin", "active", "name", "status", "approved"]
            if k in row
        }
    )


def present(c, kind, row):
    m = meta(c, kind, row)
    if kind == "users":
        value = {k: row[k] for k in ["id", "email", "system_admin", "active"]}
        value["name"] = row["email"]
        value["status"] = "active" if row["active"] else "disabled"
        value["project_count"] = c.scalar(
            select(func.count()).select_from(members).where(members.c.account_id == row["id"])
        )
    elif kind == "projects":
        value = {"id": row["id"], "name": row["name"], "status": m["state"]}
        value["member_count"] = c.scalar(
            select(func.count()).select_from(members).where(members.c.project_id == row["id"])
        )
    elif kind == "tasks":
        recent = (
            c.execute(
                select(jobs.c.id, jobs.c.status, jobs.c.created)
                .where(jobs.c.task_id == row["id"])
                .order_by(jobs.c.created.desc(), jobs.c.id)
                .limit(1)
            )
            .mappings()
            .first()
        )
        value = {
            "id": row["id"],
            "name": row["draft"]["title"],
            "purpose": row["draft"]["purpose"],
            "source_revision": row["revision"],
            "stage": "运行与成果"
            if recent
            else ("待预检" if row["draft"].get("method_id") else "资料与方法装配"),
            "last_run": dict(recent) if recent else None,
            "status": m["state"],
        }
    elif kind == "methods":
        config = row["spec"]["configuration"]
        value = {
            "id": row["id"],
            "name": row["spec"]["title"],
            "purpose": config.get("task", row["spec"]["purpose"]),
            "algorithm": config.get("method", ""),
            "indicator_count": len(config.get("indicators", [])),
            "source_revision": row["revision"],
            "approved": row["approved"],
            "basis": row["spec"]["basis"],
            "status": "approved" if row["approved"] else "draft",
            "spec": row["spec"],
        }
    else:
        value = {
            "id": row["id"],
            "name": m["display_name"] or row["manifest"].get("draft", {}).get("title", row["id"]),
            "task_id": row["task_id"],
            "status": row["status"],
            "source_revision": row["manifest"].get("draft_revision"),
            "purpose": row["manifest"].get("draft", {}).get("purpose"),
            "created": row["created"],
            "finished": row["finished"],
        }
    return {
        **value,
        "revision": m["revision"],
        "state": m["state"],
        "classification": m["classification"],
        "note": m["note"],
        "updated": m["updated"],
    }


def statement(c, store, actor, kind, project, query):
    t = table_for(kind)
    join = t.outerjoin(
        record_meta, and_(record_meta.c.kind == kind, record_meta.c.record_id == t.c.id)
    )
    condition = []
    if kind == "users":
        require_admin(store, actor, c)
        name = accounts.c.email
    elif kind == "projects":
        name = projects.c.name
        if not c.scalar(
            select(accounts.c.system_admin).where(
                accounts.c.id == actor, accounts.c.active.is_(True)
            )
        ):
            condition.append(
                projects.c.id.in_(select(members.c.project_id).where(members.c.account_id == actor))
            )
    else:
        if not project:
            raise Problem(422, "PROJECT_REQUIRED", "请选择当前项目")
        store.permission(c, actor, project)
        condition.append(t.c.project_id == project)
        name = (
            tasks.c.draft["title"].as_string()
            if kind == "tasks"
            else templates.c.spec["title"].as_string()
            if kind == "methods"
            else jobs.c.manifest["draft"]["title"].as_string()
        )
        if kind == "methods":
            condition.append(templates.c.spec["purpose"].as_string() == "method")
        if kind == "results":
            condition.append(jobs.c.status == "succeeded")
    if query.state != "all":
        condition.append(func.coalesce(record_meta.c.state, "active") == query.state)
    if query.query:
        condition.append(func.lower(name).contains(query.query.lower(), autoescape=True))
    if query.classification:
        condition.append(record_meta.c.classification == query.classification)
    if query.status:
        if kind == "users" and query.status in {"active", "disabled", "admin"}:
            condition.append(
                accounts.c.system_admin.is_(True)
                if query.status == "admin"
                else accounts.c.active.is_(query.status == "active")
            )
        elif kind == "methods" and query.status in {"approved", "draft"}:
            condition.append(templates.c.approved.is_(query.status == "approved"))
        elif kind in {"runs", "results"}:
            condition.append(jobs.c.status == query.status)
        elif kind == "tasks":
            condition.append(tasks.c.draft["purpose"].as_string() == query.status)
        else:
            raise Problem(422, "FILTER_UNSUPPORTED", "当前目录不支持所选状态")
    order = (
        name.asc()
        if query.sort == "name"
        else func.coalesce(
            record_meta.c.updated,
            t.c.updated if kind == "tasks" else t.c.created if kind in {"runs", "results"} else 0,
        ).desc()
    )
    return select(t).select_from(join).where(*condition).order_by(order, t.c.id)


def write_meta(c, kind, row, current, changes):
    value = {**current, **changes, "revision": current["revision"] + 1, "updated": time.time()}
    if current["revision"] == 0:
        c.execute(insert(record_meta).values(**value))
    elif (
        c.execute(
            update(record_meta)
            .where(
                record_meta.c.kind == kind,
                record_meta.c.record_id == row["id"],
                record_meta.c.revision == current["revision"],
            )
            .values(**value)
        ).rowcount
        != 1
    ):
        raise Problem(409, "RECORD_CONFLICT", "记录已更新，请重新读取后修改")


def protect_account(c, actor, row, active=None, admin=None):
    # Serialize all administrative demotions, including concurrent cross-disabling.
    c.execute(
        update(accounts).where(accounts.c.system_admin.is_(True)).values(active=accounts.c.active)
    )
    if (active is False or admin is False) and row["active"] and row["system_admin"]:
        others = c.scalar(
            select(func.count())
            .select_from(accounts)
            .where(
                accounts.c.id != row["id"],
                accounts.c.active.is_(True),
                accounts.c.system_admin.is_(True),
            )
        )
        if not others:
            raise Problem(409, "LAST_ADMIN", "必须保留至少一位有效系统管理员")
    if active is False:
        if row["id"] == actor:
            raise Problem(409, "CURRENT_ACCOUNT", "不能在当前会话停用自己的账号")
        for project in sorted(
            c.scalars(
                select(members.c.project_id).where(
                    members.c.account_id == row["id"], members.c.role == "manager"
                )
            )
        ):
            c.execute(update(projects).where(projects.c.id == project).values(name=projects.c.name))
            if not c.scalar(
                select(func.count())
                .select_from(members.join(accounts))
                .where(
                    members.c.project_id == project,
                    members.c.role == "manager",
                    members.c.account_id != row["id"],
                    accounts.c.active.is_(True),
                )
            ):
                raise Problem(409, "LAST_MANAGER", "请先为相关项目指定另一位有效负责人")
        c.execute(delete(sessions).where(sessions.c.account_id == row["id"]))


def lifecycle(c, store, actor, kind, row, action):
    if kind == "users":
        if action == "archive":
            raise Problem(422, "ACTION_UNSUPPORTED", "账号使用停用或回收")
        active = action in {"restore", "enable"}
        protect_account(c, actor, row, active=active)
        c.execute(update(accounts).where(accounts.c.id == row["id"]).values(active=active))
    elif action in {"enable", "disable"}:
        raise Problem(422, "ACTION_UNSUPPORTED", "此目录不支持账号启停")
    elif action in {"recycle", "archive"}:
        condition = (
            jobs.c.project_id == row["id"]
            if kind == "projects"
            else jobs.c.task_id == row["id"]
            if kind == "tasks"
            else jobs.c.id == row["id"]
            if kind in {"runs", "results"}
            else jobs.c.manifest["method"]["id"].as_string() == row["id"]
        )
        if kind == "projects":
            c.execute(
                update(projects).where(projects.c.id == row["id"]).values(name=projects.c.name)
            )
        if kind == "tasks":
            c.execute(update(tasks).where(tasks.c.id == row["id"]).values(updated=tasks.c.updated))
        if c.scalar(
            select(func.count())
            .select_from(jobs)
            .where(condition, jobs.c.status.in_(["queued", "running"]))
        ):
            raise Problem(
                409, "ACTIVE_DEPENDENCY", "有正在执行或等待的依赖，请先取消或等待；历史原件不会删除"
            )
    return "recycled" if action == "recycle" else "archived" if action == "archive" else "active"


def router(store):
    routes = APIRouter()

    @routes.get("/api/management/catalog/{kind}")
    def listing(
        kind: Kind,
        request: Request,
        project: str = "",
        query: str = Query("", max_length=200),
        state: Literal["active", "archived", "recycled", "all"] = "active",
        classification: str = "",
        status: str = "",
        sort: Literal["name", "updated"] = "updated",
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=100),
    ):
        with store.engine.connect() as c:
            stmt = statement(
                c,
                store,
                request.state.actor["id"],
                kind,
                project,
                CatalogFilter(
                    query=query,
                    state=state,
                    classification=classification,
                    status=status,
                    sort=sort,
                ),
            )
            total = c.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
            return {
                "items": [
                    present(c, kind, dict(row))
                    for row in c.execute(stmt.offset(offset).limit(limit)).mappings()
                ],
                "total": total,
                "offset": offset,
                "limit": limit,
                "scope": {"project": project or None, "kind": kind, "state": state},
            }

    @routes.patch("/api/management/catalog/{kind}/{record_id}")
    def edit(kind: Kind, record_id: str, body: Mutation, request: Request):
        actor = request.state.actor["id"]
        allowed = {"classification", "note"} | (
            {"email", "system_admin"}
            if kind == "users"
            else {"name"}
            if kind in {"projects", "tasks", "results"}
            else set()
        )
        if not set(body.changes) <= allowed:
            raise Problem(422, "FIELD_READONLY", "只允许修改明确的管理字段；历史数值不可编辑")
        with store.engine.begin() as c:
            row = get_record(c, store, actor, kind, record_id, True)
            current = meta(c, kind, row)
            if current["revision"] != body.expected_revision:
                raise Problem(409, "RECORD_CONFLICT", "记录已改变，请重新读取")
            changes = {}
            for key, value in body.changes.items():
                if key == "system_admin":
                    if type(value) is not bool:
                        raise Problem(422, "BOOLEAN_REQUIRED", "系统角色必须为明确布尔值")
                    protect_account(c, actor, row, admin=value)
                    c.execute(
                        update(accounts)
                        .where(accounts.c.id == record_id)
                        .values(system_admin=value)
                    )
                    c.execute(delete(sessions).where(sessions.c.account_id == record_id))
                else:
                    if not isinstance(value, str) or len(value) > (4000 if key == "note" else 240):
                        raise Problem(422, "TEXT_REQUIRED", "字段必须为限定长度的文本")
                    value = value.strip()
                    if key in {"email", "name"} and not value:
                        raise Problem(422, "NAME_REQUIRED", "名称不能为空")
                    if key == "email":
                        from .administration import NewAccount

                        value = NewAccount(email=value, password="unused-placeholder").email.lower()
                        try:
                            with c.begin_nested():
                                c.execute(
                                    update(accounts)
                                    .where(accounts.c.id == record_id)
                                    .values(email=value)
                                )
                        except IntegrityError as exc:
                            raise Problem(409, "EMAIL_EXISTS", "邮箱已被使用") from exc
                    elif key == "name" and kind == "projects":
                        c.execute(
                            update(projects).where(projects.c.id == record_id).values(name=value)
                        )
                    elif key == "name" and kind == "tasks":
                        draft = copy.deepcopy(row["draft"])
                        draft["title"] = value
                        store.save_task(
                            actor,
                            record_id,
                            row["revision"],
                            TaskDraft.model_validate(draft).model_dump(mode="json"),
                            c,
                        )
                    elif key == "name":
                        changes["display_name"] = value
                    else:
                        changes[key] = value
            write_meta(c, kind, row, current, changes)
            audit_event(
                c,
                actor,
                row.get("project_id", record_id if kind == "projects" else None),
                "edit_" + kind,
                record_id,
            )
            return present(c, kind, get_record(c, store, actor, kind, record_id))

    @routes.post("/api/management/catalog/tasks/{record_id}/copy", status_code=201)
    def clone(record_id: str, request: Request):
        actor = request.state.actor["id"]
        task = store.task(actor, record_id, write=True)
        draft = copy.deepcopy(task["draft"])
        draft["title"] = (draft["title"] + " · 副本")[:200]
        draft["options"].pop("publication", None)
        return store.new_task(actor, task["project_id"], draft)

    @routes.post("/api/management/catalog/{kind}/selections", status_code=201)
    def freeze(kind: Kind, body: Selection, request: Request, project: str = ""):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            if body.ids is not None:
                rows = [get_record(c, store, actor, kind, r, True) for r in dict.fromkeys(body.ids)]
            else:
                rows = [
                    dict(r)
                    for r in c.execute(
                        statement(c, store, actor, kind, project, body.query).limit(10001)
                    ).mappings()
                    if r["id"] not in body.excluded_ids
                ]
                if len(rows) > 10000:
                    raise Problem(422, "SELECTION_LIMIT", "选集超过10000项，请缩小范围")
                for row in rows:
                    record_permission(c, store, actor, kind, row, True)
            frozen = {
                "id": identifier(),
                "actor": actor,
                "kind": kind,
                "project": project or None,
                "action": body.action,
                "created": time.time(),
                "items": [
                    {
                        "id": r["id"],
                        "revision": meta(c, kind, r)["revision"],
                        "source_version": source_version(r),
                        "name": present(c, kind, r)["name"],
                    }
                    for r in rows
                ],
            }
            c.execute(insert(frozen_sets).values(**frozen))
            return {
                "id": frozen["id"],
                "count": len(rows),
                "items": frozen["items"],
                "action": body.action,
                "impact": (
                    "逻辑状态变更；原件、运行产物、成员与历史审计保留。"
                    "运行依赖及权限在执行时逐项复验。"
                ),
            }

    @routes.post("/api/management/selections/{selection_id}/apply")
    def apply(selection_id: str, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            frozen = (
                c.execute(
                    select(frozen_sets)
                    .where(frozen_sets.c.id == selection_id, frozen_sets.c.actor == actor)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if not frozen:
                raise Problem(404, "SELECTION_UNAVAILABLE", "选集不可用")
            if frozen["result"] is not None:
                return frozen["result"]
            if time.time() - frozen["created"] > 600:
                raise Problem(409, "SELECTION_EXPIRED", "选集已过期，请重新核对")
            results = []
            for item in frozen["items"]:
                try:
                    with c.begin_nested():
                        row = get_record(c, store, actor, frozen["kind"], item["id"], True)
                        current = meta(c, frozen["kind"], row)
                        if (
                            current["revision"] != item["revision"]
                            or source_version(row) != item["source_version"]
                        ):
                            raise Problem(409, "RECORD_CONFLICT", "记录在确认后已改变")
                        state = lifecycle(c, store, actor, frozen["kind"], row, frozen["action"])
                        write_meta(c, frozen["kind"], row, current, {"state": state})
                        audit_event(
                            c,
                            actor,
                            row.get(
                                "project_id", row["id"] if frozen["kind"] == "projects" else None
                            ),
                            frozen["action"] + "_" + frozen["kind"],
                            row["id"],
                        )
                        results.append({"id": row["id"], "status": "succeeded"})
                except Problem as exc:
                    results.append(
                        {
                            "id": item["id"],
                            "status": "failed",
                            "code": exc.code,
                            "message": exc.message,
                        }
                    )
                except IntegrityError:
                    results.append(
                        {
                            "id": item["id"],
                            "status": "failed",
                            "code": "RECORD_CONFLICT",
                            "message": "记录并发更新，请重新读取",
                        }
                    )
            count = sum(r["status"] == "succeeded" for r in results)
            result = {"items": results, "succeeded": count, "failed": len(results) - count}
            c.execute(
                update(frozen_sets).where(frozen_sets.c.id == selection_id).values(result=result)
            )
            return result

    return routes
