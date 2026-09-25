import numpy as np
import pytest
from pydantic import ValidationError

from coastmas_next.builtin_operators import BuiltinOperatorRegistry, WeightSet
from coastmas_next.store import Problem


def test_core_operators_work_without_plugin_discovery(monkeypatch):
    import importlib.metadata

    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda **_: (_ for _ in ()).throw(AssertionError("No extension plugin needed")),
    )
    registry = BuiltinOperatorRegistry()
    matrix = [[1, 2 / 3, 2 / 5], [3 / 2, 1, 3 / 5], [5 / 2, 5 / 3, 1]]
    ahp = registry.execute("weight.ahp", {"labels": ["a", "b", "c"], "matrix": matrix})
    np.testing.assert_allclose(list(ahp["weights"].values()), [0.2, 0.3, 0.5], rtol=1e-12)
    for method in ["entropy", "critic", "standard_deviation", "coefficient_variation"]:
        result = registry.execute(
            "weight." + method,
            {"labels": ["a", "b"], "values": [[0.1, 0.2], [0.4, 0.3], [0.8, 0.9]]},
        )
        assert result["kind"] == "WeightSet"
        assert sum(result["weights"].values()) == pytest.approx(1.0)
    score = registry.execute(
        "evaluation.wlc",
        {"labels": ["b", "c", "a"], "values": [[0.6, 0.8, 0.4]], "weight_set": ahp},
    )
    assert score["scores"] == pytest.approx([0.66])
    assert score["contributions"][0] == pytest.approx([0.18, 0.4, 0.08])
    classified = registry.execute(
        "classification.fisher_jenks", {"values": [0, 0.3, 0.31, 0.7, 0.71, 1.0], "classes": 3}
    )
    assert classified["kind"] == "ClassScheme" and len(classified["breaks"]) == 3


def test_weight_and_reducer_types_are_not_interchangeable():
    registry = BuiltinOperatorRegistry()
    reduced = registry.execute(
        "reduction.pca", {"labels": ["x", "y"], "values": [[1, 2], [2, 1], [3, 4]], "components": 1}
    )
    assert reduced["kind"] == "ReductionResult" and "weights" not in reduced
    with pytest.raises((ValidationError, Problem)):
        registry.execute(
            "evaluation.wlc", {"labels": ["x", "y"], "values": [[0.4, 0.6]], "weight_set": reduced}
        )
    with pytest.raises((ValidationError, Problem)):
        registry.execute(
            "evaluation.wlc",
            {
                "labels": ["x", "y"],
                "values": [[0.4, 0.6]],
                "weight_set": {"kind": "ScoreResult", "scores": [0.6]},
            },
        )
    with pytest.raises(Problem):
        registry.execute("weight.pca", {"values": [[1, 2], [2, 3]]})


@pytest.mark.parametrize(
    "operator",
    [
        "weight.entropy",
        "weight.critic",
        "weight.standard_deviation",
        "weight.coefficient_variation",
    ],
)
def test_no_implicit_equal_weight_for_degenerate_data(operator):
    with pytest.raises(Problem):
        BuiltinOperatorRegistry().execute(
            operator, {"labels": ["a", "b"], "values": [[1, 1], [1, 1]]}
        )


def test_scoring_and_classification_boundaries():
    registry = BuiltinOperatorRegistry()
    assert registry.execute(
        "score.fixed_interval", {"values": [0, 0.5, 1], "lower": 0, "upper": 1, "positive": False}
    )["scores"] == [1, 0.5, 0]
    result = registry.execute(
        "classification.custom", {"values": [0, 0.3, 0.31, 0.7, 0.71, 1], "breaks": [0.3, 0.7, 1]}
    )
    assert result["classes"] == [1, 1, 2, 2, 3, 3]
    for code in [
        "fisher_jenks",
        "quantile",
        "equal_interval",
        "standard_deviation",
        "geometric_interval",
    ]:
        result = registry.execute(
            "classification." + code, {"values": [1, 2, 4, 8, 16, 32], "classes": 3}
        )
        assert min(result["classes"]) >= 1 and max(result["classes"]) <= 3
    for code in ["fisher_jenks", "quantile", "equal_interval"]:
        with pytest.raises(Problem):
            registry.execute("classification." + code, {"values": [1, 1, 1], "classes": 3})
    with pytest.raises(Problem):
        registry.execute("classification.geometric_interval", {"values": [0, 1, 2], "classes": 2})


def test_unknown_weight_profile_cannot_be_published_by_type_coercion():
    with pytest.raises(ValidationError):
        WeightSet(
            kind="WeightSet", weights={"a": 0.5, "b": -0.5}, profile="manual/1.0.0", diagnostics={}
        )
    with pytest.raises(ValidationError):
        WeightSet(
            kind="WeightSet", weights={"a": 0.4, "b": 0.5}, profile="manual/1.0.0", diagnostics={}
        )
