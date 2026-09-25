"""Task-aware indicator selection, explicit binding, fixed recipes and existing queue."""

import copy
import time

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import insert, select

from .contracts import Contract, TaskDraft
from .execution import ExecuteRequest, Execution, fingerprint
from .indicator_matching import match, project_assets
from .indicator_registry import definitions, require_definition, validate_parameters
from .matcher_diagnostics import indicator_diagnostics
from .input_transactions import attachment_receipts
from .management_catalog import require_available
from .research_workspace import processing_nodes
from .store import Problem, audit_event, identifier


class ChooseIndicator(Contract):
    indicator_id: str = Field(min_length=1, max_length=100)
    candidate_key: str | None = None
    parameters: dict[str, float] = Field(default_factory=dict)


class ChooseIndicators(ExecuteRequest):
    items: list[ChooseIndicator] = Field(min_length=1, max_length=50)


def public_item(definition, matched):
    return {
        **{k: definition[k] for k in ("indicator_id", "name", "category", "description")},
        **matched,
        "installation_status": definition["status"],
        "business_parameters": definition["business_parameters"],
    }


def bind_sources(draft, chosen, definition):
    for ref in chosen["sources"]:
        current = next((r for r in draft["selection"] if r["asset_id"] == ref["asset_id"]), None)
        if current and current["revision"] != ref["revision"]:
            raise Problem(409, "INPUT_VERSION_CONFLICT", "当前研究已使用这份数据的其他版本")
        if not current:
            draft["selection"].append(
                {"asset_id": ref["asset_id"], "revision": ref["revision"], "layer": None}
            )
    if chosen["mode"] == "existing":
        ref = chosen["sources"][0]
        field = "raster/band_" + str(chosen["bindings"]["band"])
        existing = next(
            (
                m
                for m in draft["mapping"]
                if m["asset_id"] == ref["asset_id"] and m["field"] == field
            ),
            None,
        )
        if existing and existing.get("concept") not in {None, definition["semantic_type"]}:
            raise Problem(409, "INDICATOR_BINDING_CONFLICT", "此字段已绑定其他指标，请核对后再选择")
        binding = {
            "asset_id": ref["asset_id"],
            "field": field,
            "concept": definition["semantic_type"],
            "unit": definition["unit"],
            "role": "feature",
            "support": "grid",
            "template_id": None,
            "template_revision": None,
        }
        if existing:
            existing.update(binding)
        else:
            draft["mapping"].append(binding)


class IndicatorService:
    def __init__(self, store):
        self.store = store

    def catalog(self, actor, task_id):
        with self.store.engine.connect() as c:
            task = self.store.task(actor, task_id, connection=c)
            available = project_assets(c, self.store, actor, task["project_id"])
            return {
                "task_id": task_id,
                "revision": task["revision"],
                "items": [
                    public_item(
                        d,
                        {
                            **match(d, task, available),
                            "diagnostics": indicator_diagnostics(
                                d, match(d, task, available), available
                            ),
                        },
                    )
                    for d in definitions()
                ],
                "selected": task["draft"]["options"].get("indicators", []),
            }

    def project_catalog(self, actor, project):
        with self.store.engine.connect() as c:
            available = project_assets(c, self.store, actor, project)
            context = {"draft": {"selection": [], "options": {}}}
            return {"items": [public_item(d, match(d, context, available)) for d in definitions()]}

    def choose(self, actor, task_id, body):
        digest = fingerprint(body.model_dump())
        with self.store.engine.begin() as c:
            task = self.store.task(actor, task_id, write=True, connection=c)
            require_available(c, "projects", task["project_id"])
            require_available(c, "tasks", task_id)
            intent = "indicator:" + body.idempotency_key
            previous = (
                c.execute(
                    select(attachment_receipts).where(
                        attachment_receipts.c.task_id == task_id,
                        attachment_receipts.c.actor == actor,
                        attachment_receipts.c.intent == intent,
                    )
                )
                .mappings()
                .first()
            )
            if previous:
                if previous["fingerprint"] != digest:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT", "本次操作标识对应其他指标选择")
                return previous["response"]
            if task["revision"] != body.expected_revision:
                raise Problem(409, "DRAFT_CONFLICT", "研究已更新，请重读后选择")
            available = project_assets(c, self.store, actor, task["project_id"])
            draft = copy.deepcopy(task["draft"])
            selections = draft["options"].setdefault("indicators", [])
            results = []
            for item in body.items:
                definition = require_definition(item.indicator_id)
                parameters = validate_parameters(definition, item.parameters)
                matched = match(definition, task, available)
                key = item.candidate_key or matched.get("suggested_key")
                chosen = next((x for x in matched["candidates"] if x["key"] == key), None)
                if item.candidate_key and chosen is None:
                    raise Problem(422, "INDICATOR_CANDIDATE", "选择的数据来源已失效，请重新匹配")
                existing = next(
                    (s for s in selections if s["indicator_id"] == item.indicator_id), None
                )
                value = {
                    "selection_id": existing["selection_id"] if existing else identifier(),
                    "indicator_id": item.indicator_id,
                    "definition_version": definition["version"],
                    "definition": definition,
                    "parameters": parameters,
                    "candidate": chosen,
                    "status": chosen["status"] if chosen else matched["status"],
                    "mode": chosen["mode"] if chosen else None,
                }
                if chosen:
                    bind_sources(draft, chosen, definition)
                if existing:
                    selections[selections.index(existing)] = value
                else:
                    selections.append(value)
                results.append(value)
            task = self.store.save_task(
                actor,
                task_id,
                task["revision"],
                TaskDraft.model_validate(draft).model_dump(mode="json"),
                c,
            )
            response = {"task": task, "items": results}
            c.execute(
                insert(attachment_receipts).values(
                    task_id=task_id,
                    actor=actor,
                    intent=intent,
                    fingerprint=digest,
                    response=response,
                )
            )
            audit_event(c, actor, task["project_id"], "select_builtin_indicators", task_id)
            return response

    def execute(self, actor, task_id, selection_id, body):
        intent = "indicator-run:" + body.idempotency_key
        with self.store.engine.begin() as c:
            task = self.store.task(actor, task_id, write=True, connection=c)
            require_available(c, "projects", task["project_id"])
            require_available(c, "tasks", task_id)
            if task["revision"] != body.expected_revision:
                raise Problem(409, "DRAFT_CONFLICT", "请先保存当前研究")
            selection = next(
                (
                    x
                    for x in task["draft"]["options"].get("indicators", [])
                    if x["selection_id"] == selection_id
                ),
                None,
            )
            if selection is None:
                raise Problem(404, "INDICATOR_SELECTION", "指标未加入此研究")
            definition = require_definition(
                selection["indicator_id"], selection["definition_version"]
            )
            selected = copy.deepcopy(selection)
            available = project_assets(c, self.store, actor, task["project_id"])
            matched = match(definition, task, available)
            key = (
                selection["candidate"]["key"]
                if selection["candidate"]
                else matched.get("suggested_key")
            )
            chosen = next(
                (x for x in matched["candidates"] if x["key"] == key and x["status"] == "ready"),
                None,
            )
            if not chosen:
                raise Problem(
                    422,
                    "INDICATOR_INPUT",
                    matched["message"],
                    {"missing": matched["missing"], "candidates": matched["candidates"]},
                )
            if chosen["mode"] == "existing":
                raise Problem(422, "INDICATOR_REUSE", "已有指标已引用，无需重复计算")
            selected["candidate"] = chosen
            if selection["candidate"] != chosen:
                draft = copy.deepcopy(task["draft"])
                bind_sources(draft, chosen, definition)
                draft["options"]["indicators"] = [
                    selected if s["selection_id"] == selection_id else s
                    for s in draft["options"]["indicators"]
                ]
                task = self.store.save_task(
                    actor,
                    task_id,
                    task["revision"],
                    TaskDraft.model_validate(draft).model_dump(mode="json"),
                    c,
                )
            draft = TaskDraft(
                title=definition["name"],
                purpose="spatial",
                selection=[
                    {"asset_id": r["asset_id"], "revision": r["revision"]}
                    for r in chosen["sources"]
                ],
                options={"operator": "builtin_indicator", "indicator_selection": selected},
            ).model_dump(mode="json")
            digest = fingerprint({"selection_id": selection_id, "draft": draft})
            previous = (
                c.execute(
                    select(processing_nodes).where(
                        processing_nodes.c.task_id == task_id,
                        processing_nodes.c.actor == actor,
                        processing_nodes.c.intent == intent,
                    )
                )
                .mappings()
                .first()
            )
            if previous:
                if previous["fingerprint"] != digest:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT", "本次运行标识对应其他指标配置")
                node_id = previous["id"]
            else:
                node_id = identifier()
                c.execute(
                    insert(processing_nodes).values(
                        id=node_id,
                        task_id=task_id,
                        actor=actor,
                        intent=intent,
                        fingerprint=digest,
                        draft=draft,
                        created=time.time(),
                    )
                )
                audit_event(c, actor, task["project_id"], "prepare_indicator", node_id)
        return Execution(self.store).enqueue(
            actor, task_id, task["revision"], intent, node_id=node_id
        )


def router(store):
    routes = APIRouter()
    service = IndicatorService(store)

    @routes.get("/api/v1/projects/{project}/indicators")
    def project_catalog(project: str, request: Request):
        return service.project_catalog(request.state.actor["id"], project)

    @routes.get("/api/v1/tasks/{task_id}/indicators")
    def catalog(task_id: str, request: Request):
        return service.catalog(request.state.actor["id"], task_id)

    @routes.post("/api/v1/tasks/{task_id}/indicators")
    def choose(task_id: str, body: ChooseIndicators, request: Request):
        return service.choose(request.state.actor["id"], task_id, body)

    @routes.post("/api/v1/tasks/{task_id}/indicators/{selection_id}/execute", status_code=202)
    def execute(task_id: str, selection_id: str, body: ExecuteRequest, request: Request):
        return service.execute(request.state.actor["id"], task_id, selection_id, body)

    return routes
