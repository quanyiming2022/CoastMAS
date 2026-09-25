"""Publish reviewed methods from durable drafts, with atomic revision protection."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field, StrictBool, ValidationError
from sqlalchemy import select

from .contracts import Contract, TaskDraft
from .decisions import AssessmentMethod, OptimizationMethod
from .reuse import TemplateSpec, templates, write_draft_template
from .store import Problem


class NewMethodDraft(Contract):
    title: str = Field(min_length=1, max_length=200)
    purpose: Literal["assessment", "optimization"]


class PublishMethod(Contract):
    expected_revision: int = Field(ge=1)
    approve: StrictBool = False


def router(store):
    routes = APIRouter()

    @routes.post("/api/projects/{project}/method-drafts", status_code=201)
    def create(project: str, body: NewMethodDraft, request: Request):
        draft = TaskDraft(
            title=body.title,
            purpose=body.purpose,
            options={
                "editor": "method",
                "definition": {
                    "basis": "",
                    "profiles": ["csv", "csvw", "geojson", "geopackage", "shapefile"],
                    "configuration": {"task": body.purpose},
                },
            },
        )
        return store.new_task(request.state.actor["id"], project, draft.model_dump(mode="json"))

    @routes.post("/api/tasks/{task_id}/publish-method", status_code=201)
    def publish(task_id: str, body: PublishMethod, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            task = store.task(actor, task_id, write=True, connection=c)
            store.permission(c, actor, task["project_id"], manage=body.approve, write=True)
            draft = TaskDraft.model_validate(task["draft"]).model_dump(mode="json")
            options = draft["options"]
            previous = options.get("publication", {})
            # A response lost after commit is replayable, but a later edit is not.
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
                    .first()
                )
                if entry is not None:
                    return {"template": dict(entry), "task": task}
            if task["revision"] != body.expected_revision:
                raise Problem(409, "DRAFT_CONFLICT", "方法草稿已有更新，请核对后发布")
            if options.get("editor") != "method" or draft["purpose"] not in {
                "assessment",
                "optimization",
            }:
                raise Problem(422, "METHOD_EDITOR_REQUIRED", "当前任务不是方法维护草稿")
            definition = options.get("definition", {})
            try:
                schema = (
                    AssessmentMethod if draft["purpose"] == "assessment" else OptimizationMethod
                )
                configuration = schema.model_validate(definition.get("configuration", {}))
                spec = TemplateSpec.model_validate(
                    {
                        "title": draft["title"],
                        "purpose": "method",
                        "basis": definition.get("basis"),
                        "profiles": definition.get("profiles"),
                        "scope": definition.get("scope", {}),
                        "configuration": configuration.model_dump(mode="json"),
                    }
                )
            except ValidationError as exc:
                raise Problem(
                    422,
                    "METHOD_DEFINITION",
                    "方法定义不完整或科学约束不满足",
                    {
                        "fields": [
                            {"path": ".".join(map(str, e["loc"])), "message": e["msg"]}
                            for e in exc.errors(include_context=False, include_input=False)
                        ]
                    },
                ) from exc
            entry = write_draft_template(c, actor, task["project_id"], spec, previous, body.approve)
            options["publication"] = {
                "template_id": entry["id"],
                "template_revision": entry["revision"],
                "origin_revision": task["revision"],
                "approve": body.approve,
            }
            saved = store.save_task(actor, task_id, task["revision"], draft, connection=c)
            return {"template": entry, "task": saved}

    return routes
