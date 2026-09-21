import pytest

from coastmas.core.llm import ProviderProposal
from coastmas.core.research import summarize_trials
from coastmas.core.research_planning import ResearchCase, evaluate_rule_case
from coastmas.core.research_provider import evaluate_proposal_trial, research_prompt
from tests.unit.test_planning import inputs


def case_and_proposal():
    catalog, data, scene = inputs()
    case = ResearchCase(
        id="fixed",
        goal="可持续性评价：等权综合评价",
        scene=scene,
        models=catalog.models,
        assets=(data,),
    )
    workflow = evaluate_rule_case(case, catalog.registry, repetition=1).workflow
    proposal = ProviderProposal(
        management_goal=case.goal,
        task_graph=(),
        required_data=(),
        required_capabilities=(),
        missing_conditions=(),
        rationale=(),
        candidate_workflow={
            "nodes": [
                {
                    "id": n.id,
                    "model": {"id": n.model_id, "version": n.model_version},
                    "parameters": [{"name": k, "value": v} for k, v in n.parameters.items()],
                }
                for n in workflow.nodes
            ],
            "edges": workflow.edges,
            "input_bindings": [
                {"source": b.source, "target": b.target} for b in workflow.input_bindings
            ],
            "output_definition": workflow.output_definition,
        },
    )
    return catalog, case, proposal


def test_arms_share_frozen_catalog_but_only_c_receives_actual_graph_evidence():
    _, case, _ = case_and_proposal()
    direct = research_prompt(case, "B")
    graph = research_prompt(case, "C")
    assert direct.models == graph.models
    assert direct.data == graph.data
    assert "knowledge_graph" not in direct.scene_summary
    assert graph.scene_summary["knowledge_graph"]["connections"]
    serialized = graph.model_dump_json()
    assert case.assets[0].uri not in serialized
    assert "requires_preflight" in serialized
    with pytest.raises(ValueError):
        research_prompt(case, "A")


def test_local_provider_result_is_scientifically_audited_and_never_counted_as_external():
    catalog, case, proposal = case_and_proposal()
    trial = evaluate_proposal_trial(
        case,
        catalog.registry,
        proposal,
        experiment="B",
        repetition=1,
        origin="LOCAL",
        latency=0.2,
        requests=1,
        usage={"total_tokens": 10},
        trace_id="trace-local",
    )
    assert trial.observation.workflow_valid is True
    assert trial.observation.provider_requests == 1
    assert trial.observation.manual_corrections is None
    assert trial.proposal == proposal
    assert summarize_trials((trial.observation,))[0].origin == "LOCAL"


def test_unknown_model_is_retained_as_invalid_candidate_not_fake_no_candidate():
    catalog, case, proposal = case_and_proposal()
    payload = proposal.model_dump(mode="json")
    payload["candidate_workflow"]["nodes"][0]["model"]["id"] = "unknown-model"
    trial = evaluate_proposal_trial(
        case,
        catalog.registry,
        ProviderProposal.model_validate(payload),
        experiment="C",
        repetition=1,
        origin="MOCK",
        latency=0.1,
        requests=0,
        usage=None,
        trace_id="trace-mock",
    )
    assert trial.workflow is None
    assert trial.proposal.candidate_workflow is not None
    assert trial.observation.candidate_present is True
    assert trial.observation.workflow_valid is False
    assert trial.observation.constraint_violated is True
    assert trial.observation.diagnostics == ("MODEL_UNKNOWN",)


def test_structurally_invalid_candidate_is_a_failed_observation_not_a_crashed_suite():
    catalog, case, proposal = case_and_proposal()
    payload = proposal.model_dump(mode="json")
    payload["candidate_workflow"]["nodes"].append(payload["candidate_workflow"]["nodes"][0])
    trial = evaluate_proposal_trial(
        case,
        catalog.registry,
        ProviderProposal.model_validate(payload),
        experiment="B",
        repetition=1,
        origin="MOCK",
        latency=0.1,
        requests=0,
        usage=None,
        trace_id="trace-mock",
    )
    assert trial.observation.workflow_valid is False
    assert trial.observation.constraint_violated is True
    assert trial.observation.diagnostics == ("WORKFLOW_SCHEMA_INVALID",)
