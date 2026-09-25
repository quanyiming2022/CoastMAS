"""Bounded, read-only review of saved metadata. Never calls scientific preflight."""

import hashlib
import time

from sqlalchemy import select

from .intake import Intake
from .management_catalog import record_meta, require_available
from .method_library import method_version
from .store import Problem


def review(store, actor, task_id, revision):
    issues = {}

    def add(code, message, steps, action, *, asset=None, concept=None, details=None):
        identity = f"{code}:{asset or ''}:{concept or ''}"
        issues[identity] = {
            "id": hashlib.sha256(identity.encode()).hexdigest()[:16],
            "code": code,
            "message": message,
            "steps": steps,
            "action": action,
            "asset_id": asset,
            "concept": concept,
            "details": details,
        }

    with store.engine.connect() as c:
        task = store.task(actor, task_id, connection=c)
        if task["revision"] != revision:
            raise Problem(
                409, "REVIEW_STALE", "配置已更新，正在重新检查", {"revision": task["revision"]}
            )
        draft = task["draft"]
        for kind, key in [("projects", task["project_id"]), ("tasks", task_id)]:
            try:
                require_available(c, kind, key, lock=False)
            except Problem as exc:
                add(
                    exc.code,
                    exc.message,
                    ["sources", "synthesis"],
                    "lifecycle",
                    details=exc.details,
                )
        sources = []
        for ref in draft["selection"]:
            asset = Intake(store).read_asset(actor, ref["asset_id"], connection=c)
            if asset["project_id"] != task["project_id"]:
                raise Problem(403, "PROJECT_SCOPE", "输入资料不属于当前项目")
            sources.append(asset)
            if asset["revision"] != ref["revision"]:
                add(
                    "SOURCE_CHANGED",
                    f"“{asset['name']}”的版本已变化",
                    ["sources"],
                    "inputs",
                    asset=asset["id"],
                )
            state = c.scalar(
                select(record_meta.c.state).where(
                    record_meta.c.kind == "assets", record_meta.c.record_id == asset["id"]
                )
            )
            if state in {"archived", "recycled"}:
                add(
                    "SOURCE_INACTIVE",
                    f"“{asset['name']}”已归档或回收",
                    ["sources"],
                    "inputs",
                    asset=asset["id"],
                )
        if not sources:
            add("DATA_REQUIRED", "尚未添加输入资料", ["sources"], "inputs")
        elif (
            draft["purpose"] in {"assessment", "optimization"}
            and draft["options"].get("task_type") != "planning"
        ):
            if not draft.get("method_id"):
                add(
                    "METHOD_REQUIRED",
                    "尚未选择评价方法" if draft["purpose"] == "assessment" else "尚未选择优化方法",
                    ["normalization", "weights", "synthesis"],
                    "methods",
                )
            else:
                try:
                    method = method_version(
                        c,
                        draft["method_id"],
                        draft["options"].get("method_revision"),
                        approved=True,
                    )
                    if method["project_id"] != task["project_id"]:
                        raise Problem(403, "PROJECT_SCOPE", "方法不属于当前项目")
                    config = method["spec"]["configuration"]
                    indicators = (
                        config.get("indicators", [])
                        if draft["purpose"] == "assessment"
                        else list(config.get("quantities", {}).values())
                    )
                    for indicator in indicators:
                        concept = indicator.get("concept")
                        bindings = [
                            b
                            for b in draft["mapping"]
                            if b.get("concept") == concept and b["role"] in {"feature", "response"}
                        ]
                        if len(bindings) != 1:
                            add(
                                "CONCEPT_MAPPING_REQUIRED",
                                f"指标“{concept}”尚未唯一匹配输入字段",
                                ["indicators"],
                                "bindings",
                                concept=concept,
                            )
                        elif not bindings[0].get("unit"):
                            add(
                                "UNIT_REQUIRED",
                                f"指标“{concept}”的原始单位尚未确认",
                                ["indicators", "normalization"],
                                "bindings",
                                asset=bindings[0]["asset_id"],
                                concept=concept,
                            )
                        if draft["purpose"] == "assessment" and not isinstance(
                            indicator.get("positive"), bool
                        ):
                            add(
                                "DIRECTION_REQUIRED",
                                f"指标“{concept}”尚未设置评分方向",
                                ["normalization"],
                                "methods",
                                concept=concept,
                            )
                    if config.get("task") != draft["purpose"]:
                        add(
                            "METHOD_PURPOSE",
                            "所选方法不适用于当前研究目标",
                            ["synthesis"],
                            "methods",
                        )
                except Problem as exc:
                    if exc.status == 403:
                        raise
                    add(
                        exc.code,
                        exc.message,
                        ["normalization", "weights", "synthesis"],
                        "methods",
                        details=exc.details,
                    )
        elif draft["purpose"] in {"cluster", "regression", "temporal"}:
            for binding in draft["mapping"]:
                if binding["role"] not in {"feature", "response"}:
                    continue
                name = binding.get("concept") or binding["field"]
                if not binding.get("unit"):
                    add(
                        "UNIT_REQUIRED",
                        f"“{name}”的原始单位尚未确认",
                        ["indicators"],
                        "bindings",
                        asset=binding["asset_id"],
                        concept=name,
                    )
                if not binding.get("concept"):
                    add(
                        "CONCEPT_REQUIRED",
                        f"字段“{name}”尚未确定指标含义",
                        ["indicators"],
                        "bindings",
                        asset=binding["asset_id"],
                        concept=name,
                    )
            if (
                draft["purpose"] == "regression"
                and len([b for b in draft["mapping"] if b["role"] == "response"]) != 1
            ):
                add("RESPONSE_REQUIRED", "回归需要明确一个响应变量", ["indicators"], "bindings")
        if sources and draft["purpose"] not in {"inspect", "spatial"}:
            from .reuse import validate_knowledge

            for issue in validate_knowledge(store, actor, task["project_id"], draft, sources):
                step = "sources" if issue["code"].startswith("DECLARATION") else "indicators"
                asset_id = issue.get("asset_id")
                name = next((a["name"] for a in sources if a["id"] == asset_id), None)
                message = issue.get("message", "相关定义需要核对")
                add(
                    issue["code"],
                    f"“{name}”：{message}" if name else message,
                    [step],
                    "asset" if asset_id else "bindings",
                    asset=asset_id,
                    concept=issue.get("field"),
                    details=issue,
                )
        # File diagnostics are scoped to the affected action, not replicated into all steps.
        for asset in sources:
            for fact in asset["facts"].get("issues", []):
                if not isinstance(fact, dict):
                    continue
                code = str(fact.get("code", "FILE_DIAGNOSTIC"))
                if "CRS" in code or "GEOREFER" in code or "LOCATION" in code:
                    add(
                        code,
                        f"“{asset['name']}”的定位信息需要核对",
                        ["spatial"],
                        "asset",
                        asset=asset["id"],
                        details=fact,
                    )
        return {
            "task_id": task_id,
            "revision": revision,
            "scope": "saved_metadata",
            "checked_at": time.time(),
            "execution_checked": False,
            "issues": list(issues.values()),
        }
