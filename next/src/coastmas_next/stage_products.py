"""Immutable stage products, registered in the same transaction as job completion.

Original inputs and editable drafts are not rewritten by background completion.
Consumers resolve only outputs whose source versions and recipe still apply.
"""

import copy
import hashlib
import time

from fastapi import APIRouter, Request
from sqlalchemy import JSON, Column, Float, ForeignKey, String, Table, insert, select

from .intake import assets
from .profiles import inspect_file
from .store import Problem, audit_event, metadata

stage_products = Table(
    "stage_products",
    metadata,
    Column("asset_id", ForeignKey("assets.id"), primary_key=True),
    Column("task_id", ForeignKey("tasks.id"), nullable=False),
    Column("job_id", ForeignKey("jobs.id"), nullable=False),
    Column("node_id", String, nullable=False),
    Column("role", String, nullable=False),
    Column("concept", String),
    Column("basis", JSON, nullable=False),
    Column("created", Float, nullable=False),
)


def prepare_registration(store, job, data):
    manifest = job["manifest"]
    if not manifest.get("processing_node_id"):
        return []
    operator = manifest["draft"]["options"].get("operator")
    if operator not in {"align_grid", "ndvi", "score", "builtin_indicator"}:
        return []
    prepared = []
    for item in data.get("files", []):
        if item["role"] not in {"raw_indicator", "prepared_input", "indicator"}:
            continue
        path = store.settings.storage_root / item["key"]
        facts = inspect_file(path)
        lineage = {
            "job_id": job["id"],
            "node_id": manifest["processing_node_id"],
            "task_id": job["task_id"],
            "operator": operator,
            "sources": [
                {k: a[k] for k in ("id", "revision", "sha256")} for a in manifest["assets"]
            ],
            "parameters": manifest["draft"]["options"].get("parameters", {}),
            "indicator_selection": manifest["draft"]["options"].get("indicator_selection"),
            "band": manifest["draft"]["options"].get("band", 1),
        }
        facts["lineage"] = lineage
        asset_id = hashlib.sha256(f"{job['id']}:{item['name']}".encode()).hexdigest()[:32]
        asset = {
            "id": asset_id,
            "project_id": job["project_id"],
            "revision": 1,
            "name": item["title"] + path.suffix,
            "size": item["size"],
            "sha256": item["sha256"],
            "object_key": item["key"],
            "facts": facts,
            "created": time.time(),
        }
        prepared.append(
            (
                asset,
                {
                    "asset_id": asset_id,
                    "task_id": job["task_id"],
                    "job_id": job["id"],
                    "node_id": manifest["processing_node_id"],
                    "role": item["role"],
                    "concept": manifest["method"]["definition"]["semantic_type"]
                    if operator == "builtin_indicator"
                    else "NDVI"
                    if operator == "ndvi"
                    else lineage["parameters"]["concept"]
                    if operator == "score"
                    else None,
                    "basis": lineage,
                    "created": asset["created"],
                },
            )
        )
    return prepared


def publish(c, store, job, prepared):
    if not prepared:
        return
    store.permission(c, job["actor"], job["project_id"], write=True)
    for asset, product in prepared:
        c.execute(insert(assets).values(**asset))
        c.execute(insert(stage_products).values(**product))
        audit_event(c, job["actor"], job["project_id"], "register_stage_product", asset["id"])


def read_products(c, store, actor, task):
    from .resource_catalog import asset_metadata

    refs = {r["asset_id"]: r["revision"] for r in task["draft"]["selection"]}
    rows = [
        dict(r)
        for r in c.execute(
            select(stage_products)
            .where(stage_products.c.task_id == task["id"])
            .order_by(stage_products.c.created.desc(), stage_products.c.asset_id)
        ).mappings()
    ]
    lookup = {r["asset_id"]: r for r in rows}

    def reasons_for(row, seen):
        if row["asset_id"] in seen:
            return ["阶段依赖循环"]
        seen = seen | {row["asset_id"]}
        basis, reasons = row["basis"], []
        for source in basis["sources"]:
            if refs.get(source["id"]) == source["revision"]:
                continue
            if source["id"] in lookup:
                reasons += reasons_for(lookup[source["id"]], seen)
            else:
                reasons.append("本次输入已移除或版本改变")
        fixed = basis.get("indicator_selection")
        if fixed:
            current_indicator = next((s for s in task["draft"]["options"].get("indicators", []) if s["selection_id"] == fixed["selection_id"]), None)
            if current_indicator != fixed:
                reasons.append("指标选择或配置已修改")
        current = task["draft"]["options"].get("preparation", {}).get(basis["operator"], {})
        expected = {
            "asset_id": basis["sources"][0]["id"],
            "band": basis["band"],
            **basis["parameters"],
        }
        if any(k in current and current[k] != v for k, v in expected.items()):
            reasons.append("处理参数已修改，旧产物不能用于当前配置")
        if (
            c.scalar(
                select(asset_metadata.c.state).where(asset_metadata.c.asset_id == row["asset_id"])
            )
            == "recycled"
        ):
            reasons.append("阶段资料已回收")
        return list(dict.fromkeys(reasons))

    return [
        {**row, "applicable": not (reasons := reasons_for(row, set())), "reasons": reasons}
        for row in rows
    ]


def effective_task(store, actor, task):
    """Resolve exact concept matches; explicit user bindings always take precedence."""
    if task["draft"]["purpose"] != "assessment" or not task["draft"].get("method_id"):
        return task
    from .method_library import method_version

    with store.engine.connect() as c:
        products = read_products(c, store, actor, task)
        try:
            method = method_version(
                c,
                task["draft"]["method_id"],
                task["draft"]["options"].get("method_revision"),
                approved=True,
            )
        except Problem:
            return task
        if method["project_id"] != task["project_id"]:
            return task
        concepts = {i["concept"] for i in method["spec"]["configuration"].get("indicators", [])}
        if not concepts:
            return task
        draft = copy.deepcopy(task["draft"])
        mapped = {m.get("concept") for m in draft["mapping"] if m["role"] == "feature"}
        used = []
        for p in products:
            if (
                not p["applicable"]
                or p["role"] != "raw_indicator"
                or p["concept"] not in concepts - mapped
            ):
                continue
            asset = c.execute(select(assets).where(assets.c.id == p["asset_id"])).mappings().one()
            store.permission(c, actor, asset["project_id"])
            layer = asset["facts"]["layers"][0]
            field = layer["fields"][0]
            draft["selection"].append(
                {"asset_id": asset["id"], "revision": asset["revision"], "layer": layer["name"]}
            )
            draft["mapping"].append(
                {
                    "asset_id": asset["id"],
                    "field": layer["name"] + "/" + field["name"],
                    "concept": p["concept"],
                    "unit": field["unit"],
                    "role": "feature",
                    "support": None,
                    "template_id": None,
                    "template_revision": None,
                }
            )
            mapped.add(p["concept"])
            used.append(p)
        if not used:
            return task
        # Keep source statements for all upstream material for normal scope revalidation.
        draft["options"]["stage_products"] = [
            {k: p[k] for k in ("asset_id", "job_id", "node_id", "concept")} for p in used
        ]
        return {**task, "draft": draft}


def router(store):
    routes = APIRouter()

    @routes.get("/api/tasks/{task_id}/stage-products")
    def products(task_id: str, request: Request):
        with store.engine.connect() as c:
            actor = request.state.actor["id"]
            task = store.task(actor, task_id, connection=c)
            return read_products(c, store, actor, task)

    return routes
