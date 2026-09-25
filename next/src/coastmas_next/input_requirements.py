"""Read-only requirements of a fixed method and task, with scoped alternatives.

No file scans, model execution, implicit semantic approval or task mutation.
"""

from coastmas.core.contracts import UNITS
from fastapi import APIRouter, Request
from sqlalchemy import select

from .intake import assets
from .method_library import method_version
from .resource_catalog import asset_metadata
from .store import Problem


def resolve(store, actor, task):
    with store.engine.connect() as c:
        store.permission(c, actor, task["project_id"])
        draft = task["draft"]
        rows = []
        if draft["purpose"] in {"cluster", "regression"}:
            predicting = draft["options"].get("model_operation") == "predict"
            chosen = {ref["asset_id"] for ref in draft["selection"]}
            valid = []
            for binding in draft["mapping"]:
                if binding["asset_id"] not in chosen:
                    continue
                asset = (
                    c.execute(
                        select(assets).where(
                            assets.c.id == binding["asset_id"],
                            assets.c.project_id == task["project_id"],
                        )
                    )
                    .mappings()
                    .first()
                )
                if (
                    asset
                    and c.scalar(
                        select(asset_metadata.c.state).where(
                            asset_metadata.c.asset_id == asset["id"]
                        )
                    )
                    != "recycled"
                ):
                    paths = {
                        layer["name"] + "/" + field["name"]
                        for layer in asset["facts"]["layers"]
                        for field in layer["fields"]
                    }
                    if binding["field"] in paths:
                        valid.append(binding)
            roles = [("predictors", "预测因子" if predicting else "特征观测", "feature")]
            if draft["purpose"] == "regression" and not predicting:
                roles.append(("response", "训练响应观测", "response"))
            needs = []
            for key, label, role in roles:
                bindings = [b for b in valid if b["role"] == role]
                needs.append(
                    {
                        "id": key,
                        "label": label,
                        "status": "used"
                        if bindings
                        and all(
                            b.get("concept") and b.get("unit") and b.get("support")
                            for b in bindings
                        )
                        else "needs_review"
                        if bindings
                        else "missing",
                        "alternatives": [{"id": "observations", "label": "已绑定的实际观测资料"}],
                    }
                )
            if predicting:
                needs.append(
                    {
                        "id": "fitted_model",
                        "label": "固定的已训练模型",
                        "status": "not_implemented",
                        "alternatives": [
                            {"id": "trained_package", "label": "独立预测包接入尚未实现"}
                        ],
                    }
                )
            return {
                "task_id": task["id"],
                "revision": task["revision"],
                "method": None,
                "requirements": needs,
                "execution_status": "not_implemented" if predicting else "requires_preflight",
                "guidance": "预测只需适用因子和固定训练模型，不索取真值；独立预测服务尚未接入。"
                if predicting
                else "按实际模型角色核对观测；聚类不要求响应变量。训练与全域应用范围在执行时重验。",
            }
        if not draft.get("method_id"):
            return {
                "task_id": task["id"],
                "revision": task["revision"],
                "method": None,
                "requirements": [],
                "guidance": "可先导入与查看资料；明确方法后再核对本研究需要的指标。",
            }
        try:
            method = method_version(
                c, draft["method_id"], draft["options"].get("method_revision"), approved=True
            )
        except Problem as exc:
            return {
                "task_id": task["id"],
                "revision": task["revision"],
                "method": None,
                "requirements": [],
                "guidance": "当前方法版本不可用于正式计算，仍可导入和查看资料。",
                "method_issue": {"code": exc.code, "message": exc.message},
            }
        if method["project_id"] != task["project_id"]:
            raise Problem(404, "METHOD_UNAVAILABLE", "方法不属于当前项目")
        config = method["spec"]["configuration"]
        definitions = config.get("indicators", list(config.get("quantities", {}).values()))
        selected = {r["asset_id"]: r for r in draft["selection"]}
        candidates = list(
            c.execute(select(assets).where(assets.c.project_id == task["project_id"])).mappings()
        )
        from .stage_products import read_products

        products = read_products(c, store, actor, task)
        for indicator in definitions:
            concept = indicator["concept"]
            bound = []
            available = []
            for asset in candidates:
                if (
                    c.scalar(
                        select(asset_metadata.c.state).where(
                            asset_metadata.c.asset_id == asset["id"]
                        )
                    )
                    == "recycled"
                ):
                    continue
                for layer in asset["facts"]["layers"]:
                    for field in layer["fields"]:
                        path = layer["name"] + "/" + field["name"]
                        binding = next(
                            (
                                b
                                for b in draft["mapping"]
                                if b["asset_id"] == asset["id"]
                                and b["field"] == path
                                and b.get("concept") == concept
                                and b["role"] == "feature"
                            ),
                            None,
                        )
                        item = {
                            "asset_id": asset["id"],
                            "revision": asset["revision"],
                            "name": asset["name"],
                            "field": path,
                            "unit": field.get("unit") or (binding or {}).get("unit"),
                        }
                        if binding and asset["id"] in selected:
                            bound.append(item)
                        elif field.get("concept") == concept:
                            available.append(item)
            derived = [
                p
                for p in products
                if p["concept"] == concept and p["role"] == "raw_indicator" and p["applicable"]
            ]

            def compatible(item, unit=indicator["unit"]):
                if not item["unit"]:
                    return False
                try:
                    UNITS.Quantity(1, item["unit"]).to(unit)
                    return True
                except Exception:
                    return False

            status = (
                "used"
                if (bound and all(compatible(x) for x in bound)) or derived
                else "needs_review"
                if bound
                else "reusable"
                if available
                else "missing"
            )
            alternatives = [
                {"id": "existing_indicator", "label": "已有同定义指标", "candidates": available}
            ]
            if concept == "NDVI":
                prep = draft["options"].get("preparation", {}).get("ndvi", {})
                source = next(
                    (
                        a
                        for a in candidates
                        if a["id"] == prep.get("asset_id") and a["id"] in selected
                    ),
                    None,
                )
                bands = (
                    {
                        field.get("band")
                        for layer in source["facts"]["layers"]
                        for field in layer["fields"]
                    }
                    if source
                    else set()
                )
                configured = (
                    prep.get("red_band") in bands
                    and prep.get("nir_band") in bands
                    and prep.get("red_band")
                    and prep.get("nir_band")
                    and prep["red_band"] != prep["nir_band"]
                    and prep.get("qa_policy")
                )
                alternatives.append(
                    {
                        "id": "ndvi",
                        "label": "红光与近红外影像＋NDVI配方",
                        "state": "configured" if configured else "needs_band_mapping",
                    }
                )
                if configured and status == "missing":
                    status = "can_generate"
            rows.append(
                {
                    "id": concept,
                    "label": concept,
                    "required": True,
                    "step": "indicators",
                    "status": status,
                    "unit": indicator["unit"],
                    "bound": bound,
                    "products": [p["asset_id"] for p in derived],
                    "alternatives": alternatives,
                }
            )
        return {
            "task_id": task["id"],
            "revision": task["revision"],
            "method": {
                "id": method["id"],
                "revision": method["revision"],
                "title": method["spec"]["title"],
            },
            "requirements": rows,
            "guidance": "任选适用路线；候选资料加入后仍核对单位、含义与范围。",
        }


def router(store):
    routes = APIRouter()

    @routes.get("/api/tasks/{task_id}/input-requirements")
    def requirements(task_id: str, request: Request):
        actor = request.state.actor["id"]
        return resolve(store, actor, store.task(actor, task_id))

    return routes
