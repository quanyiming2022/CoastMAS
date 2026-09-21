from coastmas.core.research_planning import ResearchCase, evaluate_rule_case
from tests.unit.test_planning import inputs


def test_rule_trial_runs_actual_planner_and_shared_validation():
    catalog, data, context = inputs()
    case = ResearchCase(
        id="valid",
        goal="可持续性评价：等权综合评价",
        scene=context,
        models=catalog.models,
        assets=(data,),
    )
    trial = evaluate_rule_case(case, catalog.registry, repetition=1)
    assert trial.observation.status == "EVALUATED"
    assert trial.observation.workflow_valid is True
    assert trial.observation.constraint_violated is False
    assert trial.observation.provider_requests == 0
    assert trial.observation.manual_corrections is None
    assert trial.observation.latency_seconds >= 0
    assert trial.workflow is not None and len(trial.workflow.nodes) == 3
    assert trial.workflow.input_bindings[0].source.id == data.id


def test_missing_data_remains_invalid_with_real_planner_diagnostics():
    catalog, _, context = inputs()
    case = ResearchCase(
        id="missing",
        goal="可持续性评价：等权综合评价",
        scene=context,
        models=catalog.models,
        assets=(),
    )
    trial = evaluate_rule_case(case, catalog.registry, repetition=2)
    assert trial.workflow is None
    assert trial.observation.workflow_valid is False
    assert trial.observation.constraint_violated is None
    assert "DATA_MISSING" in trial.observation.diagnostics


def test_unrecognized_goal_is_not_silently_rewritten_or_marked_blocked():
    catalog, data, context = inputs()
    case = ResearchCase(
        id="unknown",
        goal="arbitrary extra requirement",
        scene=context,
        models=catalog.models,
        assets=(data,),
    )
    trial = evaluate_rule_case(case, catalog.registry, repetition=1)
    assert trial.observation.status == "EVALUATED"
    assert trial.observation.workflow_valid is False
    assert trial.observation.diagnostics == ("GOAL_UNRESOLVED",)


def test_suite_records_unavailable_external_arms_as_blocked_not_rule_fallback():
    from coastmas.core.research_planning import ResearchManifest, evaluate_research

    catalog, data, context = inputs()
    case = ResearchCase(
        id="valid",
        goal="可持续性评价：等权综合评价",
        scene=context,
        models=catalog.models,
        assets=(data,),
    )
    manifest = ResearchManifest(cases=(case,), experiments=("A", "B", "C"), repetitions=2)
    result = evaluate_research(manifest, catalog.registry)
    assert result.status == "PARTIAL"
    assert len(result.trials) == 6
    assert sum(row.observation.status == "BLOCKED" for row in result.trials) == 4
    assert result.metrics[0].evaluated == 2
    for metric in result.metrics[1:]:
        assert metric.evaluated == 0
        assert metric.workflow_validity_rate is None
        assert metric.provider_requests == 0


def test_suite_rejects_duplicates_and_obeys_cancellation():
    import threading

    import pytest

    from coastmas.core.errors import CoastMASError
    from coastmas.core.research_planning import ResearchManifest, evaluate_research

    catalog, data, context = inputs()
    case = ResearchCase(
        id="valid",
        goal="可持续性评价：等权综合评价",
        scene=context,
        models=catalog.models,
        assets=(data,),
    )
    with pytest.raises(ValueError, match="duplicate"):
        ResearchManifest(cases=(case, case), experiments=("A",), repetitions=1)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(CoastMASError, match="cancel"):
        evaluate_research(
            ResearchManifest(cases=(case,), experiments=("A",), repetitions=1),
            catalog.registry,
            cancel=cancel,
        )
