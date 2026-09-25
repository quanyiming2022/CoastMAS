"""Versioned source statements from durable task drafts, never file metadata edits."""

from fastapi import APIRouter, Request
from pydantic import Field, ValidationError, model_validator
from sqlalchemy import select

from .contracts import Contract, TaskDraft
from .intake import Intake
from .method_authoring import PublishMethod
from .reuse import Reuse, TemplateSpec, templates, write_draft_template
from .store import Problem


class SourceStatement(Contract):
    basis: str = Field(min_length=1, max_length=10000)
    source_description: str | None = Field(default=None, max_length=4000)
    license_statement: str | None = Field(default=None, max_length=4000)
    observed_year: int | None = Field(default=None, ge=1, le=9999, strict=True)

    @model_validator(mode="after")
    def supplied(self):
        if not (
            self.source_description or self.license_statement or self.observed_year is not None
        ):
            raise ValueError("Provide at least one actual statement; leave unknown values empty")
        return self


def router(store):
    routes = APIRouter()

    @routes.post("/api/tasks/{task_id}/publish-statement", status_code=201)
    def publish(task_id: str, body: PublishMethod, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            task = store.task(actor, task_id, write=True, connection=c)
            store.permission(c, actor, task["project_id"], write=True, manage=body.approve)
            draft = TaskDraft.model_validate(task["draft"]).model_dump(mode="json")
            previous = draft["options"].get("statement_publication", {})
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
                raise Problem(409, "DRAFT_CONFLICT", "任务已有新版本，请核对后保存声明")
            try:
                statement = SourceStatement.model_validate(
                    draft["options"].get("source_statement", {})
                )
            except ValidationError as exc:
                raise Problem(
                    422,
                    "STATEMENT_INVALID",
                    "请补充声明依据，并只填写实际已知信息",
                    {
                        "fields": [
                            {"path": ".".join(map(str, e["loc"])), "message": e["msg"]}
                            for e in exc.errors(include_context=False, include_input=False)
                        ]
                    },
                ) from exc
            sources = [
                Intake(store).read_asset(actor, ref["asset_id"], c) for ref in draft["selection"]
            ]
            if not sources:
                raise Problem(422, "ASSETS_REQUIRED", "先选择声明适用的实际资料")
            if any(asset["project_id"] != task["project_id"] for asset in sources):
                raise Problem(422, "PROJECT_MISMATCH", "声明不能跨项目绑定资料")
            declaration = {
                key: value
                for key, value in {
                    "source": statement.source_description,
                    "use_restriction": statement.license_statement,
                    "observed_year": statement.observed_year,
                }.items()
                if value is not None and value != ""
            }
            spec = TemplateSpec(
                title=task["draft"]["title"][:190] + " · 来源声明",
                purpose="declaration",
                profiles=sorted({asset["facts"]["profile"] for asset in sources}),
                basis=statement.basis,
                scope={"asset_sha256": sorted({asset["sha256"] for asset in sources})},
                declaration=declaration,
            )
            entry = write_draft_template(c, actor, task["project_id"], spec, previous, body.approve)
            draft["options"]["statement_publication"] = {
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
                    # Scientific mappings and response slots remain exactly as the user saved.
                    for key, value in {
                        "inherited_declarations": suggested["declaration"],
                        "declaration_references": suggested["declaration_references"],
                        "mapping_issues": suggested["issues"],
                    }.items():
                        draft["options"].setdefault(key, {})[asset["id"]] = value
            saved = store.save_task(
                actor,
                task_id,
                task["revision"],
                TaskDraft.model_validate(draft).model_dump(mode="json"),
                connection=c,
            )
            return {"template": entry, "task": saved}

    return routes
