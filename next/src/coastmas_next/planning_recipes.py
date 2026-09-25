"""Versioned business recipes. Linear metrics are not generic science assertions."""

import math
from typing import Literal

from pydantic import Field, StrictFloat, StrictInt, ValidationError

from .contracts import Contract
from .store import Problem

VERSION = "1.0.0"
METRICS = {
    "minimize_construction_cost": {
        "name": "减少建设成本",
        "direction": "min",
        "field": "construction_cost",
        "unit": "declared_currency",
        "templates": ["LandUseAllocation", "RestorationPlanning", "FacilityLocation"],
        "category": "经济",
    },
    "maximize_restoration_gain": {
        "name": "增加生态修复收益",
        "direction": "max",
        "field": "restoration_gain",
        "unit": "declared_gain",
        "templates": ["RestorationPlanning"],
        "category": "生态",
    },
    "minimize_ecological_occupation": {
        "name": "减少生态用地占用",
        "direction": "min",
        "field": "ecological_area_m2",
        "unit": "m^2",
        "templates": ["LandUseAllocation", "FacilityLocation"],
        "category": "生态",
    },
    "minimize_high_risk_development": {
        "name": "减少高风险区开发",
        "direction": "min",
        "field": "high_risk_area_m2",
        "unit": "m^2",
        "templates": ["LandUseAllocation", "FacilityLocation"],
        "category": "风险",
    },
}
CONSTRAINTS = {
    "development_quota": {
        "name": "新增开发面积上限",
        "category": "land_quota",
        "field": "area_m2",
        "unit": "m^2",
        "limit_required": True,
    },
    "ecological_redline_exclusion": {
        "name": "必须避让区域",
        "category": "ecological",
        "field": "forbidden",
        "unit": None,
        "limit_required": False,
    },
    "budget": {
        "name": "总预算上限",
        "category": "budget",
        "field": "construction_cost",
        "unit": "declared_currency",
        "limit_required": True,
    },
}
DECISIONS = {
    "LandUseAllocation": {
        "name": "建设用地位置",
        "action": "develop",
        "description": (
            "选择新增建设单元；其他用途保持原状。此版本仅支持二元新增建设，不代表多用途配置。"
        ),
    },
    "RestorationPlanning": {
        "name": "生态修复单元",
        "action": "restore",
        "description": "选择修复或保持原状；不默认修复类型、强度或收益。",
    },
    "FacilityLocation": {
        "name": "设施候选位置",
        "action": "select_site",
        "description": "选择设施候选点；容量与服务网络约束需由后续匹配检查。",
    },
}


class ObjectiveItem(Contract):
    metric: str = ""
    weight: StrictFloat | StrictInt | None = Field(default=None, ge=0, le=1)


class ObjectiveSet(Contract):
    mode: Literal["single_objective", "weighted_multiobjective", "pareto_multiobjective"] = (
        "single_objective"
    )
    items: list[ObjectiveItem] = Field(default_factory=list, max_length=32)


class ConstraintItem(Contract):
    recipe: str = ""
    limit: StrictFloat | StrictInt | None = Field(default=None, ge=0)
    unit: str | None = None
    basis: str = Field(default="", max_length=10000)


class ConstraintSet(Contract):
    items: list[ConstraintItem] = Field(default_factory=list, max_length=100)


class DecisionSpec(Contract):
    template: str = ""
    actions: list[str] = Field(default_factory=list, max_length=10)


SCHEMAS = {"objectives": ObjectiveSet, "constraints": ConstraintSet, "decisions": DecisionSpec}


def fail(code, message, **details):
    raise Problem(422, code, message, details)


def validate_body(kind, body, publish=False):
    try:
        model = SCHEMAS[kind].model_validate(body)
    except ValidationError as exc:
        fail(
            "PLANNING_FIELDS_INVALID",
            "规划内容格式不正确",
            fields=[".".join(map(str, e["loc"])) for e in exc.errors()],
        )
    value = model.model_dump(exclude_none=True)
    if not publish:
        return value
    if kind == "objectives":
        items = value["items"]
        if (
            not items
            or (value["mode"] == "single_objective" and len(items) != 1)
            or (value["mode"] != "single_objective" and len(items) < 2)
        ):
            fail("OBJECTIVE_COUNT", "单目标需要一项目标，多目标至少需要两项")
        if len({i["metric"] for i in items}) != len(items):
            fail("OBJECTIVE_DUPLICATE", "同一目标不能重复添加")
        for item in items:
            if item["metric"] not in METRICS:
                fail("METRIC_NOT_IMPLEMENTED", "所选目标尚无可执行度量", metric=item["metric"])
        if value["mode"] == "weighted_multiobjective":
            if any("weight" not in i for i in items) or not math.isclose(
                sum(i["weight"] for i in items), 1.0, abs_tol=1e-9
            ):
                fail("OBJECTIVE_WEIGHTS", "请明确各目标权重，合计必须为1")
        elif any("weight" in i for i in items):
            fail("OBJECTIVE_WEIGHT_SCOPE", "当前模式不使用权重，不得静默忽略权重")
    elif kind == "constraints":
        for item in value["items"]:
            recipe = CONSTRAINTS.get(item["recipe"])
            if not recipe:
                fail("CONSTRAINT_NOT_IMPLEMENTED", "所选约束尚无编译实现")
            if not item["basis"].strip():
                fail(
                    "CONSTRAINT_BASIS_REQUIRED",
                    "请提供此约束的适用依据；系统不代设政策阈值",
                    recipe=item["recipe"],
                )
            if recipe["limit_required"] and ("limit" not in item or not item.get("unit")):
                fail("CONSTRAINT_LIMIT_REQUIRED", "此约束需要明确上限和单位")
            if not recipe["limit_required"] and ("limit" in item or item.get("unit")):
                fail("CONSTRAINT_UNUSED_PARAMETER", "避让约束不使用数值上限或单位")
            if item["recipe"] == "development_quota":
                area_limit(item)
    elif kind == "decisions":
        template = DECISIONS.get(value["template"])
        if not template or value["actions"] != [template["action"]]:
            fail("DECISION_NOT_IMPLEMENTED", "请选择已实现的决策模板和对应的允许改变事项")
    return value


def area_limit(item):
    factors = {"m^2": 1.0, "ha": 10000.0, "km^2": 1e6}
    if item.get("unit") not in factors:
        fail("AREA_UNIT_REQUIRED", "开发面积上限仅接受平方米、公顷或平方千米")
    return item["limit"] * factors[item["unit"]]


def numeric_column(units, field):
    values = []
    for unit in units:
        value = unit.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            fail(
                "UNIT_VALUE_REQUIRED",
                "规划单元缺少合法数值，不以0补齐",
                unit_id=unit.get("id"),
                field=field,
            )
        values.append(float(value))
    return values


def objective_values(spec, units, decision):
    value = validate_body("objectives", spec, True)
    chosen = validate_body("decisions", decision, True)
    result = {}
    for item in value["items"]:
        metric = METRICS[item["metric"]]
        if chosen["template"] not in metric["templates"]:
            fail("OBJECTIVE_UNAFFECTED", "当前决策变量无法影响该目标", metric=item["metric"])
        result[item["metric"]] = numeric_column(units, metric["field"])
    return result


def compile_constraints(spec, units):
    value = validate_body("constraints", spec, True)
    compiled = []
    for item in value["items"]:
        recipe = CONSTRAINTS[item["recipe"]]
        row = {"recipe": item["recipe"], "recipe_version": VERSION, "basis": item["basis"]}
        if item["recipe"] == "ecological_redline_exclusion":
            if any(not isinstance(u.get("forbidden"), bool) for u in units):
                fail("EXCLUSION_MASK_REQUIRED", "避让约束需要经验证的逐单元空间相交结果")
            row["upper_bounds"] = [0 if u["forbidden"] else 1 for u in units]
        else:
            row.update(
                coefficients=numeric_column(units, recipe["field"]),
                upper=area_limit(item) if item["recipe"] == "development_quota" else item["limit"],
                unit=recipe["unit"],
            )
        compiled.append(row)
    return compiled


def catalog():
    return {
        "version": VERSION,
        "objectives": [
            {
                "code": k,
                **v,
                "status": "configurable",
                "implementation": "additive_selection_metric",
            }
            for k, v in METRICS.items()
        ],
        "constraints": [{"code": k, **v, "status": "configurable"} for k, v in CONSTRAINTS.items()],
        "decisions": [{"code": k, **v, "status": "configurable"} for k, v in DECISIONS.items()],
        "limitations": [
            "配置发布不等于输入匹配或求解通过",
            "仅支持已列出的选择型度量与约束；完整规划诊断、多用途分配和再评价仍待接通",
        ],
    }
