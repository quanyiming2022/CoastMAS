"""Project-scoped method workspaces; no research created by maintaining a method."""

import copy
import json
import math
import os
import time
from typing import Annotated, Literal

import yaml
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import Field, StrictBool, ValidationError
from sqlalchemy import (
    JSON,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    insert,
    select,
    update,
)

from .contracts import Contract, TaskDraft
from .decisions import AssessmentMethod, OptimizationMethod
from .management_catalog import require_available
from .method_documents import FORMAT, VERSION, parse_method
from .method_validation import business_issues, validate_draft
from .reuse import TemplateSpec, template_history, templates, write_draft_template
from .store import Problem, audit_event, identifier, metadata

method_edits = Table(
    "method_workspaces",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", ForeignKey("projects.id")),
    Column("actor", ForeignKey("accounts.id")),
    Column("revision", Integer, nullable=False),
    Column("definition", JSON, nullable=False),
    Column("provenance", JSON, nullable=False),
    Column("publication", JSON),
    Column("base", JSON, nullable=False),
    Column("updated", Float, nullable=False),
)


class Definition(Contract):
    definition: dict


class Edit(Definition):
    expected_revision: int = Field(ge=1)


class Publication(Contract):
    expected_revision: int = Field(ge=1)
    approve: StrictBool = False


class OpenMethod(Contract):
    revision: int = Field(ge=1)
    mode: Literal["clone", "revise"]


def bounded(value):
    if set(value) - set(TemplateSpec.model_fields):
        raise Problem(422, "METHOD_FIELDS", "存在未知方法字段，不能默默忽略")
    try:
        TaskDraft.bounded_non_secret_options(value)
    except ValueError as exc:
        raise Problem(422, "METHOD_DOCUMENT", "方法草稿过大、嵌套过深或包含敏感配置") from exc
    validate_draft(value)
    return copy.deepcopy(value)


def method_version(connection, method_id, revision, *, approved=False):
    current = (
        connection.execute(select(templates).where(templates.c.id == method_id)).mappings().first()
    )
    if current is None or current["spec"]["purpose"] != "method":
        raise Problem(404, "METHOD_UNAVAILABLE", "方法不可用")
    require_available(connection, "methods", method_id, lock=False)
    if revision == current["revision"]:
        result = dict(current)
    else:
        historical = (
            connection.execute(
                select(template_history).where(
                    template_history.c.template_id == method_id,
                    template_history.c.revision == revision,
                )
            )
            .mappings()
            .first()
        )
        if not historical:
            raise Problem(404, "METHOD_VERSION", "方法版本不存在")
        result = {
            **dict(current),
            "revision": revision,
            "spec": historical["spec"],
            "approved": bool(historical["approved_by"]),
            "approved_by": historical["approved_by"],
        }
    if approved and not result["approved"]:
        raise Problem(422, "METHOD_CHANGED", "此方法版本尚未认可或已撤销认可")
    return result


def router(store):
    routes = APIRouter()

    def read(c, actor, key, write=False):
        item = c.execute(select(method_edits).where(method_edits.c.id == key)).mappings().first()
        if not item:
            raise Problem(404, "METHOD_WORKSPACE", "方法草稿不可用")
        store.permission(c, actor, item["project_id"], write=write)
        if write:
            require_available(c, "projects", item["project_id"])
        return dict(item)

    def create(c, actor, project, definition, provenance=None, base=None):
        store.permission(c, actor, project, write=True)
        require_available(c, "projects", project)
        item = {
            "id": identifier(),
            "project_id": project,
            "actor": actor,
            "revision": 1,
            "definition": bounded(definition),
            "provenance": provenance or {},
            "base": base or {},
            "publication": None,
            "updated": time.time(),
        }
        c.execute(insert(method_edits).values(**item))
        audit_event(c, actor, project, "create_method_workspace", item["id"])
        return item

    @routes.post("/api/projects/{project}/method-workspaces", status_code=201)
    def new(project: str, body: Definition, request: Request):
        with store.engine.begin() as c:
            return create(c, request.state.actor["id"], project, body.definition)

    @routes.get("/api/projects/{project}/method-workspaces")
    def listing(project: str, request: Request):
        with store.engine.connect() as c:
            store.permission(c, request.state.actor["id"], project)
            return [
                dict(r)
                for r in c.execute(
                    select(method_edits)
                    .where(method_edits.c.project_id == project)
                    .order_by(method_edits.c.updated.desc())
                    .limit(100)
                ).mappings()
            ]

    @routes.get("/api/method-workspaces/{key}")
    def get(key: str, request: Request):
        with store.engine.connect() as c:
            return read(c, request.state.actor["id"], key)

    @routes.put("/api/method-workspaces/{key}")
    def save(key: str, body: Edit, request: Request):
        with store.engine.begin() as c:
            actor = request.state.actor["id"]
            item = read(c, actor, key, True)
            values = {
                "definition": bounded(body.definition),
                "revision": body.expected_revision + 1,
                "updated": time.time(),
            }
            changed = c.execute(
                update(method_edits)
                .where(method_edits.c.id == key, method_edits.c.revision == body.expected_revision)
                .values(**values)
            ).rowcount
            if changed != 1:
                raise Problem(
                    409,
                    "METHOD_DRAFT_CONFLICT",
                    "另一窗口已修改方法，请读取最新草稿后核对",
                    {"current_revision": item["revision"]},
                )
            audit_event(c, actor, item["project_id"], "save_method_workspace", key)
            return {**item, **values}

    @routes.post("/api/method-workspaces/{key}/publish", status_code=201)
    def publish(key: str, body: Publication, request: Request):
        with store.engine.begin() as c:
            actor = request.state.actor["id"]
            item = read(c, actor, key, True)
            store.permission(c, actor, item["project_id"], manage=body.approve, write=True)
            receipt = item["publication"]
            if receipt and receipt["origin_revision"] == body.expected_revision:
                if receipt["approve"] != body.approve:
                    raise Problem(409, "METHOD_PUBLICATION_INTENT", "同一发布不能更改认可意图")
                return {
                    "workspace": item,
                    "template": method_version(
                        c, receipt["template_id"], receipt["template_revision"]
                    ),
                }
            if item["revision"] != body.expected_revision:
                raise Problem(409, "METHOD_DRAFT_CONFLICT", "方法草稿已变化，请核对后发布")
            try:
                spec = TemplateSpec.model_validate(item["definition"])
                if spec.purpose != "method":
                    raise ValueError("必须为方法方案")
                schema = {"assessment": AssessmentMethod, "optimization": OptimizationMethod}.get(
                    spec.configuration.get("task")
                )
                if schema is None:
                    raise ValueError("该研究目标的方法编译器尚未实现，不可假发布")
                config = schema.model_validate(spec.configuration)
                if isinstance(config, AssessmentMethod) and config.method != "entropy":
                    if not math.isclose(
                        sum(i.weight for i in config.indicators), 1.0, abs_tol=1e-8
                    ):
                        raise ValueError("明确权重之和必须为1；不会自动改写科学权重")
                spec.configuration = config.model_dump(mode="json")
            except (ValueError, ValidationError) as exc:
                raise Problem(
                    422,
                    "METHOD_DEFINITION",
                    "草稿已保存，尚未发布。请处理标出的项目。",
                    {"issues": business_issues(exc)},
                ) from exc
            previous = item["base"]
            entry = write_draft_template(c, actor, item["project_id"], spec, previous, body.approve)
            receipt = {
                "origin_revision": item["revision"],
                "template_id": entry["id"],
                "template_revision": entry["revision"],
                "approve": body.approve,
            }
            saved = {
                **item,
                "publication": receipt,
                "base": {"template_id": entry["id"], "template_revision": entry["revision"]},
                "revision": item["revision"] + 1,
            }
            count = c.execute(
                update(method_edits)
                .where(method_edits.c.id == key, method_edits.c.revision == item["revision"])
                .values(publication=receipt, base=saved["base"], revision=saved["revision"])
            ).rowcount
            if count != 1:
                raise Problem(409, "METHOD_DRAFT_CONFLICT", "发布期间草稿发生变化")
            return {"workspace": saved, "template": entry}

    @routes.post("/api/methods/{method_id}/edit", status_code=201)
    def open_version(method_id: str, body: OpenMethod, request: Request):
        with store.engine.begin() as c:
            entry = method_version(c, method_id, body.revision)
            store.permission(c, request.state.actor["id"], entry["project_id"], write=True)
            base = (
                {"template_id": method_id, "template_revision": body.revision}
                if body.mode == "revise"
                else {}
            )
            definition = copy.deepcopy(entry["spec"])
            if body.mode == "clone":
                definition["title"] += " · 副本"
            return create(
                c,
                request.state.actor["id"],
                entry["project_id"],
                definition,
                {"copied_from": method_id, "revision": body.revision, "mode": body.mode},
                base,
            )

    @routes.get("/api/methods/{method_id}/versions/{revision}")
    def fixed_version(method_id: str, revision: int, request: Request):
        with store.engine.connect() as c:
            entry = method_version(c, method_id, revision)
            store.permission(c, request.state.actor["id"], entry["project_id"])
            return entry

    @routes.get("/api/methods/{method_id}/versions/{revision}/export")
    def export(
        method_id: str, revision: int, request: Request, format: Literal["json", "yaml"] = "json"
    ):
        with store.engine.connect() as c:
            entry = method_version(c, method_id, revision)
            store.permission(c, request.state.actor["id"], entry["project_id"])
        value = {"format": FORMAT, "version": VERSION, "definition": entry["spec"]}
        payload = (
            json.dumps(value, ensure_ascii=False, indent=2)
            if format == "json"
            else yaml.safe_dump(value, allow_unicode=True, sort_keys=False)
        )
        return Response(
            payload,
            media_type="application/json" if format == "json" else "application/yaml",
            headers={"Content-Disposition": f'attachment; filename="method-v{revision}.{format}"'},
        )

    @routes.post("/api/projects/{project}/method-imports", status_code=201)
    async def imported(
        project: str,
        request: Request,
        file: Annotated[UploadFile, File()],
        mapping: Annotated[str | None, Form()] = None,
    ):
        with store.engine.connect() as c:
            store.permission(c, request.state.actor["id"], project, write=True)
        content = await file.read(8 * 1024**2 + 1)
        try:
            mapped = json.loads(mapping) if mapping else None
            if mapped is not None and not isinstance(mapped, dict):
                raise ValueError("Expected columns")
        except ValueError as exc:
            raise Problem(422, "METHOD_COLUMNS", "列映射格式不正确") from exc
        definition, provenance = parse_method(file.filename or "", content, mapped)
        bounded(definition)
        source = store.settings.storage_root / "method-sources" / provenance["sha256"]
        source.parent.mkdir(exist_ok=True)
        try:
            with source.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if source.read_bytes() != content:
                raise Problem(
                    409, "METHOD_SOURCE_INTEGRITY", "已有方法原文校验失败，请保留现场并重新接入"
                ) from None
        provenance["object_key"] = str(source.relative_to(store.settings.storage_root))
        with store.engine.begin() as c:
            return create(c, request.state.actor["id"], project, definition, provenance)

    @routes.get("/api/method-workspaces/{key}/source")
    def original_source(key: str, request: Request):
        with store.engine.connect() as c:
            item = read(c, request.state.actor["id"], key)
            key = item["provenance"].get("object_key")
            if not key:
                raise Problem(404, "METHOD_SOURCE", "此草稿不是从文件导入")
            return FileResponse(
                store.settings.storage_root / key,
                filename=item["provenance"]["filename"],
                media_type="application/octet-stream",
            )

    @routes.post("/api/method-workspaces/{key}/indicators:import")
    async def import_indicators(
        key: str,
        request: Request,
        file: Annotated[UploadFile, File()],
        expected_revision: Annotated[int, Form()],
    ):
        actor = request.state.actor["id"]
        with store.engine.connect() as c:
            read(c, actor, key, True)
        content = await file.read(8 * 1024**2 + 1)
        definition, provenance = parse_method(file.filename or "", content)
        bounded(definition)
        rows = definition.get("configuration", {}).get("indicators")
        if not rows:
            raise Problem(422, "METHOD_INDICATORS", "文件没有可导入的评价指标")
        source = store.settings.storage_root / "method-sources" / provenance["sha256"]
        source.parent.mkdir(exist_ok=True)
        try:
            with source.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if source.read_bytes() != content:
                raise Problem(409, "METHOD_SOURCE_INTEGRITY", "方法原文校验失败") from None
        provenance["object_key"] = str(source.relative_to(store.settings.storage_root))
        with store.engine.begin() as c:
            item = read(c, actor, key, True)
            if item["revision"] != expected_revision:
                raise Problem(409, "METHOD_DRAFT_CONFLICT", "草稿已变化，请核对后重新导入")
            changed = copy.deepcopy(item["definition"])
            config = changed["configuration"]
            if config.get("task") != "assessment":
                raise Problem(422, "METHOD_INDICATORS", "此方法不是指标评价方案")
            config["indicators"] = [*config.get("indicators", []), *rows]
            if len(config["indicators"]) > 64:
                raise Problem(422, "METHOD_ROWS", "一个方案最多64项指标")
            bounded(changed)
            values = {
                "definition": changed,
                "revision": expected_revision + 1,
                "updated": time.time(),
                "provenance": {
                    **item["provenance"],
                    "indicator_sources": [
                        *item["provenance"].get("indicator_sources", []),
                        provenance,
                    ],
                },
            }
            count = c.execute(
                update(method_edits)
                .where(method_edits.c.id == key, method_edits.c.revision == expected_revision)
                .values(**values)
            ).rowcount
            if count != 1:
                raise Problem(409, "METHOD_DRAFT_CONFLICT", "草稿已变化，请核对后重新导入")
            audit_event(c, actor, item["project_id"], "import_method_indicators", key)
            return {**item, **values}

    @routes.get("/api/method-workspaces/{key}/sources/{index}")
    def indicator_source(key: str, index: int, request: Request):
        with store.engine.connect() as c:
            row = read(c, request.state.actor["id"], key)
            sources = row["provenance"].get("indicator_sources", [])
            if not 0 <= index < len(sources):
                raise Problem(404, "METHOD_SOURCE", "指标来源不可用")
            source = sources[index]
            return FileResponse(
                store.settings.storage_root / source["object_key"],
                filename=source["filename"],
                media_type="application/octet-stream",
            )

    @routes.get("/api/projects/{project}/indicator-definitions")
    def indicator_library(project: str, request: Request):
        with store.engine.connect() as c:
            store.permission(c, request.state.actor["id"], project)
            result = []
            for row in c.execute(
                select(templates).where(
                    templates.c.project_id == project, templates.c.approved.is_(True)
                )
            ).mappings():
                try:
                    require_available(
                        c,
                        "methods" if row["spec"]["purpose"] == "method" else "templates",
                        row["id"],
                        lock=False,
                    )
                except Problem:
                    continue
                spec = row["spec"]
                definitions = (
                    spec.get("configuration", {}).get("indicators", [])
                    if spec["purpose"] == "method"
                    else spec.get("rules", [])
                    if spec["purpose"] == "semantic"
                    else []
                )
                for index, value in enumerate(definitions):
                    if not value.get("concept"):
                        continue
                    indicator = {
                        key: value.get(key, "" if key in ("concept", "unit") else None)
                        for key in ("concept", "unit", "lower", "upper", "positive", "weight")
                    }
                    result.append(
                        {
                            "id": f"{row['id']}:{row['revision']}:{index}",
                            "source": spec["title"],
                            "revision": row["revision"],
                            "basis": spec["basis"],
                            "indicator": indicator,
                        }
                    )
            return result

    return routes
