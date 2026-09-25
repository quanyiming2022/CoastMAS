"""Draft structure is strict; scientific completeness belongs to publication."""

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictStr, ValidationError

from .contracts import Contract
from .store import Problem

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class DraftIndicator(Contract):
    concept: StrictStr = ""
    unit: StrictStr = ""
    lower: Number | None = None
    upper: Number | None = None
    positive: StrictBool | None = None
    weight: Number | None = None


class DraftWeighting(Contract):
    method: StrictStr = "ahp"
    labels: list[StrictStr] = Field(default_factory=list, max_length=10)
    matrix: list[list[Number | None]] = Field(default_factory=list, max_length=10)
    consistency_limit: Number | None = None
    source: dict | None = None


class DraftQuantity(Contract):
    concept: StrictStr = ""
    unit: StrictStr = ""


class DraftConfiguration(Contract):
    task: StrictStr = ""
    method: StrictStr = ""
    indicators: list[DraftIndicator] | None = None
    weighting: DraftWeighting | None = None
    quantities: dict[str, DraftQuantity] | None = None
    protected_concept: StrictStr | None = None
    risk_aggregation: StrictStr | None = None
    additivity_basis: StrictStr | None = None
    budget: Number | None = None
    minimum_area: Number | None = None
    maximum_ecological_cost: Number | None = None
    maximum_risk: Number | None = None
    time_limit: Number | None = None


class DraftDefinition(Contract):
    title: Annotated[StrictStr, Field(max_length=200)] = ""
    purpose: Literal["method"] = "method"
    basis: Annotated[StrictStr, Field(max_length=10000)] = ""
    profiles: list[StrictStr] = Field(default_factory=list, max_length=20)
    configuration: DraftConfiguration = Field(default_factory=DraftConfiguration)
    scope: dict = Field(default_factory=dict)
    rules: list[dict] = Field(default_factory=list, max_length=500)
    declaration: dict = Field(default_factory=dict)


def validate_draft(value):
    try:
        DraftDefinition.model_validate(value)
    except ValidationError as exc:
        raise Problem(
            422,
            "METHOD_DRAFT_STRUCTURE",
            "草稿包含类型不正确的字段，请核对后保存。",
            {"issues": business_issues(exc)},
        ) from exc


def business_issues(exc):
    labels = {
        "title": "方法名称",
        "basis": "方法依据",
        "profiles": "适用资料格式",
        "indicators": "评价指标",
        "concept": "指标含义",
        "unit": "单位",
        "lower": "参考下限",
        "upper": "参考上限",
        "positive": "评分方向",
        "weight": "权重",
        "weighting": "判断矩阵",
        "configuration": "方法配置",
    }
    result = []
    if not isinstance(exc, ValidationError):
        return [
            {"field": "configuration", "message": "方法配置不满足发布条件，请核对当前算法及参数。"}
        ]
    for e in exc.errors(include_url=False, include_input=False, include_context=False):
        loc = e["loc"]
        key = str(loc[-1]) if loc else "configuration"
        field = (
            "basis"
            if "basis" in loc
            else "indicators"
            if "indicators" in loc
            else "weighting"
            if "weighting" in loc
            else key
        )
        if key == "basis":
            message = "请补充方法依据，或选择已有依据。"
        elif key == "indicators" and e["type"] in {"too_short", "missing"}:
            message = "请至少添加一个评价指标。"
        elif e["type"] == "value_error" and "indicators" in loc:
            message = "请核对指标单位与参考范围，参考上限须大于下限。"
        elif e["type"] == "value_error" and not loc:
            message = "请核对指标是否重复及当前赋权要求；手工权重须完整且合计为1。"
        else:
            message = f"请核对{labels.get(key, '该字段')}的类型和必要内容。"
        indexes = [x for x in loc if isinstance(x, int)]
        if indexes:
            message = f"第{indexes[0] + 1}项：" + message
        item = {"field": field, "message": message}
        if item not in result:
            result.append(item)
    return result
