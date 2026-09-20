import pytest
from pydantic import ValidationError

from coastmas.core.matching import MatchWeights, match_models
from tests.factories import asset, model, scene, variable


def match(candidates, assets=None, **kwargs):
    return match_models(
        candidates,
        [asset()] if assets is None else assets,
        scene(),
        capability="screen",
        parameters={"increment": 0.5},
        **kwargs,
    )


def test_rejected_model_never_receives_score_even_with_maximum_preference():
    result = match(
        [model(id="bad", enabled=False), model(id="good")], preferences={"bad": 1.0, "good": 0.0}
    )
    assert [item.model_id for item in result.ranked] == ["good"]
    assert result.rejected[0].score is None
    assert "MODEL_DISABLED" in {issue.code for issue in result.rejected[0].issues}


def test_selects_valid_asset_after_invalid_and_records_actual_conversion():
    invalid = asset(id="invalid", vertical_datum="different")
    valid = asset(id="valid", variables=[variable(unit="cm")])
    result = match([model()], assets=[invalid, valid])
    assert len(result.ranked) == 1
    binding = result.ranked[0].workflow.input_bindings[0]
    assert binding.source.id == "valid"
    assert binding.unit_conversion == "cm -> m"


def test_unavailable_inputs_and_capability_return_actionable_rejections():
    result = match([model(capabilities=["other"])], assets=[])
    assert not result.ranked
    assert {issue.code for issue in result.rejected[0].issues} >= {"CAPABILITY", "INPUT_MISSING"}


def test_invalid_asset_failure_is_retained_in_explanation():
    result = match([model()], assets=[asset(vertical_datum="different")])
    assert "VERTICAL_DATUM" in {issue.code for issue in result.rejected[0].issues}


def test_ranking_weights_change_order_without_affecting_hard_filter():
    candidates = [model(id="slow"), model(id="fast")]
    by_cost = match(
        candidates,
        runtime_seconds={"slow": 10, "fast": 1},
        weights=MatchWeights(
            runtime_cost=1,
            user_preference=0,
            capability=0,
            data_availability=0,
            scale_fitness=0,
            validation_evidence=0,
        ),
    )
    assert [item.model_id for item in by_cost.ranked] == ["fast", "slow"]
    by_preference = match(
        candidates,
        preferences={"slow": 1, "fast": 0},
        weights=MatchWeights(
            runtime_cost=0,
            user_preference=1,
            capability=0,
            data_availability=0,
            scale_fitness=0,
            validation_evidence=0,
        ),
    )
    assert [item.model_id for item in by_preference.ranked] == ["slow", "fast"]
    assert by_preference.ranked[0].components["runtime_cost"] is None


def test_deterministic_ties_and_duplicate_versions_rejected():
    assert [item.model_id for item in match([model(id="b"), model(id="a")]).ranked] == ["a", "b"]
    with pytest.raises(ValueError, match="duplicate"):
        match([model(), model()])


def test_scoring_configuration_rejects_nonfinite_or_invalid_values():
    with pytest.raises(ValidationError):
        MatchWeights(runtime_cost=-1)
    with pytest.raises(ValidationError):
        MatchWeights(user_preference=float("nan"))
    with pytest.raises(ValueError):
        match([model()], runtime_seconds={"screen": -1})
    with pytest.raises(ValueError):
        match([model()], preferences={"screen": 2})
