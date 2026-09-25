"""Separate file identities, approved knowledge and per-task bindings."""

from datetime import UTC, datetime
from fnmatch import fnmatchcase
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    insert,
    select,
    update,
)

from coastmas.core.contracts import UNITS

from .contracts import Contract, TaskDraft
from .intake import Intake
from .store import Problem, audit_event, identifier, metadata
from .temporal import automatic_choices


class MappingRule(Contract):
    field: str = Field(min_length=1, max_length=200)
    concept: str | None = Field(default=None, min_length=1, max_length=200)
    unit: str | None = Field(default=None, min_length=1, max_length=80)
    support: str | None = Field(default=None, min_length=1, max_length=100)
    role: (
        Literal["feature", "response", "identity", "time", "geometry", "constraint", "ignored"]
        | None
    ) = None

    @model_validator(mode="after")
    def known_values_only(self):
        if not any((self.concept, self.unit, self.support, self.role)):
            raise ValueError("A mapping rule must provide at least one known scientific property")
        if self.unit:
            try:
                UNITS.Unit(self.unit)
            except Exception as exc:
                raise ValueError("Unknown scientific unit") from exc
        return self


class TemplateScope(Contract):
    asset_sha256: list[str] = Field(default_factory=list, max_length=500)
    valid_until: AwareDatetime | None = None
    filenames: list[str] = Field(default_factory=list, max_length=100)
    exact_filenames: list[str] = Field(default_factory=list, max_length=200)
    required_fields: list[str] = Field(default_factory=list, max_length=500)
    standard_versions: list[str] = Field(default_factory=list, max_length=20)

    def matches(self, asset):
        paths = {
            layer["name"] + "/" + field["name"]
            for layer in asset["facts"]["layers"]
            for field in layer["fields"]
        }
        return (
            (not self.asset_sha256 or asset["sha256"] in self.asset_sha256)
            and (not self.exact_filenames or asset["name"] in self.exact_filenames)
            and (self.valid_until is None or datetime.now(UTC) <= self.valid_until)
            and (
                not self.filenames
                or any(fnmatchcase(asset["name"], pattern) for pattern in self.filenames)
            )
            and (
                not self.standard_versions
                or asset["facts"]["standard_version"] in self.standard_versions
            )
            and set(self.required_fields).issubset(paths)
        )


class TemplateSpec(Contract):
    title: str = Field(min_length=1, max_length=200)
    profiles: list[str] = Field(min_length=1, max_length=20)
    purpose: Literal["semantic", "method", "workflow", "declaration"]
    scope: TemplateScope = Field(default_factory=TemplateScope)
    basis: str = Field(min_length=1, max_length=10000)
    rules: list[MappingRule] = Field(default_factory=list, max_length=500)
    declaration: dict[str, str | int | None] = Field(default_factory=dict)
    configuration: dict = Field(default_factory=dict)


class TemplateUpdate(Contract):
    expected_revision: int = Field(ge=1)
    spec: TemplateSpec


class Approval(Contract):
    revision: int = Field(ge=1)


class AttachSources(Contract):
    expected_revision: int = Field(ge=1)
    assets: list[str] = Field(min_length=1, max_length=200)


templates = Table(
    "templates",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", ForeignKey("projects.id"), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("spec", JSON, nullable=False),
    Column("approved", Boolean, nullable=False),
    Column("approved_by", String),
)
template_history = Table(
    "template_revisions",
    metadata,
    Column("template_id", ForeignKey("templates.id"), primary_key=True),
    Column("revision", Integer, primary_key=True),
    Column("spec", JSON, nullable=False),
    Column("approved_by", String),
)


class Reuse:
    def __init__(self, store):
        self.store, self.intake = store, Intake(store)

    def suggestions(self, actor, asset_id, *, asset=None, connection=None):
        if connection is None:
            with self.store.engine.connect() as c:
                return self.suggestions(actor, asset_id, asset=asset, connection=c)
        asset = self.intake.read_asset(actor, asset_id, connection) if asset is None else asset
        self.store.permission(connection, actor, asset["project_id"])
        available = [
            t
            for t in connection.execute(
                select(templates).where(
                    templates.c.project_id == asset["project_id"], templates.c.approved.is_(True)
                )
            ).mappings()
            if TemplateScope.model_validate(t["spec"].get("scope", {})).matches(asset)
        ]
        applied, issues, declarations, adaptations = [], [], {}, []
        for layer in asset["facts"]["layers"]:
            for field in layer["fields"]:
                path = layer["name"] + "/" + field["name"]
                candidates = [
                    (t, rule)
                    for t in available
                    if t["spec"]["purpose"] == "semantic"
                    and asset["facts"]["profile"] in t["spec"]["profiles"]
                    for rule in t["spec"]["rules"]
                    if rule["field"] in {field["name"], path}
                ]
                if len(candidates) > 1:
                    issues.append(
                        {
                            "code": "MAPPING_AMBIGUOUS",
                            "field": path,
                            "templates": [t["id"] for t, _ in candidates],
                            "message": "多份认可定义匹配，请明确本次采用的依据",
                        }
                    )
                    continue
                if not candidates:
                    continue
                template, rule = candidates[0]
                if field.get("unit") and rule.get("unit") and field["unit"] != rule["unit"]:
                    try:
                        offset = float(UNITS.Quantity(0, field["unit"]).to(rule["unit"]).magnitude)
                        scale = (
                            float(UNITS.Quantity(1, field["unit"]).to(rule["unit"]).magnitude)
                            - offset
                        )
                    except Exception:
                        issues.append(
                            {
                                "code": "FILE_TEMPLATE_CONFLICT",
                                "field": path,
                                "file_unit": field["unit"],
                                "template_unit": rule["unit"],
                                "template_id": template["id"],
                                "message": "文件单位与模板量纲不兼容，不能用声明覆盖文件事实",
                            }
                        )
                        continue
                    adaptations.append(
                        {
                            "field": path,
                            "source_unit": field["unit"],
                            "target_unit": rule["unit"],
                            "scale": scale,
                            "offset": offset,
                            "loss": "none",
                            "basis": "dimensional unit registry; preserve original bytes",
                            "requires_confirmation": False,
                        }
                    )
                if (
                    field.get("concept")
                    and rule.get("concept")
                    and field["concept"] != rule["concept"]
                ):
                    issues.append(
                        {
                            "code": "SEMANTIC_CONFLICT",
                            "field": path,
                            "file_concept": field["concept"],
                            "template_concept": rule["concept"],
                        }
                    )
                    continue
                applied.append(
                    {
                        "asset_id": asset_id,
                        "field": path,
                        "unit": rule.get("unit") or field.get("unit"),
                        "concept": rule.get("concept") or field.get("concept"),
                        "support": rule.get("support") or field.get("support"),
                        "role": rule.get("role") or field.get("role") or "feature",
                        "template_id": template["id"],
                        "template_revision": template["revision"],
                    }
                )
        references, conflicted = [], set()
        field_paths = {
            layer["name"] + "/" + f["name"]
            for layer in asset["facts"]["layers"]
            for f in layer["fields"]
        }
        field_names = {f["name"] for layer in asset["facts"]["layers"] for f in layer["fields"]}
        for template in available:
            spec = template["spec"]
            if not spec["declaration"] or asset["facts"]["profile"] not in spec["profiles"]:
                continue
            if spec["purpose"] != "declaration" and not any(
                r["field"] in field_paths | field_names for r in spec["rules"]
            ):
                continue
            references.append(
                {
                    "template_id": template["id"],
                    "revision": template["revision"],
                    "basis": spec["basis"],
                }
            )
            for key, value in spec["declaration"].items():
                if key in conflicted:
                    continue
                if key in declarations and declarations[key] != value:
                    issues.append(
                        {
                            "code": "DECLARATION_CONFLICT",
                            "field": key,
                            "message": "适用来源声明冲突，相关值未自动采用",
                        }
                    )
                    declarations.pop(key, None)
                    conflicted.add(key)
                else:
                    declarations[key] = value
        return {
            "asset_id": asset_id,
            "asset_revision": asset["revision"],
            "file_sha256": asset["sha256"],
            "applied": applied,
            "issues": issues,
            "declaration": declarations,
            "declaration_references": references,
            "adaptations": adaptations,
        }

    @staticmethod
    def bind(draft, asset, suggested):
        asset_id = asset["id"]
        declarations = draft["options"].setdefault("inherited_declarations", {})
        mapping_issues = draft["options"].setdefault("mapping_issues", {})
        draft["selection"] = [r for r in draft["selection"] if r["asset_id"] != asset_id] + [
            {"asset_id": asset_id, "revision": asset["revision"], "layer": None}
        ]
        draft["mapping"] = [m for m in draft["mapping"] if m["asset_id"] != asset_id]
        lookup = {m["field"]: m for m in suggested["applied"]}
        for layer in asset["facts"]["layers"]:
            for field in layer["fields"]:
                path = layer["name"] + "/" + field["name"]
                draft["mapping"].append(
                    lookup.get(
                        path,
                        {
                            "asset_id": asset_id,
                            "field": path,
                            "unit": field.get("unit"),
                            "concept": field.get("concept"),
                            "support": None,
                            "template_id": None,
                            "template_revision": None,
                            "role": field.get("role") or "feature",
                        },
                    )
                )
        declarations[asset_id] = suggested["declaration"]
        draft["options"].setdefault("declaration_references", {})[asset_id] = suggested.get(
            "declaration_references", []
        )
        mapping_issues[asset_id] = suggested["issues"]
        draft["options"].setdefault("adaptations", {})[asset_id] = suggested["adaptations"]
        automatic_choices(draft, asset)

    def attach(self, actor, task_id, expected_revision, asset_ids):
        task = self.store.task(actor, task_id, write=True)
        draft = task["draft"]
        for asset_id in asset_ids:
            asset = self.intake.read_asset(actor, asset_id)
            if asset["project_id"] != task["project_id"]:
                raise Problem(422, "PROJECT_MISMATCH", "不能跨项目绑定资料")
            suggested = self.suggestions(actor, asset_id)
            self.bind(draft, asset, suggested)
        canonical = TaskDraft.model_validate(draft).model_dump(mode="json")
        return self.store.save_task(actor, task_id, expected_revision, canonical)


def validate_knowledge(store, actor, project, draft, sources):
    issues = []
    assets = {asset["id"]: asset for asset in sources}
    with store.engine.connect() as c:
        store.permission(c, actor, project)
        paths = {
            asset_id: {
                layer["name"] + "/" + field["name"]: field
                for layer in asset["facts"]["layers"]
                for field in layer["fields"]
            }
            for asset_id, asset in assets.items()
        }
        for binding in draft["mapping"]:
            native = paths.get(binding["asset_id"], {}).get(binding["field"])
            if native is None:
                issues.append(
                    {
                        "code": "BINDING_INVALID",
                        "field": binding["field"],
                        "message": "绑定字段不在本次实际资料中",
                    }
                )
                continue
            if binding["role"] in {"feature", "response", "constraint"}:
                conflict = bool(
                    native.get("concept")
                    and binding.get("concept")
                    and native["concept"] != binding["concept"]
                )
                if native.get("unit") and binding.get("unit") and native["unit"] != binding["unit"]:
                    try:
                        UNITS.Quantity(1, native["unit"]).to(binding["unit"])
                    except Exception:
                        conflict = True
                if conflict:
                    issues.append(
                        {
                            "code": "FILE_BINDING_CONFLICT",
                            "field": binding["field"],
                            "message": "本次定义与文件中的科学含义或量纲相冲突，不能覆盖文件事实",
                        }
                    )
            template_id = binding.get("template_id")
            if not template_id:
                continue
            item = (
                c.execute(
                    select(templates).where(
                        templates.c.id == template_id, templates.c.project_id == project
                    )
                )
                .mappings()
                .first()
            )
            if (
                item is None
                or item["revision"] != binding.get("template_revision")
                or not item["approved"]
            ):
                issues.append(
                    {
                        "code": "TEMPLATE_CHANGED",
                        "field": binding["field"],
                        "message": "本次绑定的认可定义已变化或撤销，请核对相关字段",
                    }
                )
                continue
            asset = assets.get(binding["asset_id"])
            if asset is None or not TemplateScope.model_validate(
                item["spec"].get("scope", {})
            ).matches(asset):
                issues.append(
                    {
                        "code": "TEMPLATE_SCOPE",
                        "field": binding["field"],
                        "message": "资料不再满足模板适用范围",
                    }
                )
                continue
            matched = any(
                rule["field"] in {binding["field"], binding["field"].split("/", 1)[-1]}
                and all(
                    rule.get(k) is None or rule[k] == binding[k]
                    for k in ["unit", "concept", "support", "role"]
                )
                for rule in item["spec"]["rules"]
            )
            if not matched:
                issues.append(
                    {
                        "code": "TEMPLATE_BINDING_CHANGED",
                        "field": binding["field"],
                        "message": "本次值与认可定义不同；需明确新的科学依据",
                    }
                )
        inherited = draft["options"].get("inherited_declarations", {})
        references = draft["options"].get("declaration_references", {})
        if not isinstance(references, dict) or not isinstance(inherited, dict):
            return issues + [{"code": "DECLARATION_INVALID", "message": "来源声明引用结构无效"}]
        for asset_id, claims in references.items():
            # No declaration and a declaration that became invalid are different.
            # Unused inputs do not participate in this action's scientific scope.
            asset = assets.get(asset_id)
            if asset is None or claims == []:
                continue
            if not isinstance(claims, list):
                issues.append(
                    {"code": "DECLARATION_CHANGED", "message": "来源声明的资料范围已变化"}
                )
                continue
            for claim in claims:
                if not isinstance(claim, dict):
                    issues.append({"code": "DECLARATION_INVALID", "message": "来源声明引用无效"})
                    continue
                item = (
                    c.execute(
                        select(templates).where(
                            templates.c.id == claim.get("template_id"),
                            templates.c.project_id == project,
                        )
                    )
                    .mappings()
                    .first()
                )
                if (
                    item is None
                    or not item["approved"]
                    or item["revision"] != claim.get("revision")
                    or not TemplateScope.model_validate(item["spec"].get("scope", {})).matches(
                        asset
                    )
                    or any(
                        inherited.get(asset_id, {}).get(key) != value
                        for key, value in item["spec"]["declaration"].items()
                    )
                ):
                    issues.append(
                        {
                            "code": "DECLARATION_CHANGED",
                            "message": "来源声明已更新、撤销、过期或不再适用",
                            "asset_id": asset_id,
                        }
                    )
    return issues


def write_draft_template(connection, actor, project, spec, previous, approve):
    """One transactional template lineage shared by domain authoring forms."""
    template_id = previous.get("template_id") or identifier()
    revision = previous.get("template_revision", 1) if previous else 0
    value = spec.model_dump(mode="json")
    entry = {
        "id": template_id,
        "project_id": project,
        "revision": revision + 1,
        "spec": value,
        "approved": approve,
        "approved_by": actor if approve else None,
    }
    if previous:
        changed = connection.execute(
            update(templates)
            .where(
                templates.c.id == template_id,
                templates.c.project_id == project,
                templates.c.revision == revision,
            )
            .values(
                revision=revision + 1,
                spec=value,
                approved=approve,
                approved_by=entry["approved_by"],
            )
        ).rowcount
        if changed != 1:
            raise Problem(409, "TEMPLATE_CHANGED", "已发布定义由其他维护者更新，请先核对版本")
    else:
        connection.execute(insert(templates).values(**entry))
    connection.execute(
        insert(template_history).values(
            template_id=template_id,
            revision=entry["revision"],
            spec=value,
            approved_by=entry["approved_by"],
        )
    )
    audit_event(connection, actor, project, "publish_template", template_id)
    if approve:
        audit_event(connection, actor, project, "approve_template", template_id)
    return entry


def router(store):
    routes = APIRouter()
    reuse = Reuse(store)

    @routes.get("/api/projects/{project}/templates")
    def catalog(project: str, request: Request):
        with store.engine.connect() as c:
            store.permission(c, request.state.actor["id"], project)
            return [
                dict(r)
                for r in c.execute(
                    select(templates).where(templates.c.project_id == project)
                ).mappings()
            ]

    @routes.post("/api/projects/{project}/templates", status_code=201)
    def create_template(project: str, body: TemplateSpec, request: Request):
        actor = request.state.actor["id"]
        TaskDraft.bounded_non_secret_options(body.configuration)
        TaskDraft.bounded_non_secret_options(body.declaration)
        entry = {
            "id": identifier(),
            "project_id": project,
            "revision": 1,
            "spec": body.model_dump(mode="json"),
            "approved": False,
            "approved_by": None,
        }
        with store.engine.begin() as c:
            store.permission(c, actor, project, write=True)
            c.execute(insert(templates).values(**entry))
            c.execute(
                insert(template_history).values(
                    template_id=entry["id"], revision=1, spec=entry["spec"], approved_by=None
                )
            )
            audit_event(c, actor, project, "create_template", entry["id"])
        return entry

    @routes.put("/api/templates/{template_id}")
    def update_template(template_id: str, body: TemplateUpdate, request: Request):
        actor = request.state.actor["id"]
        spec = body.spec.model_dump(mode="json")
        TaskDraft.bounded_non_secret_options(spec["configuration"])
        TaskDraft.bounded_non_secret_options(spec["declaration"])
        with store.engine.begin() as c:
            item = (
                c.execute(select(templates).where(templates.c.id == template_id)).mappings().first()
            )
            if item is None:
                raise Problem(404, "TEMPLATE_UNAVAILABLE", "模板不可用")
            store.permission(c, actor, item["project_id"], write=True)
            changed = c.execute(
                update(templates)
                .where(
                    templates.c.id == template_id, templates.c.revision == body.expected_revision
                )
                .values(
                    revision=body.expected_revision + 1, spec=spec, approved=False, approved_by=None
                )
            ).rowcount
            if changed != 1:
                raise Problem(409, "TEMPLATE_CHANGED", "模板版本已改变，请核对后再保存")
            c.execute(
                insert(template_history).values(
                    template_id=template_id,
                    revision=body.expected_revision + 1,
                    spec=spec,
                    approved_by=None,
                )
            )
            audit_event(c, actor, item["project_id"], "update_template", template_id)
            return {
                **dict(item),
                "revision": body.expected_revision + 1,
                "spec": spec,
                "approved": False,
                "approved_by": None,
            }

    @routes.get("/api/templates/{template_id}/history")
    def history(template_id: str, request: Request):
        with store.engine.connect() as c:
            item = (
                c.execute(select(templates).where(templates.c.id == template_id)).mappings().first()
            )
            if item is None:
                raise Problem(404, "TEMPLATE_UNAVAILABLE", "模板不可用")
            store.permission(c, request.state.actor["id"], item["project_id"])
            return [
                dict(row)
                for row in c.execute(
                    select(template_history)
                    .where(template_history.c.template_id == template_id)
                    .order_by(template_history.c.revision)
                ).mappings()
            ]

    @routes.post("/api/templates/{template_id}/revoke")
    def revoke(template_id: str, body: Approval, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            item = (
                c.execute(select(templates).where(templates.c.id == template_id)).mappings().first()
            )
            if item is None:
                raise Problem(404, "TEMPLATE_UNAVAILABLE", "模板不可用")
            store.permission(c, actor, item["project_id"], manage=True)
            changed = c.execute(
                update(templates)
                .where(templates.c.id == template_id, templates.c.revision == body.revision)
                .values(approved=False, approved_by=None)
            ).rowcount
            if changed != 1:
                raise Problem(409, "TEMPLATE_CHANGED", "模板版本已改变")
            # Approval belongs to this exact revision. A later publication must not
            # revive the revoked version through its historical approval snapshot.
            c.execute(
                update(template_history)
                .where(
                    template_history.c.template_id == template_id,
                    template_history.c.revision == body.revision,
                )
                .values(approved_by=None)
            )
            audit_event(c, actor, item["project_id"], "revoke_template", template_id)
        return {"revoked": True}

    @routes.post("/api/templates/{template_id}/approve")
    def approve(template_id: str, body: Approval, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            item = (
                c.execute(select(templates).where(templates.c.id == template_id)).mappings().first()
            )
            if item is None:
                raise Problem(404, "TEMPLATE_UNAVAILABLE", "模板不可用")
            store.permission(c, actor, item["project_id"], manage=True)
            if item["revision"] != body.revision:
                raise Problem(409, "TEMPLATE_CHANGED", "模板版本已改变")
            c.execute(
                update(templates)
                .where(templates.c.id == template_id, templates.c.revision == body.revision)
                .values(approved=True, approved_by=actor)
            )
            c.execute(
                update(template_history)
                .where(
                    template_history.c.template_id == template_id,
                    template_history.c.revision == body.revision,
                )
                .values(approved_by=actor)
            )
            audit_event(c, actor, item["project_id"], "approve_template", template_id)
        return {"id": template_id, "revision": body.revision, "approved": True}

    @routes.get("/api/assets/{asset_id}/suggestions")
    def suggestions(asset_id: str, request: Request):
        return reuse.suggestions(request.state.actor["id"], asset_id)

    @routes.post("/api/tasks/{task_id}/sources")
    def attach(task_id: str, body: AttachSources, request: Request):
        return reuse.attach(request.state.actor["id"], task_id, body.expected_revision, body.assets)

    return routes
