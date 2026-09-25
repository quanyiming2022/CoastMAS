"""Public task contracts describe user intent, not a generic JSON form."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

Purpose = Literal[
    "inspect",
    "spatial",
    "entities",
    "temporal",
    "assessment",
    "optimization",
    "cluster",
    "regression",
    "workflow",
    "research",
    "comparison",
    "simulation",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SignIn(Contract):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class SourceRef(Contract):
    asset_id: str
    revision: int = Field(ge=1)
    layer: str | None = None


class VariableBinding(Contract):
    asset_id: str
    field: str
    concept: str | None = None
    unit: str | None = None
    support: str | None = None
    template_id: str | None = None
    template_revision: int | None = Field(default=None, ge=1)
    role: Literal[
        "feature", "response", "identity", "time", "geometry", "constraint", "ignored"
    ] = "feature"


class TaskDraft(Contract):
    title: str = Field(min_length=1, max_length=200)
    purpose: Purpose
    selection: list[SourceRef] = Field(default_factory=list, max_length=200)
    mapping: list[VariableBinding] = Field(default_factory=list, max_length=500)
    method_id: str | None = None
    options: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def scope_source_references(self):
        selected = {source.asset_id for source in self.selection}
        for key in (
            "inherited_declarations",
            "declaration_references",
            "mapping_issues",
            "adaptations",
        ):
            entries = self.options.get(key)
            if isinstance(entries, dict):
                self.options[key] = {
                    asset_id: entry for asset_id, entry in entries.items() if asset_id in selected
                }
        return self

    @field_validator("options")
    @classmethod
    def bounded_non_secret_options(cls, value):
        if len(json.dumps(value, allow_nan=False)) > 64000:
            raise ValueError("draft options are too large; reference managed data instead")

        def check(item):
            if isinstance(item, dict):
                for key, nested in item.items():
                    if key.lower() in {
                        "password",
                        "token",
                        "credentials",
                        "secret",
                        "authorization",
                        "api_key",
                    }:
                        raise ValueError("credentials must never enter task drafts")
                    check(nested)
            elif isinstance(item, list):
                for nested in item:
                    check(nested)

        check(value)
        return value


RESEARCH_GOALS = {
    "comprehensive-assessment": {
        "label": "综合评价",
        "purpose": "assessment",
        "capability": "支持固定权重、AHP、熵权与TOPSIS；评价型PP尚未接入。",
    },
    "spatiotemporal-change": {
        "label": "时空变化分析",
        "purpose": "temporal",
        "capability": "已有时间适配与聚合；完整变化研究流程需继续接入。",
    },
    "spatial-regionalization": {
        "label": "空间聚类与分区",
        "purpose": "cluster",
        "capability": "使用经审批的真实聚类模型；不能把簇号当评价权重。",
    },
    "numerical-prediction": {
        "label": "数值建模与预测",
        "purpose": "regression",
        "capability": "需明确响应变量与训练验证依据，使用经审批的真实模型。",
    },
    "spatial-optimization": {
        "label": "空间布局优化",
        "purpose": "optimization",
        "capability": "需具备认可的目标、预算、成本与保护约束。",
    },
}


class NewTask(Contract):
    project_id: str
    title: str = Field(min_length=1, max_length=200)
    purpose: Purpose | None = None
    goal: str | None = None
    task_type: Literal["assessment", "simulation", "planning", "comparison"] | None = None

    @model_validator(mode="after")
    def goal_or_operator(self):
        if self.task_type is not None:
            if self.goal is not None or self.purpose is not None:
                raise ValueError("任务类型不能与旧研究目标或工具同时指定")
            self.purpose = {"assessment": "assessment", "simulation": "simulation", "planning": "optimization", "comparison": "comparison"}[self.task_type]
            return self
        if (self.goal is None) == (self.purpose is None):
            raise ValueError("请选择一个研究目标或独立工具，不同时指定")
        if self.goal is not None:
            if self.goal not in RESEARCH_GOALS:
                raise ValueError("未知研究目标")
            self.purpose = RESEARCH_GOALS[self.goal]["purpose"]
        return self


class SaveDraft(Contract):
    expected_revision: int = Field(ge=1)
    draft: TaskDraft
