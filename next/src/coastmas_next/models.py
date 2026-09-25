"""Provided implementations, immutable release identity and project-specific approval."""

import csv
import hashlib
import json
import math
import shutil
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field, StrictBool, ValidationError
from sqlalchemy import Boolean, Column, ForeignKey, String, Table, insert, select, update

from coastmas.adapters.projection_pursuit import ProjectionFrame, ProjectionPursuitAdapter
from coastmas.adapters.runtime import RunRequest
from coastmas.core.errors import CoastMASError

from .contracts import Contract
from .store import Problem, audit_event, metadata


class Release(Contract):
    model_id: Literal["ppci_mcdc", "ppr_ols"]
    image: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runner_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    application_proof_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    package: str
    version: str

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()


class ProjectionOptions(Contract):
    standardize: StrictBool
    size: int = Field(strict=True, ge=1, le=20)
    seed: int = Field(strict=True, ge=0, le=2147483647)


class ApproveModel(Contract):
    release_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


approvals = Table(
    "model_approvals",
    metadata,
    Column("project_id", ForeignKey("projects.id"), primary_key=True),
    Column("model_id", String, primary_key=True),
    Column("release_digest", String, primary_key=True),
    Column("actor", String, nullable=False),
    Column("active", Boolean, nullable=False),
)


def configured_releases(settings):
    if settings.runtime_catalog is None:
        return []
    rows = json.loads(settings.runtime_catalog.read_text())
    return [Release.model_validate(row) for row in rows]


class ModelRegistry:
    def __init__(self, store, releases=None):
        self.store = store
        self.releases = {
            r.model_id: r
            for r in (configured_releases(store.settings) if releases is None else releases)
        }

    def catalog(self, actor, project):
        with self.store.engine.connect() as c:
            role = self.store.permission(c, actor, project)
            enabled = set(
                c.execute(
                    select(approvals.c.model_id, approvals.c.release_digest).where(
                        approvals.c.project_id == project, approvals.c.active.is_(True)
                    )
                ).all()
            )
        return [
            {
                "can_approve": role == "manager",
                "release": r.model_dump(),
                "release_digest": r.digest,
                "approved": (r.model_id, r.digest) in enabled,
            }
            for r in self.releases.values()
        ]

    def approve(self, actor, project, model, digest):
        release = self.releases.get(model)
        if release is None or release.digest != digest:
            raise Problem(409, "RELEASE_CHANGED", "核验运行包不存在或已改变，不能沿用审批")
        with self.store.engine.begin() as c:
            self.store.permission(c, actor, project, manage=True)
            query = select(approvals).where(
                approvals.c.project_id == project,
                approvals.c.model_id == model,
                approvals.c.release_digest == digest,
            )
            if c.execute(query).first():
                c.execute(
                    update(approvals)
                    .where(
                        approvals.c.project_id == project,
                        approvals.c.model_id == model,
                        approvals.c.release_digest == digest,
                    )
                    .values(active=True, actor=actor)
                )
            else:
                c.execute(
                    insert(approvals).values(
                        project_id=project,
                        model_id=model,
                        release_digest=digest,
                        actor=actor,
                        active=True,
                    )
                )
            audit_event(c, actor, project, "approve_model", digest)
        return self.require(actor, project, model)

    def require(self, actor, project, model):
        for item in self.catalog(actor, project):
            if item["release"]["model_id"] == model and item["approved"]:
                return item
        raise Problem(422, "RUNTIME_APPROVAL_REQUIRED", "本项目尚未批准当前核验运行包")


def selected_bindings(manifest):
    draft = manifest["draft"]
    assets = {a["id"]: a for a in manifest["assets"]}
    bindings = draft["mapping"]
    seen = set()
    for binding in bindings:
        key = (binding["asset_id"], binding["field"])
        asset = assets.get(binding["asset_id"])
        paths = (
            {
                layer["name"] + "/" + field["name"]
                for layer in asset["facts"]["layers"]
                for field in layer["fields"]
            }
            if asset
            else set()
        )
        if key in seen or binding["field"] not in paths:
            raise Problem(422, "INVALID_BINDING", "变量映射不在本次实际资料中或重复")
        seen.add(key)
    features = [b for b in bindings if b["role"] == "feature"]
    response = [b for b in bindings if b["role"] == "response"]
    if not features:
        raise Problem(422, "FEATURES_REQUIRED", "至少选择一个实际解释变量")
    if (draft["purpose"] == "regression" and len(response) != 1) or (
        draft["purpose"] == "cluster" and response
    ):
        raise Problem(422, "RESPONSE_REQUIRED", "回归需要唯一响应变量；聚类不使用响应变量")
    return features, response


def table_frame(settings, manifest):
    features, response = selected_bindings(manifest)
    if len(manifest["assets"]) != 1 or manifest["assets"][0]["facts"]["profile"] != "csv":
        raise Problem(422, "TABLE_SCOPE", "本方法需要一个观测表；栅格需使用显式空间训练流程")
    asset = manifest["assets"][0]
    identities = [b for b in manifest["draft"]["mapping"] if b["role"] == "identity"]
    if len(identities) > 1:
        raise Problem(422, "IDENTITY_AMBIGUOUS", "请指定一个行标识字段")
    ids, values, responses = [], [], []

    def cell(row, binding):
        raw = row[binding["field"].split("/", 1)[1]]
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise Problem(
                422,
                "OBSERVATION_INVALID",
                "变量包含空白或非数值；请集中选择有依据的缺测处理",
                {"field": binding["field"], "row": len(ids)},
            ) from exc
        if not math.isfinite(value):
            raise Problem(422, "OBSERVATION_INVALID", "观测必须是有限数值")
        return value

    with (settings.storage_root / asset["object_key"]).open(
        encoding=asset["facts"]["encoding"], newline=""
    ) as source:
        reader = csv.DictReader(source, **asset["facts"]["dialect"])
        for index, row in enumerate(reader):
            if index >= 10000:
                raise Problem(
                    422,
                    "TRAINING_BUDGET",
                    "完整训练超过当前方法内存预算；请明确一次训练与分批应用规则，不自动截取",
                )
            identity = (
                row[identities[0]["field"].split("/", 1)[1]] if identities else f"row-{index + 1}"
            )
            if not identity:
                raise Problem(422, "IDENTITY_REQUIRED", "行标识不能为空")
            ids.append(identity)
            values.append(tuple(cell(row, b) for b in features))
            if response:
                responses.append(cell(row, response[0]))
    try:
        return ProjectionFrame(
            row_ids=tuple(ids),
            feature_names=tuple(b["field"].split("/", 1)[1] for b in features),
            feature_units=tuple(b["unit"] for b in features),
            values=tuple(values),
            standardize=manifest["draft"]["options"]["standardize"],
            response=tuple(responses) if response else None,
            response_unit=response[0]["unit"] if response else None,
            observation_scope="all_joint_valid_cells",
            joint_valid_cells=len(ids),
        )
    except (ValidationError, KeyError) as exc:
        raise Problem(
            422,
            "FRAME_INVALID",
            "观测维度、单位、标识或标准化选择不满足模型要求",
            {"reason": str(exc)[:1500]},
        ) from exc


def projection_preflight(store, actor, task, sources):
    purpose = task["draft"]["purpose"]
    if task["draft"]["options"].get("model_operation") == "predict":
        raise Problem(422, "PREDICTION_PACKAGE_NOT_IMPLEMENTED", "固定训练包的独立预测入口尚未接入；不能改为重新训练或要求新真值来替代。")
    model = "ppci_mcdc" if purpose == "cluster" else "ppr_ols"
    release = ModelRegistry(store).require(actor, task["project_id"], model)
    if sources and all(a["facts"]["profile"] in {"geotiff", "cog"} for a in sources):
        from .raster_task import preflight as raster_preflight

        raster_preflight(
            store.settings,
            {"assets": sources, "draft": task["draft"]},
            Release.model_validate(release["release"]),
        )
        return release
    options = ProjectionOptions.model_validate(
        {k: task["draft"]["options"].get(k) for k in ["standardize", "size", "seed"]}
    )
    if purpose == "cluster" and options.size < 2:
        raise Problem(422, "MODEL_SIZE", "聚类至少需要两个类")
    frame = table_frame(store.settings, {"assets": sources, "draft": task["draft"]})
    if options.size >= len(frame.row_ids):
        raise Problem(422, "MODEL_SIZE", "模型规模必须小于观测数")
    return release


def compute(settings, manifest, cancelled, artifact_dir=None):
    frozen = manifest["runtime"]
    release = Release.model_validate(frozen["release"])
    if release.digest != frozen["release_digest"] or not any(
        r.digest == release.digest for r in configured_releases(settings)
    ):
        raise Problem(409, "RUNTIME_CHANGED", "当前核验运行包与固定运行清单不同")
    if manifest["assets"] and all(
        a["facts"]["profile"] in {"geotiff", "cog"} for a in manifest["assets"]
    ):
        from .raster_task import compute as raster_compute

        if artifact_dir is None:
            raise Problem(500, "ARTIFACT_CONTEXT", "完整成果缺少独立运行产物目录")
        return raster_compute(settings, manifest, cancelled, artifact_dir, release)
    docker = shutil.which("docker")
    if docker is None:
        raise Problem(503, "RUNTIME_UNAVAILABLE", "本机容器运行环境不可用")
    frame = table_frame(settings, manifest)
    options = ProjectionOptions.model_validate(
        {k: manifest["draft"]["options"].get(k) for k in ["standardize", "size", "seed"]}
    )
    key = "clusters" if release.model_id == "ppci_mcdc" else "terms"
    try:
        output = ProjectionPursuitAdapter(image=release.image, docker=docker).run(
            RunRequest(
                handler=release.model_id,
                inputs={"frame": frame.model_dump(mode="json")},
                parameters={key: options.size, "seed": options.seed},
                work_root=settings.storage_root / "work",
                timeout_seconds=300,
                cancel=cancelled,
            )
        )
    except CoastMASError as exc:
        raise Problem(422, exc.code, str(exc)) from exc
    return {
        **output.outputs["result"],
        "runtime": frozen,
        "elapsed_seconds": output.elapsed_seconds,
        "identity_basis": "file"
        if any(b["role"] == "identity" for b in manifest["draft"]["mapping"])
        else "source_row_order",
    }


def router(store):
    routes = APIRouter()

    @routes.get("/api/projects/{project}/models")
    def catalog(project: str, request: Request):
        return ModelRegistry(store).catalog(request.state.actor["id"], project)

    @routes.post("/api/projects/{project}/models/{model}/approve")
    def approve(project: str, model: str, body: ApproveModel, request: Request):
        return ModelRegistry(store).approve(
            request.state.actor["id"], project, model, body.release_digest
        )

    @routes.post("/api/projects/{project}/models/{model}/revoke")
    def revoke(project: str, model: str, body: ApproveModel, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            store.permission(c, actor, project, manage=True)
            c.execute(
                update(approvals)
                .where(
                    approvals.c.project_id == project,
                    approvals.c.model_id == model,
                    approvals.c.release_digest == body.release_digest,
                )
                .values(active=False)
            )
            audit_event(c, actor, project, "revoke_model", body.release_digest)
        return {"revoked": True}

    return routes
