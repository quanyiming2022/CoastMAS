import pytest
from pydantic import ValidationError

from coastmas.core.collaboration import ProposalDraft
from coastmas.domain.collaboration import compare_constraints


def proposal(identifier, constraints, **changes):
    value = {
        "id": identifier,
        "name": identifier,
        "version": 1,
        "scene": {"id": "scene", "version": 1},
        "rationale": "Synthetic proposal for constraint comparison",
        "objectives": [{"objective_id": "benefit", "name": "Benefit", "weight": 1}],
        "constraints": constraints,
        "evidence_results": [],
    }
    value.update(changes)
    return ProposalDraft.model_validate(value)


def bound(identifier, metric, unit, lower=None, upper=None):
    return {
        "constraint_id": identifier,
        "metric": metric,
        "unit": unit,
        "minimum": lower,
        "maximum": upper,
    }


def test_hard_conflict_uses_compatible_units_and_cannot_be_offset_by_weights():
    first = proposal("researcher", [bound("lower", "height", "cm", lower=200)])
    second = proposal(
        "manager",
        [bound("upper", "height", "m", upper=1)],
        objectives=[{"objective_id": "benefit", "name": "Benefit", "weight": 1e12}],
    )
    comparison = compare_constraints((first, second))
    assert comparison.policy_decision is False
    assert len(comparison.conflicts) == 1
    conflict = comparison.conflicts[0]
    assert conflict.code == "EMPTY_INTERVAL"
    assert conflict.metric == "height"
    assert conflict.minimum == 200
    assert conflict.maximum == 100
    assert conflict.unit == "cm"
    assert {(ref.proposal_id, ref.version, ref.constraint_id) for ref in conflict.sources} == {
        ("researcher", 1, "lower"),
        ("manager", 1, "upper"),
    }


def test_overlapping_and_zero_boundaries_are_not_conflicts():
    first = proposal(
        "a", [bound("lower", "area", "m^2", lower=0), bound("budget", "budget", "1", upper=0)]
    )
    second = proposal("b", [bound("upper", "area", "ha", upper=1)])
    result = compare_constraints((first, second))
    assert result.conflicts == ()
    area = next(item for item in result.intersections if item.metric == "area")
    assert area.minimum == 0 and area.maximum == 10000
    budget = next(item for item in result.intersections if item.metric == "budget")
    assert budget.minimum is None and budget.maximum == 0


def test_incompatible_units_and_internal_conflicts_are_explicit():
    first = proposal(
        "a",
        [
            bound("length", "extent", "m", lower=1),
            bound("low", "cost", "1", lower=10),
            bound("high", "cost", "1", upper=2),
        ],
    )
    second = proposal("b", [bound("time", "extent", "s", upper=5)])
    assert {item.code for item in compare_constraints((first, second)).conflicts} == {
        "UNIT_MISMATCH",
        "EMPTY_INTERVAL",
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"objectives": [{"objective_id": "benefit", "name": "Benefit", "weight": 0}]},
        {"constraints": [bound("x", "area", "ha", lower=2, upper=1)]},
        {"constraints": [bound("x", "area", "unknown_coastmas_unit", upper=1)]},
        {"constraints": [bound("x", "area", "m")]},
        {"constraints": [bound("x", "area", "m", lower=0), bound("x", "area", "m", upper=1)]},
    ],
)
def test_undefined_or_ambiguous_proposal_metadata_is_rejected(changes):
    payload = dict(changes)
    constraints = payload.pop("constraints", [])
    with pytest.raises(ValidationError):
        proposal("invalid", constraints, **payload)
