"""Installed, typed deterministic operators; extension discovery is never a core dependency."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import Field, StrictBool, ValidationError, model_validator

from .ahp import derive_weights
from .contracts import Contract
from .store import Problem


class WeightSet(Contract):
    kind: Literal["WeightSet"] = "WeightSet"
    weights: dict[str, float]
    profile: str
    diagnostics: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_weights(self):
        values = np.array(list(self.weights.values()))
        if (
            not self.weights
            or not np.isfinite(values).all()
            or (values < 0).any()
            or not np.isclose(values.sum(), 1, rtol=0, atol=1e-10)
        ):
            raise ValueError("权重必须有限、非负且合计为1")
        return self


class MatrixInput(Contract):
    labels: list[str] = Field(min_length=1, max_length=64)
    values: list[list[float]] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def bounded_matrix(self):
        if len(set(self.labels)) != len(self.labels) or any(
            len(r) != len(self.labels) for r in self.values
        ):
            raise ValueError("指标身份必须唯一，矩阵列必须完整对应")
        if len(self.values) * len(self.labels) > 64000:
            raise ValueError("矩阵超过轻量计算预算，使用受管数据和异步全域运行")
        return self


class WLCInput(MatrixInput):
    weight_set: WeightSet


class PCAInput(MatrixInput):
    components: int = Field(default=1, ge=1, le=64)


class AhpInput(Contract):
    labels: list[str] = Field(min_length=1, max_length=10)
    matrix: list[list[float | None]]
    consistency_limit: float = Field(default=0.1, gt=0, le=0.1)


class ManualInput(Contract):
    weights: dict[str, float]


class EqualInput(Contract):
    labels: list[str] = Field(min_length=1, max_length=64)


class IntervalInput(Contract):
    values: list[float] = Field(min_length=1, max_length=64000)
    lower: float
    upper: float
    positive: StrictBool


class ValuesInput(Contract):
    values: list[float] = Field(min_length=2, max_length=64000)


class CategoryInput(ValuesInput):
    mapping: dict[str, float]


class ClassInput(ValuesInput):
    classes: int = Field(default=5, ge=2, le=30)


class CustomClassInput(ValuesInput):
    breaks: list[float] = Field(min_length=1, max_length=30)


def failure(code, message):
    raise Problem(422, code, message)


def estimate(method, body):
    matrix = np.array(body.values, dtype=float)
    if matrix.shape[0] < 2 or not np.isfinite(matrix).all():
        failure("WEIGHT_DATA", "至少需要两条完整、有限的标准化观测")
    if (matrix < 0).any() or (matrix > 1).any():
        failure("WEIGHT_SCORE_DOMAIN", "此赋权档案要求已按目标方向标准化的0—1评分")
    std = matrix.std(axis=0, ddof=0)
    if method == "entropy":
        totals = matrix.sum(axis=0)
        if (totals <= 0).any():
            failure(
                "ENTROPY_ZERO_COLUMN",
                "存在合计为零的指标，无法定义熵比例，请调整指标集合或选择有依据的其他方法",
            )
        proportions = matrix / totals
        logs = np.zeros_like(proportions)
        np.log(proportions, out=logs, where=proportions > 0)
        information = 1 + (proportions * logs).sum(axis=0) / np.log(matrix.shape[0])
        information[std <= np.finfo(float).eps] = 0
    elif method == "critic":
        centered = matrix - matrix.mean(axis=0)
        cross = centered.T @ centered / matrix.shape[0]
        denominator = np.outer(std, std)
        corr = np.divide(cross, denominator, out=np.ones_like(cross), where=denominator > 0)
        corr = np.clip(corr, -1, 1)
        information = std * (1 - corr).sum(axis=1)
    elif method == "coefficient_variation":
        mean = matrix.mean(axis=0)
        if (mean <= 0).any():
            failure("CV_MEAN", "变异系数要求正均值，不能对零或负均值自动赋权")
        information = std / mean
    else:
        information = std
    information = np.maximum(information, 0)
    if information.sum() <= 1e-14:
        failure("WEIGHT_DEGENERATE", "指标没有可辨识差异，不能自动改为等权；请选择有依据的赋权方法")
    return WeightSet(
        weights=dict(zip(body.labels, (information / information.sum()).tolist(), strict=True)),
        profile=method + "/1.0.0",
        diagnostics={
            "sample_count": len(matrix),
            "fit_scope": "provided_complete_matrix",
            "constant_indicators": [body.labels[i] for i in np.flatnonzero(std == 0)],
            "ddof": 0,
        },
    ).model_dump()


def ahp(body):
    report = derive_weights(body.labels, body.matrix, body.labels, body.consistency_limit)
    return WeightSet(
        weights=dict(zip(body.labels, report["weights"], strict=True)),
        profile="ahp_eigenvector/1.0.0",
        diagnostics=report,
    ).model_dump()


def wlc(body):
    if set(body.labels) != set(body.weight_set.weights):
        failure("WEIGHT_IDENTITY", "权重与指标身份不一致")
    values = np.array(body.values)
    weights = np.array([body.weight_set.weights[k] for k in body.labels])
    if (values < 0).any() or (values > 1).any():
        failure("SCORE_DOMAIN", "WLC要求已标准化的0—1评分")
    contributions = values * weights
    return {
        "kind": "ScoreResult",
        "profile": "wlc/1.0.0",
        "scores": contributions.sum(axis=1).tolist(),
        "contributions": contributions.tolist(),
        "labels": body.labels,
        "weight_set": body.weight_set.model_dump(),
    }


def topsis(body):
    from coastmas.core.errors import ConstraintError
    from coastmas.domain.assessment import topsis as calculate

    if set(body.labels) != set(body.weight_set.weights):
        failure("WEIGHT_IDENTITY", "权重与指标身份不一致")
    try:
        values = calculate(
            body.values,
            [body.weight_set.weights[k] for k in body.labels],
            [True] * len(body.labels),
        )
    except ConstraintError as exc:
        raise Problem(422, "TOPSIS_DEGENERATE", "TOPSIS理想解退化，无法作有效排序") from exc
    return {
        "kind": "ScoreResult",
        "profile": "topsis/1.0.0",
        "scores": values.tolist(),
        "contributions": None,
        "fit_scope": "provided_complete_matrix",
        "weight_set": body.weight_set.model_dump(),
    }


def pca(body):
    values = np.array(body.values)
    if len(values) < 2 or body.components > min(values.shape):
        failure("PCA_DIMENSION", "PCA样本量或分量数不适用")
    mean = values.mean(axis=0)
    scale = values.std(axis=0, ddof=0)
    if (scale <= 1e-14).any():
        failure("PCA_CONSTANT", "PCA存在常量列，请明确处理规则后再拟合")
    standardized = (values - mean) / scale
    _, singular, components = np.linalg.svd(standardized, full_matrices=False)
    # Fix the mathematical sign ambiguity, not an ecological scoring direction.
    signs = np.sign(components[np.arange(len(components)), np.abs(components).argmax(axis=1)])
    components *= signs[:, None]
    return {
        "kind": "ReductionResult",
        "profile": "pca_standardized_svd/1.0.0",
        "labels": body.labels,
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "components": components[: body.components].tolist(),
        "transformed_features": (standardized @ components[: body.components].T).tolist(),
        "explained_variance_ratio": (singular**2 / (singular**2).sum())[: body.components].tolist(),
        "sign_convention": "largest_absolute_loading_positive",
        "evaluation_meaning": None,
    }


def interval(body):
    x = np.array(body.values)
    if body.upper <= body.lower or (x < body.lower).any() or (x > body.upper).any():
        failure("SCORING_RANGE", "固定评分范围无效或数据越界；未静默截断")
    y = (x - body.lower) / (body.upper - body.lower)
    return {
        "kind": "ScoreResult",
        "profile": "fixed_interval/1.0.0",
        "scores": (y if body.positive else 1 - y).tolist(),
    }


def zscore(body):
    x = np.array(body.values)
    std = x.std(ddof=0)
    if std <= 1e-14:
        failure("ZSCORE_CONSTANT", "常量数据不能使用此Z-score档案")
    return {
        "kind": "StandardizedValues",
        "profile": "zscore_population/1.0.0",
        "values": ((x - x.mean()) / std).tolist(),
        "mean": float(x.mean()),
        "std": float(std),
        "bounded_0_1": False,
    }


def categories(body):
    missing = sorted(
        {str(int(v)) if v.is_integer() else str(v) for v in body.values} - body.mapping.keys()
    )
    if missing:
        failure("CATEGORY_UNKNOWN", "部分类别缺少评分依据：" + "、".join(missing))
    return {
        "kind": "ScoreResult",
        "profile": "category_map/1.0.0",
        "scores": [body.mapping[str(int(v)) if v.is_integer() else str(v)] for v in body.values],
    }


def classify(method, body):
    values = np.array(body.values)
    unique = np.unique(values)
    if method == "custom":
        breaks = np.array(body.breaks)
    else:
        k = body.classes
        if len(unique) < k:
            failure("CLASS_UNIQUE", "唯一值数量少于类别数，请减少类别数")
        if method == "fisher_jenks":
            import jenkspy

            breaks = np.array(jenkspy.jenks_breaks(values, n_classes=k)[1:])
        elif method == "quantile":
            breaks = np.quantile(values, np.linspace(0, 1, k + 1)[1:])
        elif method == "equal_interval":
            breaks = np.linspace(values.min(), values.max(), k + 1)[1:]
        elif method == "geometric_interval":
            if values.min() <= 0:
                failure("GEOMETRIC_POSITIVE", "此正值几何区间档案不适用零或负值")
            breaks = np.geomspace(values.min(), values.max(), k + 1)[1:]
        else:
            std = values.std(ddof=0)
            inner = values.mean() + std * (np.arange(1, k) - k / 2)
            if (inner <= values.min()).any() or (inner >= values.max()).any():
                failure("STDDEV_BREAKS", "标准差断点超出观测范围，请减少类别数或更换分级方法")
            breaks = np.r_[inner, values.max()]
    if (np.diff(breaks) <= 0).any() or breaks[-1] < values.max():
        failure("CLASS_BREAKS", "断点必须严格递增并覆盖实际最大值")
    labels = np.searchsorted(breaks, values, side="left") + 1
    return {
        "kind": "ClassScheme",
        "profile": method + "/1.0.0",
        "breaks": breaks.tolist(),
        "classes": labels.tolist(),
        "closure": "first includes minimum, then (lower,upper]",
        "fit_scope": "provided_complete_values",
        "sample_count": len(values),
        "labels": [f"第{i + 1}组" for i in range(len(breaks))],
        "semantic_basis": None,
    }


@dataclass(frozen=True)
class Operator:
    code: str
    name: str
    kind: Literal[
        "WeightEstimator", "DirectEvaluator", "DimensionalityReducer", "Scorer", "Classifier"
    ]
    input_type: type[Contract]
    output_type: str
    locality: str
    run: Callable
    version: str = "1.0.0"


class BuiltinOperatorRegistry:
    def __init__(self):
        items = [
            Operator(
                "weight.ahp", "AHP", "WeightEstimator", AhpInput, "WeightSet", "GLOBAL_FIT", ahp
            ),
            Operator(
                "weight.manual",
                "专家直接赋权",
                "WeightEstimator",
                ManualInput,
                "WeightSet",
                "LOCAL",
                lambda b: WeightSet(weights=b.weights, profile="manual/1.0.0").model_dump(),
            ),
            Operator(
                "weight.equal",
                "等权",
                "WeightEstimator",
                EqualInput,
                "WeightSet",
                "LOCAL",
                self.equal,
            ),
            Operator(
                "evaluation.wlc",
                "WLC",
                "DirectEvaluator",
                WLCInput,
                "ScoreResult",
                "GLOBAL_APPLY",
                wlc,
            ),
            Operator(
                "evaluation.topsis",
                "TOPSIS",
                "DirectEvaluator",
                WLCInput,
                "ScoreResult",
                "GLOBAL_FIT",
                topsis,
            ),
            Operator(
                "reduction.pca",
                "PCA",
                "DimensionalityReducer",
                PCAInput,
                "ReductionResult",
                "GLOBAL_FIT",
                pca,
            ),
            Operator(
                "score.fixed_interval",
                "固定区间 Min-Max",
                "Scorer",
                IntervalInput,
                "ScoreResult",
                "GLOBAL_APPLY",
                interval,
            ),
            Operator(
                "score.zscore",
                "Z-score",
                "Scorer",
                ValuesInput,
                "StandardizedValues",
                "GLOBAL_FIT",
                zscore,
            ),
            Operator(
                "score.category",
                "类别评分",
                "Scorer",
                CategoryInput,
                "ScoreResult",
                "GLOBAL_APPLY",
                categories,
            ),
        ]
        for method, name in [
            ("entropy", "熵权法"),
            ("critic", "CRITIC"),
            ("standard_deviation", "标准差法"),
            ("coefficient_variation", "变异系数法"),
        ]:
            items.append(
                Operator(
                    "weight." + method,
                    name,
                    "WeightEstimator",
                    MatrixInput,
                    "WeightSet",
                    "GLOBAL_FIT",
                    lambda b, m=method: estimate(m, b),
                )
            )
        for method, name in [
            ("fisher_jenks", "Fisher-Jenks"),
            ("quantile", "分位数"),
            ("equal_interval", "等距"),
            ("standard_deviation", "标准差分级"),
            ("geometric_interval", "正值几何区间"),
            ("custom", "自定义阈值"),
        ]:
            items.append(
                Operator(
                    "classification." + method,
                    name,
                    "Classifier",
                    CustomClassInput if method == "custom" else ClassInput,
                    "ClassScheme",
                    "GLOBAL_FIT",
                    lambda b, m=method: classify(m, b),
                )
            )
        self.operators = {item.code: item for item in items}

    @staticmethod
    def require_indicator(indicator_id, version=None):
        from .indicator_registry import require_definition

        return require_definition(indicator_id, version)

    @staticmethod
    def compute_indicator(settings, manifest, cancelled, artifact_dir):
        from .indicator_kernels_v1 import compute

        return compute(settings, manifest, cancelled, artifact_dir)

    @staticmethod
    def equal(body):
        if len(set(body.labels)) != len(body.labels):
            failure("WEIGHT_IDENTITIES", "指标身份重复")
        return WeightSet(
            weights={k: 1 / len(body.labels) for k in body.labels}, profile="equal/1.0.0"
        ).model_dump()

    def execute(self, code, payload):
        item = self.operators.get(code)
        if item is None:
            failure("OPERATOR_NOT_INSTALLED", "没有已发布的此类内置算子")
        try:
            return item.run(item.input_type.model_validate(payload))
        except ValidationError as exc:
            raise Problem(
                422,
                "OPERATOR_CONTRACT",
                "输入不符合所选方法；权重、评价分数和降维结果不能混用",
                {"fields": [".".join(map(str, e["loc"])) for e in exc.errors()]},
            ) from exc
