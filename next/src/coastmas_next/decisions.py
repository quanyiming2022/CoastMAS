"""Approved method templates bind real assets to reliable scientific kernels."""

import math
from dataclasses import asdict
from typing import Annotated, Literal

import numpy as np
from coastmas.core.contracts import UNITS
from coastmas.core.errors import CoastMASError
from coastmas.core.optimization import CandidateUnit
from coastmas.domain.assessment import composite, entropy_weights, normalize, topsis
from coastmas.domain.optimization import optimize_units
from pydantic import Field, StrictBool, model_validator
from sqlalchemy import select

from .ahp import AhpDefinition, derive_weights
from .contracts import Contract
from .observations import quantity, read_rows
from .reuse import TemplateScope, templates
from .store import Problem

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]


def validate_unit(unit):
    try:
        UNITS.Unit(unit)
    except Exception as exc:
        raise ValueError("Unknown or invalid scientific unit") from exc


class Indicator(Contract):
    concept: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    lower: Number
    upper: Number
    positive: StrictBool
    weight: Annotated[Number, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def interval(self):
        validate_unit(self.unit)
        if self.upper <= self.lower:
            raise ValueError("Reference interval must be increasing")
        return self


class AssessmentMethod(Contract):
    task: Literal["assessment"]
    method: Literal["weighted", "entropy", "topsis"]
    indicators: list[Indicator] = Field(min_length=1, max_length=64)
    weighting: AhpDefinition | None = None

    @model_validator(mode="after")
    def explicit_weights(self):
        if self.weighting is not None:
            if self.method != "weighted":
                raise ValueError("AHP判断仅用于明确的加权综合，不混用熵权或TOPSIS")
            value = self.weighting
            report = derive_weights(
                value.labels,
                value.matrix,
                [i.concept for i in self.indicators],
                value.consistency_limit,
            )
            for indicator, weight in zip(self.indicators, report["weights"], strict=True):
                indicator.weight = weight
        if len({i.concept for i in self.indicators}) != len(self.indicators):
            raise ValueError("Indicator concepts must be unique")
        if self.method != "entropy" and (
            any(i.weight is None for i in self.indicators)
            or sum(i.weight for i in self.indicators) <= 0
        ):
            raise ValueError("Reviewed weights are required, never implicit equal weights")
        if self.method != "entropy" and not math.isclose(
            sum(i.weight for i in self.indicators), 1.0, abs_tol=1e-8
        ):
            raise ValueError("评价权重之和必须为1；不得静默重算未认可的相对权重")
        if self.method == "entropy" and any(i.weight is not None for i in self.indicators):
            raise ValueError(
                "Entropy method derives its weights; do not silently ignore declared weights"
            )
        return self


class Quantity(Contract):
    concept: str = Field(min_length=1)
    unit: str = Field(min_length=1)


class OptimizationMethod(Contract):
    task: Literal["optimization"]
    method: Literal["binary_allocation"]
    quantities: dict[str, Quantity]
    protected_concept: str = Field(min_length=1)
    risk_aggregation: Literal["additive_index"]
    additivity_basis: str = Field(min_length=1, max_length=10000)
    budget: Annotated[Number, Field(ge=0)]
    minimum_area: Annotated[Number, Field(ge=0)]
    maximum_ecological_cost: Annotated[Number, Field(ge=0)]
    maximum_risk: Annotated[Number, Field(ge=0)]
    time_limit: Annotated[Number, Field(gt=0, le=120)]

    @model_validator(mode="after")
    def required_quantities(self):
        if set(self.quantities) != {"benefit", "cost", "area", "ecological_cost", "risk"}:
            raise ValueError("All five quantity definitions are required")
        for definition in self.quantities.values():
            validate_unit(definition.unit)
        if UNITS.get_dimensionality(self.quantities["area"].unit) != UNITS.get_dimensionality(
            "m^2"
        ):
            raise ValueError("Area reference must use an area unit")
        return self


def method_snapshot(store, actor, project, draft, sources):
    with store.engine.connect() as c:
        store.permission(c, actor, project)
        method = (
            c.execute(
                select(templates).where(
                    templates.c.id == draft.get("method_id"), templates.c.project_id == project
                )
            )
            .mappings()
            .first()
        )
        if method is None or method["spec"]["purpose"] != "method":
            raise Problem(422, "METHOD_REQUIRED", "请选择适用的认可方法模板，无需手写数据矩阵")
        from .method_library import method_version

        method = method_version(
            c, method["id"], draft["options"].get("method_revision"), approved=True
        )
        if any(
            a["facts"]["profile"] not in method["spec"]["profiles"]
            or not TemplateScope.model_validate(method["spec"].get("scope", {})).matches(a)
            for a in sources
        ):
            raise Problem(422, "METHOD_SCOPE", "所选资料不符合认可方法的适用范围")
        configuration = method["spec"]["configuration"]
        if configuration.get("task") != draft["purpose"]:
            raise Problem(422, "METHOD_TASK", "方法模板与当前任务目的不匹配")
        return dict(method)


def prepare(settings, manifest, method):
    rows, bindings = read_rows(
        settings, manifest, limit=5000 if manifest["draft"]["purpose"] == "optimization" else 100000
    )
    configuration = method["spec"]["configuration"]

    def mapped(concept):
        if concept not in bindings:
            raise Problem(
                422,
                "CONCEPT_MAPPING_REQUIRED",
                "需要把实际字段映射到方法含义",
                {"concept": concept},
            )
        return bindings[concept]

    if manifest["draft"]["purpose"] == "assessment":
        spec = AssessmentMethod.model_validate(configuration)
        matrix = np.asarray(
            [
                [
                    quantity(row, mapped(indicator.concept), indicator.unit)
                    for indicator in spec.indicators
                ]
                for row in rows
            ]
        )
        normalized = normalize(
            matrix,
            [i.lower for i in spec.indicators],
            [i.upper for i in spec.indicators],
            [i.positive for i in spec.indicators],
        )
        return rows, spec, normalized
    spec = OptimizationMethod.model_validate(configuration)
    protected = mapped(spec.protected_concept)
    units = []
    for row in rows:
        raw = row["properties"].get(protected["native"]["name"])
        if isinstance(raw, str) and raw.lower() in {"true", "false"}:
            raw = raw.lower() == "true"
        if not isinstance(raw, bool):
            raise Problem(
                422,
                "PROTECTION_UNKNOWN",
                "保护准入必须有明确布尔依据，未知不能默认允许",
                {"row": row["id"]},
            )
        values = {
            name: quantity(row, mapped(item.concept), "m^2" if name == "area" else item.unit)
            for name, item in spec.quantities.items()
        }
        units.append(CandidateUnit(id=row["id"], allowed=not raw, **values))
    return rows, spec, units


def preflight(store, actor, task, sources):
    method = method_snapshot(store, actor, task["project_id"], task["draft"], sources)
    try:
        manifest = {"draft": task["draft"], "assets": sources}
        from .raster_assessment import applicable, inputs

        if task["draft"]["purpose"] == "assessment" and applicable(manifest):
            inputs(
                store.settings,
                manifest,
                AssessmentMethod.model_validate(method["spec"]["configuration"]),
            )
        else:
            prepare(store.settings, manifest, method)
    except CoastMASError as exc:
        raise Problem(422, exc.code, str(exc)) from exc
    return method


def compute(store, manifest, cancelled, artifact_dir=None):
    frozen = manifest["method"]
    current = method_snapshot(
        store, manifest["actor"], manifest["project_id"], manifest["draft"], manifest["assets"]
    )
    if current["revision"] != frozen["revision"] or current["spec"] != frozen["spec"]:
        raise Problem(422, "METHOD_CHANGED", "已固定方法资格改变，当前任务不继续计算")
    from .raster_assessment import applicable
    from .raster_assessment import compute as raster_compute

    if manifest["draft"]["purpose"] == "assessment" and applicable(manifest):
        return raster_compute(
            store.settings,
            manifest,
            AssessmentMethod.model_validate(frozen["spec"]["configuration"]),
            cancelled,
            artifact_dir,
        )
    rows, spec, prepared = prepare(store.settings, manifest, frozen)
    if cancelled.is_set():
        raise Problem(409, "CANCELLED", "任务已取消")
    if isinstance(spec, AssessmentMethod):
        weights = (
            entropy_weights(prepared)
            if spec.method == "entropy"
            else np.asarray([i.weight for i in spec.indicators], dtype=float)
        )
        scores = (
            topsis(prepared, weights, [True] * len(spec.indicators))
            if spec.method == "topsis"
            else composite(prepared, weights)
        )
        from .observation_space import spatial_result

        spatial = spatial_result(
            rows,
            manifest,
            [
                {
                    "assessment_score": float(score),
                    "rank": int(1 + np.count_nonzero(scores > score)),
                }
                for score in scores
            ],
        )
        return {
            **spatial,
            "row_ids": [r["id"] for r in rows],
            "scores": scores.tolist(),
            "ranks": [int(1 + np.count_nonzero(scores > value)) for value in scores],
            "weights": (weights / weights.sum()).tolist(),
            "normalized_values": prepared.tolist(),
            "contributions": (prepared * (weights / weights.sum())).tolist()
            if spec.method != "topsis"
            else None,
            "weight_evidence": (
                derive_weights(
                    spec.weighting.labels,
                    spec.weighting.matrix,
                    [i.concept for i in spec.indicators],
                    spec.weighting.consistency_limit,
                )
                if spec.weighting
                else {"method": spec.method, "scope": "complete_selected_observations"}
            ),
            "method_snapshot": frozen,
            "scope": "complete_selected_observations",
            "business_validated": False,
        }
    outcome = optimize_units(
        prepared,
        budget=spec.budget,
        minimum_area=float(
            UNITS.Quantity(spec.minimum_area, spec.quantities["area"].unit).to("m^2").magnitude
        ),
        maximum_ecological_cost=spec.maximum_ecological_cost,
        maximum_risk=spec.maximum_risk,
        time_limit=spec.time_limit,
    )
    from .observation_space import spatial_result

    spatial = spatial_result(
        rows,
        manifest,
        [
            {
                "selected": unit.id in outcome.selected if outcome.constraints_satisfied else None,
                "allowed": unit.allowed,
            }
            for unit in prepared
        ],
    )
    return {
        **spatial,
        **asdict(outcome),
        "row_ids": [r["id"] for r in rows],
        "allocations": [
            {
                **unit.model_dump(),
                "selected": unit.id in outcome.selected if outcome.constraints_satisfied else None,
            }
            for unit in prepared
        ],
        "method_snapshot": frozen,
        "scope": "complete_selected_units",
        "area_unit": "m^2",
        "policy_decision": False,
        "business_validated": False,
    }
