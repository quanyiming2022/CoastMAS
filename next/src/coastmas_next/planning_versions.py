"""Independent versioned planning objects; no PlanningProblem parent prerequisite."""

import copy
import hashlib
import json
import re
import time
from typing import Literal

from fastapi import APIRouter, Query, Request, Response
from pydantic import Field
from sqlalchemy import (
    DDL,
    JSON,
    Column,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Table,
    UniqueConstraint,
    event,
    func,
    insert,
    select,
    update,
)

from .contracts import Contract
from .management_catalog import require_available
from .planning_recipes import SCHEMAS, VERSION, catalog, validate_body
from .store import Problem, audit_event, identifier, metadata

Kind = Literal["objectives", "constraints", "decisions"]


def immutable(table):
    # Guards also protect against accidental maintenance SQL, not just API writes.
    for action in ("UPDATE", "DELETE"):
        event.listen(
            table,
            "after_create",
            DDL(
                f"CREATE TRIGGER {table.name}_{action.lower()}_immutable "
                f"BEFORE {action} ON {table.name} BEGIN "
                "SELECT RAISE(ABORT, 'published planning revision is immutable'); END"
            ).execute_if(dialect="sqlite"),
        )
    event.listen(
        table,
        "after_create",
        DDL(
            f"CREATE FUNCTION {table.name}_immutable() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION "
            "'published planning revision is immutable'; END $$"
        ).execute_if(dialect="postgresql"),
    )
    event.listen(
        table,
        "after_create",
        DDL(
            f"CREATE TRIGGER {table.name}_immutable BEFORE UPDATE OR DELETE "
            f"ON {table.name} FOR EACH ROW EXECUTE FUNCTION {table.name}_immutable()"
        ).execute_if(dialect="postgresql"),
    )


def family(name, revision_name, member_name):
    objects = Table(
        name,
        metadata,
        Column("id", String, primary_key=True),
        Column("project_id", ForeignKey("projects.id"), nullable=False),
        Column("name", String, nullable=False),
        Column("revision", Integer, nullable=False),
        Column("body", JSON, nullable=False),
        Column("created", Float, nullable=False),
        Column("updated", Float, nullable=False),
        UniqueConstraint("id", "project_id"),
    )
    versions = Table(
        revision_name,
        metadata,
        Column("id", String, primary_key=True),
        Column("object_id", String, nullable=False),
        Column("project_id", String, nullable=False),
        Column("version", Integer, nullable=False),
        Column("draft_revision", Integer, nullable=False),
        Column("name", String, nullable=False),
        Column("body", JSON, nullable=False),
        Column("sha256", String, nullable=False),
        Column("recipe_version", String, nullable=False),
        Column("validation_state", String, nullable=False),
        Column("actor", ForeignKey("accounts.id"), nullable=False),
        Column("created", Float, nullable=False),
        ForeignKeyConstraint(["object_id", "project_id"], [name + ".id", name + ".project_id"]),
        UniqueConstraint("object_id", "version"),
        UniqueConstraint("object_id", "draft_revision"),
    )
    items = Table(
        member_name,
        metadata,
        Column("revision_id", ForeignKey(revision_name + ".id"), primary_key=True),
        Column("position", Integer, primary_key=True),
        Column("body", JSON, nullable=False),
    )
    for table in (versions, items):
        immutable(table)
    return objects, versions, items


TABLES = {
    "objectives": family("objective_sets", "objective_set_revisions", "objective_items"),
    "constraints": family("constraint_sets", "constraint_set_revisions", "constraint_items"),
    "decisions": family("decision_specs", "decision_spec_revisions", "decision_variables"),
}


class NewObject(Contract):
    name: str = Field(min_length=1, max_length=240)


class SaveObject(NewObject):
    body: dict


class BindObject(Contract):
    kind: Kind
    object_id: str
    version_id: str


def expected_revision(request):
    value = request.headers.get("If-Match")
    if value is None:
        raise Problem(428, "REVISION_REQUIRED", "保存需要当前版本，请重新读取后操作")
    if not re.fullmatch(r'"[1-9][0-9]*"', value):
        raise Problem(422, "REVISION_INVALID", "版本格式不正确")
    return int(value[1:-1])


def read_object(c, store, actor, project, kind, object_id, write=False):
    store.permission(c, actor, project, write=write)
    if write:
        require_available(c, "projects", project)
    objects, versions, _ = TABLES[kind]
    row = (
        c.execute(select(objects).where(objects.c.id == object_id, objects.c.project_id == project))
        .mappings()
        .first()
    )
    if not row:
        raise Problem(404, "PLANNING_OBJECT_UNAVAILABLE", "此规划对象不可用")
    return {
        **dict(row),
        "kind": kind,
        "versions": [
            dict(r)
            for r in c.execute(
                select(
                    versions.c.id,
                    versions.c.version,
                    versions.c.name,
                    versions.c.sha256,
                    versions.c.draft_revision,
                )
                .where(versions.c.object_id == object_id)
                .order_by(versions.c.version.desc())
            ).mappings()
        ],
    }


def require_revision(c, objects, current, expected):
    if current["revision"] != expected:
        raise Problem(
            412,
            "PLANNING_CONFLICT",
            "其他成员已更新，请比较后继续；本地编辑未被覆盖",
            {"current": current},
        )
    # Acquire the write lock before freezing. A concurrent draft save must wait
    # or fail CAS; a publication cannot combine two revisions.
    result = c.execute(
        update(objects)
        .where(objects.c.id == current["id"], objects.c.revision == expected)
        .values(revision=expected)
    )
    if result.rowcount != 1:
        latest = c.execute(select(objects).where(objects.c.id == current["id"])).mappings().one()
        raise Problem(
            412, "PLANNING_CONFLICT", "其他成员已更新，请比较后继续", {"current": dict(latest)}
        )


def router(store):
    routes = APIRouter()

    @routes.get("/api/v1/projects/{project}/planning-catalog")
    def recipes(project: str, request: Request):
        with store.engine.connect() as c:
            store.permission(c, request.state.actor["id"], project)
        return catalog()

    @routes.get("/api/v1/projects/{project}/planning/{kind}")
    def listing(
        project: str,
        kind: Kind,
        request: Request,
        search: str = "",
        sort: Literal["updated", "name"] = "updated",
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        with store.engine.connect() as c:
            role = store.permission(c, request.state.actor["id"], project)
            objects, _, _ = TABLES[kind]
            condition = (objects.c.project_id == project) & objects.c.name.contains(
                search, autoescape=True
            )
            total = c.scalar(select(func.count()).select_from(objects).where(condition))
            order = objects.c.name.asc() if sort == "name" else objects.c.updated.desc()
            rows = c.execute(
                select(objects.c.id)
                .where(condition)
                .order_by(order, objects.c.id)
                .limit(limit)
                .offset(offset)
            ).scalars()
            return {
                "items": [
                    read_object(c, store, request.state.actor["id"], project, kind, id)
                    for id in rows
                ],
                "total": total,
                "can_edit": role != "viewer",
            }

    @routes.post("/api/v1/projects/{project}/planning/{kind}", status_code=201)
    def create(project: str, kind: Kind, body: NewObject, request: Request, response: Response):
        with store.engine.begin() as c:
            actor = request.state.actor["id"]
            store.permission(c, actor, project, write=True)
            require_available(c, "projects", project)
            id, now = identifier(), time.time()
            name = body.name.strip()
            if not name:
                raise Problem(422, "NAME_REQUIRED", "请填写名称")
            c.execute(
                insert(TABLES[kind][0]).values(
                    id=id,
                    project_id=project,
                    name=name,
                    revision=1,
                    body=SCHEMAS[kind]().model_dump(exclude_none=True),
                    created=now,
                    updated=now,
                )
            )
            audit_event(c, actor, project, "planning_create_" + kind, id)
            response.headers["ETag"] = '"1"'
            return read_object(c, store, actor, project, kind, id)

    @routes.get("/api/v1/projects/{project}/planning/{kind}/{id}")
    def read(project: str, kind: Kind, id: str, request: Request, response: Response):
        with store.engine.connect() as c:
            result = read_object(c, store, request.state.actor["id"], project, kind, id)
            response.headers["ETag"] = f'"{result["revision"]}"'
            return result

    @routes.put("/api/v1/projects/{project}/planning/{kind}/{id}")
    def save(
        project: str, kind: Kind, id: str, body: SaveObject, request: Request, response: Response
    ):
        revision = expected_revision(request)
        value = validate_body(kind, body.body)
        if not body.name.strip():
            raise Problem(422, "NAME_REQUIRED", "请填写名称")
        with store.engine.begin() as c:
            actor = request.state.actor["id"]
            current = read_object(c, store, actor, project, kind, id, True)
            objects = TABLES[kind][0]
            require_revision(c, objects, current, revision)
            c.execute(
                update(objects)
                .where(objects.c.id == id)
                .values(
                    name=body.name.strip(), body=value, revision=revision + 1, updated=time.time()
                )
            )
            audit_event(c, actor, project, "planning_save_" + kind, id)
            response.headers["ETag"] = f'"{revision + 1}"'
            return read_object(c, store, actor, project, kind, id)

    @routes.post("/api/v1/projects/{project}/planning/{kind}/{id}/versions", status_code=201)
    def publish(project: str, kind: Kind, id: str, request: Request):
        revision = expected_revision(request)
        with store.engine.begin() as c:
            actor = request.state.actor["id"]
            current = read_object(c, store, actor, project, kind, id, True)
            objects, versions, items = TABLES[kind]
            require_revision(c, objects, current, revision)
            value = validate_body(kind, current["body"], True)
            existing = (
                c.execute(
                    select(versions).where(
                        versions.c.object_id == id, versions.c.draft_revision == revision
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                return dict(existing)
            frozen = {"name": current["name"], "body": value, "recipe_version": VERSION}
            sha = hashlib.sha256(
                json.dumps(
                    frozen,
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            result = {
                "id": identifier(),
                "object_id": id,
                "project_id": project,
                "version": 1
                + (
                    c.scalar(select(func.max(versions.c.version)).where(versions.c.object_id == id))
                    or 0
                ),
                "draft_revision": revision,
                **frozen,
                "sha256": sha,
                "validation_state": "configuration_validated",
                "actor": actor,
                "created": time.time(),
            }
            c.execute(insert(versions).values(**result))
            members = value.get(
                "items",
                [
                    {"template": value.get("template"), "action": action}
                    for action in value.get("actions", [])
                ],
            )
            for position, member in enumerate(members):
                c.execute(
                    insert(items).values(revision_id=result["id"], position=position, body=member)
                )
            audit_event(c, actor, project, "planning_publish_" + kind, result["id"])
            return result

    @routes.get("/api/v1/projects/{project}/planning/{kind}/{id}/versions/{version_id}")
    def version(project: str, kind: Kind, id: str, version_id: str, request: Request):
        with store.engine.connect() as c:
            read_object(c, store, request.state.actor["id"], project, kind, id)
            table = TABLES[kind][1]
            result = (
                c.execute(
                    select(table).where(
                        table.c.id == version_id,
                        table.c.object_id == id,
                        table.c.project_id == project,
                    )
                )
                .mappings()
                .first()
            )
            if not result:
                raise Problem(
                    404, "PLANNING_VERSION_UNAVAILABLE", "固定版本不可用，不会替换为最新版本"
                )
            return dict(result)

    @routes.post("/api/v1/tasks/{task_id}/planning/bindings")
    def bind(task_id: str, body: BindObject, request: Request):
        expected = expected_revision(request)
        with store.engine.begin() as c:
            actor = request.state.actor["id"]
            task = store.task(actor, task_id, True, c)
            if task["draft"]["options"].get("task_type") != "planning":
                raise Problem(422, "PLANNING_TASK_REQUIRED", "此配置只能应用到规划任务")
            if task["revision"] != expected:
                raise Problem(
                    412, "PLANNING_CONFLICT", "研究配置已更新，请核对后应用", {"current": task}
                )
            read_object(c, store, actor, task["project_id"], body.kind, body.object_id)
            table = TABLES[body.kind][1]
            fixed = (
                c.execute(
                    select(table).where(
                        table.c.id == body.version_id,
                        table.c.object_id == body.object_id,
                        table.c.project_id == task["project_id"],
                    )
                )
                .mappings()
                .first()
            )
            if not fixed:
                raise Problem(404, "PLANNING_VERSION_UNAVAILABLE", "请选择已发布的固定配置版本")
            draft = copy.deepcopy(task["draft"])
            draft["options"].setdefault("planning_refs", {})[body.kind] = {
                "object_id": body.object_id,
                "version_id": body.version_id,
                "version": fixed["version"],
                "name": fixed["name"],
                "sha256": fixed["sha256"],
                "recipe_version": fixed["recipe_version"],
            }
            try:
                saved = store.save_task(actor, task_id, expected, draft, c)
            except Problem as exc:
                if exc.code != "DRAFT_CONFLICT":
                    raise
                current = store.task(actor, task_id, connection=c)
                raise Problem(
                    412, "PLANNING_CONFLICT", "研究配置已更新，请比较后应用", {"current": current}
                ) from exc
            audit_event(c, actor, task["project_id"], "planning_apply_" + body.kind, task_id)
            return saved

    return routes
