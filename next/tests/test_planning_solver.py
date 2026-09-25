"""Numerical solver contracts are independent of catalogue labels and UI state."""

import threading

import pytest


def problem(mode="pareto_multiobjective"):
    return {
        "unit_ids": ["a", "b", "c"],
        "mode": mode,
        "objectives": [
            {"code": "cost", "direction": "min", "coefficients": [2.0, 5.0, 3.0], "unit": "CNY"},
            {"code": "gain", "direction": "max", "coefficients": [4.0, 8.0, 5.0], "unit": "ha"},
        ],
        "constraints": [
            {"id": "budget", "coefficients": [2.0, 5.0, 3.0], "upper": 5.0, "unit": "CNY"}
        ],
        "upper_bounds": [1, 1, 1],
    }


def test_exact_pareto_preserves_tradeoffs_without_choosing_a_best():
    from coastmas_next.planning_solver_v1 import solve

    value = problem()
    result = solve(value, threading.Event())
    assert result["status"] == "complete"
    assert result["solver"] == "exact_binary_pareto/1.0.0"
    assert {tuple(c["selected"]) for c in result["candidates"]} == {(), ("a",), ("c",), ("a", "c")}
    assert "best_candidate" not in result
    assert result["searched_states"] == result["total_states"] == 8
    assert all(c["feasibility"]["feasible"] for c in result["candidates"])
    assert value == problem()  # baseline and coefficients remain unchanged


def test_milp_and_independent_constraint_check():
    from coastmas_next.planning_solver_v1 import check_candidate, solve

    value = problem("single_objective")
    value["objectives"] = [value["objectives"][1]]
    result = solve(value, threading.Event())
    candidate = result["candidates"][0]
    assert set(candidate["selected"]) == {"a", "c"}
    assert candidate["objective_vector"] == {"gain": 9.0}
    assert candidate["feasibility"]["constraints"][0]["upper_residual"] == 0.0
    assert check_candidate(value, [1, 1, 1])["feasible"] is False
    value["upper_bounds"][2] = 0
    result = solve(value, threading.Event())
    assert result["candidates"][0]["selected"] == ["b"]
    assert check_candidate(value, [1, 0, 1])["feasible"] is False


@pytest.mark.parametrize("mode", ["single_objective", "pareto_multiobjective"])
def test_infeasible_is_not_an_empty_success_or_a_repaired_constraint(mode):
    from coastmas_next.planning_solver_v1 import solve

    value = problem(mode)
    if mode == "single_objective":
        value["objectives"] = [value["objectives"][1]]
    value["constraints"].append(
        {"id": "minimum_gain", "coefficients": [4.0, 8.0, 5.0], "lower": 99.0, "unit": "ha"}
    )
    result = solve(value, threading.Event())
    assert result["status"] == "infeasible" and result["candidates"] == []
    assert value["constraints"][-1]["lower"] == 99.0


def test_weighted_objectives_require_reviewed_scales_not_just_weights():
    from coastmas_next.planning_solver_v1 import solve
    from coastmas_next.store import Problem

    value = problem("weighted_multiobjective")
    for objective in value["objectives"]:
        objective["weight"] = 0.5
    with pytest.raises(Problem, match=".*") as caught:
        solve(value, threading.Event())
    assert caught.value.code == "OBJECTIVE_SCALE_REQUIRED"
    value["objectives"][0]["scale"] = {
        "lower": 0.0,
        "upper": 10.0,
        "basis": "engineering utility range",
    }
    value["objectives"][1]["scale"] = {
        "lower": 0.0,
        "upper": 20.0,
        "basis": "engineering utility range",
    }
    result = solve(value, threading.Event())
    assert result["candidates"] and result["solver"].startswith("scipy_milp")


def test_unknown_coefficients_and_unsupported_scale_are_not_silently_truncated():
    from coastmas_next.planning_solver_v1 import solve
    from coastmas_next.store import Problem

    value = problem()
    value["objectives"][0]["coefficients"][0] = None
    with pytest.raises(Problem):
        solve(value, threading.Event())
    value = problem()
    value["unit_ids"] = [str(i) for i in range(19)]
    value["upper_bounds"] = [1] * 19
    value["constraints"] = []
    for objective in value["objectives"]:
        objective["coefficients"] = [1.0] * 19
    with pytest.raises(Problem) as caught:
        solve(value, threading.Event())
    assert caught.value.code == "SOLVER_SCALE_RISK"


def test_cancel_and_identical_vectors_retain_distinct_spatial_alternatives():
    from coastmas_next.planning_solver_v1 import solve
    from coastmas_next.store import Problem

    canceled = threading.Event()
    canceled.set()
    with pytest.raises(Problem) as caught:
        solve(problem(), canceled)
    assert caught.value.code == "CANCELLED"
    value = problem()
    value["unit_ids"] = ["west", "east"]
    value["upper_bounds"] = [1, 1]
    value["constraints"] = [
        {"id": "only_one", "coefficients": [1.0, 1.0], "upper": 1.0, "unit": "1"}
    ]
    for objective in value["objectives"]:
        objective["coefficients"] = [1.0, 1.0]
    result = solve(value, threading.Event())
    assert {tuple(c["selected"]) for c in result["candidates"]} == {(), ("west",), ("east",)}
