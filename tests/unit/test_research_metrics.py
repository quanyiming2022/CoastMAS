import pytest
from pydantic import ValidationError

from coastmas.core.research import TrialObservation, summarize_trials


def observation(**changes):
    values = dict(
        case_id="case",
        repetition=1,
        experiment="A",
        origin="RULE",
        status="EVALUATED",
        latency_seconds=0.0,
        candidate_present=True,
        workflow_valid=True,
        constraint_violated=False,
        manual_corrections=None,
        provider_requests=0,
        usage=None,
        diagnostics=(),
    )
    values.update(changes)
    return TrialObservation(**values)


def test_blocked_trials_and_unknown_manual_work_are_not_success_or_zero():
    report = summarize_trials(
        (
            observation(),
            observation(
                case_id="blocked",
                status="BLOCKED",
                candidate_present=None,
                workflow_valid=None,
                constraint_violated=None,
                latency_seconds=None,
            ),
        )
    )
    assert len(report) == 1
    metrics = report[0]
    assert metrics.total == 2 and metrics.evaluated == 1 and metrics.blocked == 1
    assert metrics.workflow_validity_rate == 1
    assert metrics.constraint_violation_rate == 0
    assert metrics.manual_correction_count is None
    assert metrics.manual_observations == 0
    assert metrics.mean_latency_seconds == 0


def test_failed_attempts_are_visible_and_never_improve_completion_rate():
    report = summarize_trials(
        (
            observation(),
            observation(
                case_id="bad",
                status="FAILED",
                candidate_present=None,
                workflow_valid=None,
                constraint_violated=None,
                diagnostics=("PROVIDER_TIMEOUT",),
                latency_seconds=2.0,
            ),
        )
    )
    assert report[0].failed == 1
    assert report[0].evaluation_completion_rate == 0.5
    assert report[0].latency_observations == 2
    assert report[0].mean_latency_seconds == 1


def test_mock_replay_and_external_arms_are_never_pooled():
    report = summarize_trials(
        tuple(
            observation(
                case_id=origin,
                experiment="B",
                origin=origin,
                provider_requests=1 if origin == "EXTERNAL" else 0,
            )
            for origin in ("MOCK", "REPLAY", "EXTERNAL")
        )
    )
    assert {(row.experiment, row.origin, row.total) for row in report} == {
        ("B", "MOCK", 1),
        ("B", "REPLAY", 1),
        ("B", "EXTERNAL", 1),
    }
    assert all(row.total_tokens is None for row in report)


def test_duplicate_trials_and_inconsistent_observations_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        summarize_trials((observation(), observation()))
    for changes in (
        {"status": "BLOCKED"},
        {"latency_seconds": -1},
        {"workflow_valid": True, "constraint_violated": True},
        {"manual_corrections": -1},
        {"provider_requests": True},
        {"experiment": "A", "origin": "EXTERNAL"},
    ):
        with pytest.raises(ValidationError):
            observation(**changes)


def test_denominators_and_unknown_provider_usage_are_explicit():
    trials = (
        observation(
            experiment="C",
            origin="EXTERNAL",
            provider_requests=1,
            usage={"total_tokens": 0},
            manual_corrections=0,
        ),
        observation(
            case_id="invalid",
            experiment="C",
            origin="EXTERNAL",
            provider_requests=1,
            candidate_present=True,
            workflow_valid=False,
            constraint_violated=True,
            usage=None,
            manual_corrections=2,
        ),
    )
    metrics = summarize_trials(trials)[0]
    assert metrics.workflow_validity_rate == 0.5
    assert metrics.constraint_violation_rate == 0.5
    assert metrics.manual_correction_count == 2
    assert metrics.provider_requests == 2
    assert metrics.total_tokens is None
    assert metrics.usage_observations == 1
