"""Explicit-unit optimization inputs and truthful infeasibility output."""

import pytest
from pydantic import ValidationError

from coastmas.core.optimization import OptimizationFrame
from coastmas.domain.optimization_components import optimize_component
from tests.factories import scene


def optimization_input(**changes):
    value = {
        "units": [
            {
                "id": "protected",
                "benefit": 1000000,
                "cost": 1,
                "area": 1,
                "ecological_cost": 0,
                "risk": 0,
                "allowed": True,
            },
            {
                "id": "a",
                "benefit": 5,
                "cost": 2,
                "area": 1,
                "ecological_cost": 1,
                "risk": 1,
                "allowed": True,
            },
            {
                "id": "b",
                "benefit": 8,
                "cost": 3,
                "area": 2,
                "ecological_cost": 1,
                "risk": 1,
                "allowed": True,
            },
        ],
        "area_unit": "ha",
        "benefit_unit": "1",
        "cost_unit": "1",
        "ecological_cost_unit": "1",
        "risk_unit": "1",
        "budget": 3,
        "minimum_area": 1,
        "maximum_ecological_cost": 2,
        "maximum_risk": 2,
        "protected_unit_ids": ["protected"],
        "risk_aggregation": "additive_index",
        "additivity_basis": "SYNTHETIC additive scores; risk is not probability",
        "data_label": "SYNTHETIC",
    }
    value.update(changes)
    return value


def test_unit_aware_allocation_retains_constraints_and_never_selects_protected_high_score():
    selected = scene()
    result = optimize_component(
        {"scene": selected.model_dump(mode="json")},
        {"candidates": optimization_input()},
        {"time_limit": 5},
    )["allocation"]
    assert result["status"] == "OPTIMAL"
    assert result["selected"] == ["b"]
    assert result["totals"]["benefit"] == 8
    assert result["totals"]["area"] == 20000
    assert result["area_unit"] == "m^2"
    assert result["constraints_satisfied"] is True
    assert result["policy_decision"] is False
    assert result["checks"]["budget"]["actual"] == 3
    assert result["checks"]["minimum_area"]["bound"] == 10000
    assert (
        next(row for row in result["allocations"] if row["id"] == "protected")["selected"] is False
    )


def test_infeasible_result_has_no_invented_allocation_or_totals():
    result = optimize_component(
        {"scene": scene().model_dump(mode="json")},
        {"candidates": optimization_input(budget=0)},
        {"time_limit": 5},
    )["allocation"]
    assert result["status"] == "INFEASIBLE"
    assert result["selected"] == [] and result["totals"] is None
    assert result["constraints_satisfied"] is False
    assert all(row["selected"] is None for row in result["allocations"])
    assert all(
        check["actual"] is None and check["satisfied"] is None
        for check in result["checks"].values()
    )


def test_scene_protection_cannot_be_overridden_by_uploaded_candidates():
    selected = scene(scenario_conditions={"optimization_protected_units": ["b"]})
    result = optimize_component(
        {"scene": selected.model_dump(mode="json")},
        {"candidates": optimization_input()},
        {"time_limit": 5},
    )["allocation"]
    assert result["selected"] == ["a"]


@pytest.mark.parametrize(
    "changes",
    [
        {"area_unit": "m"},
        {"area_unit": "unknown_area_unit"},
        {"minimum_area": True},
        {"risk_aggregation": "sum_of_probabilities"},
        {"protected_unit_ids": ["missing"]},
        {"cost_unit": "unknown_cost_unit"},
        {"additivity_basis": "   "},
    ],
)
def test_ambiguous_or_invalid_scientific_inputs_are_rejected(changes):
    with pytest.raises(ValidationError):
        OptimizationFrame.model_validate(optimization_input(**changes))


def test_boolean_candidate_numeric_values_are_rejected():
    value = optimization_input()
    value["units"][0]["benefit"] = True
    with pytest.raises(ValidationError):
        OptimizationFrame.model_validate(value)
