"""Publish partial scientific definitions from saved, actual task bindings."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field, ValidationError
from sqlalchemy import select

from .contracts import Contract, TaskDraft
from .intake import Intake
from .method_authoring import PublishMethod
from .reuse import MappingRule, Reuse, TemplateSpec, templates, write_draft_template
from .store import Problem


class DefinitionEditor(Contract):
    basis: str = Field(min_length=1, max_length=10000)
    scope: Literal["files", "same_names"] = "files"


def definition_spec(draft, assets):
    editor = DefinitionEditor.model_validate(draft["options"].get("semantic_definition", {}))
    by_id = {asset["id"]: asset for asset in assets}
    paths = {
        asset["id"]: {
            layer["name"] + "/" + field["name"]
            for layer in asset["facts"]["layers"]
            for field in layer["fields"]
        }
        for asset in assets
    }
    rules, used = {}, set()
    for binding in draft["mapping"]:
        if binding["asset_id"] not in paths or binding["field"] not in paths[binding["asset_id"]]:
            raise Problem(422, "FIELD_NOT_IN_SOURCE", "定义只能引用本任务实际文件中的字段")
        known = {key: binding[key] for key in ("concept", "unit", "support") if binding.get(key)}
        if not known:
            continue
        rule = MappingRule(field=binding["field"], **known).model_dump(mode="json")
        if binding["field"] in rules and rules[binding["field"]] != rule:
            raise Problem(
                422, "DEFINITION_CONFLICT", "同名字段有不同科学含义，请按适用资料分组维护"
            )
        rules[binding["field"]] = rule
        used.add(binding["asset_id"])
    if not rules:
        raise Problem(422, "DEFINITION_EMPTY", "至少补充一个已知的科学含义、单位或观测支撑")
    sources = [by_id[key] for key in sorted(used)]
    if len({asset["facts"]["profile"] for asset in sources}) != 1 or any(
        paths[asset["id"]] != paths[sources[0]["id"]] for asset in sources
    ):
        raise Problem(422, "DEFINITION_SCOPE", "本组资料的格式或字段结构不同，请分别维护其定义")
    scope = (
        {"asset_sha256": sorted({asset["sha256"] for asset in sources})}
        if editor.scope == "files"
        else {
            "exact_filenames": sorted({asset["name"] for asset in sources}),
            "required_fields": sorted(paths[sources[0]["id"]]),
            "standard_versions": sorted(
                {
                    asset["facts"]["standard_version"]
                    for asset in sources
                    if asset["facts"]["standard_version"]
                }
            ),
        }
    )
    return TemplateSpec(
        title=draft["title"][:190] + " · 指标定义",
        purpose="semantic",
        profiles=[sources[0]["facts"]["profile"]],
        scope=scope,
        basis=editor.basis,
        rules=list(rules.values()),
    ), sources


def router(store):
    routes = APIRouter()

    @routes.post("/api/tasks/{task_id}/publish-definition", status_code=201)
    def publish(task_id: str, body: PublishMethod, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            task = store.task(actor, task_id, write=True, connection=c)
            store.permission(c, actor, task["project_id"], write=True, manage=body.approve)
            draft = TaskDraft.model_validate(task["draft"]).model_dump(mode="json")
            previous = draft["options"].get("definition_publication", {})
            if (
                previous.get("origin_revision") == body.expected_revision
                and task["revision"] == body.expected_revision + 1
                and previous.get("approve") == body.approve
            ):
                entry = (
                    c.execute(
                        select(templates).where(
                            templates.c.id == previous["template_id"],
                            templates.c.project_id == task["project_id"],
                        )
                    )
                    .mappings()
                    .one()
                )
                return {"template": dict(entry), "task": task}
            if task["revision"] != body.expected_revision:
                raise Problem(409, "DRAFT_CONFLICT", "任务已有新版本，请核对后保存定义")
            assets = [
                Intake(store).read_asset(actor, ref["asset_id"], c) for ref in draft["selection"]
            ]
            if any(asset["project_id"] != task["project_id"] for asset in assets):
                raise Problem(422, "PROJECT_MISMATCH", "定义不能跨项目绑定资料")
            try:
                spec, sources = definition_spec(draft, assets)
            except ValidationError as exc:
                raise Problem(
                    422,
                    "DEFINITION_INVALID",
                    "请检查定义依据、适用范围及科学单位",
                    {
                        "fields": [
                            {"path": ".".join(map(str, e["loc"])), "message": e["msg"]}
                            for e in exc.errors(include_context=False, include_input=False)
                        ]
                    },
                ) from exc
            entry = write_draft_template(c, actor, task["project_id"], spec, previous, body.approve)
            draft["options"]["definition_publication"] = {
                "template_id": entry["id"],
                "template_revision": entry["revision"],
                "origin_revision": task["revision"],
                "approve": body.approve,
            }
            if body.approve:
                for asset in sources:
                    suggested = Reuse(store).suggestions(
                        actor, asset["id"], asset=asset, connection=c
                    )
                    contradictions = [
                        issue
                        for issue in suggested["issues"]
                        if issue["code"] in {"FILE_TEMPLATE_CONFLICT", "SEMANTIC_CONFLICT"}
                    ]
                    if contradictions:
                        raise Problem(
                            422,
                            "FILE_DEFINITION_CONFLICT",
                            "定义不能覆盖文件中不兼容的科学事实",
                            {"issues": contradictions},
                        )
                    lookup = {binding["field"]: binding for binding in suggested["applied"]}
                    for binding in draft["mapping"]:
                        if binding["asset_id"] == asset["id"] and binding["field"] in lookup:
                            # Preserve task-specific response/identity choices.
                            role = binding["role"]
                            binding.update(lookup[binding["field"]])
                            binding["role"] = role
                    for key in ("adaptations", "mapping_issues"):
                        draft["options"].setdefault(key, {})[asset["id"]] = suggested[
                            "issues" if key == "mapping_issues" else key
                        ]
            saved = store.save_task(
                actor,
                task_id,
                task["revision"],
                TaskDraft.model_validate(draft).model_dump(mode="json"),
                connection=c,
            )
            return {"template": entry, "task": saved}

    return routes
