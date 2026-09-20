import pytest

from coastmas.core.errors import CoastMASError
from coastmas.core.planning import ManagementGoal, build_template_plan, parse_template_goal
from coastmas.domain.builtin_catalog import assessment_catalog
from tests.factories import asset, scene


def inputs():
    catalog = assessment_catalog("plan-test")
    source = next(
        model for model in catalog.models if model.runtime_config["component"] == "normalize"
    )
    data = asset(type="json", format="JSON", variables=source.inputs, quality={"validated": True})
    context = scene(required_outputs=["scores"])
    return catalog, data, context


def test_exact_template_keeps_parameters_and_rejects_unconsumed_conditions():
    text = "分析某海岸段在0.5米海平面上升情景下，土地利用和人口受到的影响，并按照管理单元统计风险。"
    goal = parse_template_goal(text)
    assert goal.template == "coastal_impact"
    assert goal.sea_level_increment_m == 0.5
    assert goal.original_text == text
    for extra in ("但不分析人口", "且使用2050年预测", "同时计算潮汐", "忽略缺失数据"):
        with pytest.raises(CoastMASError, match="template"):
            parse_template_goal(text + extra)
    with pytest.raises(ValueError):
        ManagementGoal(original_text="x", template="coastal_impact", sea_level_increment_m=-1)


@pytest.mark.parametrize(
    "template,outputs,count",
    [
        ("sustainability", ["scores"], 3),
        ("temporal_change", ["scores", "change"], 4),
    ],
)
def test_planner_builds_registered_multinode_dag(template, outputs, count):
    catalog, data, context = inputs()
    context = context.model_copy(update={"required_outputs": tuple(outputs)})
    goal = ManagementGoal(
        original_text="structured request", template=template, weight_method="equal"
    )
    plan = build_template_plan(goal, context, catalog.models, (data,), catalog.registry)
    assert not plan.missing_conditions
    assert plan.candidate_workflow is not None
    assert len(plan.task_graph.nodes) == count
    assert plan.provider_requests == 0
    assert plan.candidate_workflow.input_bindings[0].status == "VALIDATED"
    weight = next(node for node in plan.task_graph.nodes if node.id == "weight")
    assert weight.parameters == {"method": 0}
    assert plan.required_data[0].selected.id == data.id


def test_missing_ambiguous_or_invalid_data_never_yields_executable_candidate():
    catalog, data, context = inputs()
    goal = parse_template_goal("可持续性评价：等权综合评价")
    missing = build_template_plan(goal, context, catalog.models, (), catalog.registry)
    assert missing.candidate_workflow is None
    assert any(item.code == "DATA_MISSING" for item in missing.missing_conditions)
    duplicate = data.model_copy(update={"id": "other"})
    ambiguous = build_template_plan(
        goal, context, catalog.models, (data, duplicate), catalog.registry
    )
    assert any(item.code == "DATA_AMBIGUOUS" for item in ambiguous.missing_conditions)
    explicit = build_template_plan(
        goal,
        context,
        catalog.models,
        (data, duplicate),
        catalog.registry,
        selected_data={"normalize.frame": {"id": "other", "version": 1}},
    )
    assert explicit.candidate_workflow.input_bindings[0].source.id == "other"
    bad = data.model_copy(update={"quality": {"validated": False}})
    invalid = build_template_plan(goal, context, catalog.models, (bad,), catalog.registry)
    assert invalid.candidate_workflow is None
    assert invalid.missing_conditions


def test_disabled_or_forged_model_unknown_outputs_and_selectors_are_blocked():
    catalog, data, context = inputs()
    goal = parse_template_goal("可持续性评价：熵权综合评价")
    altered = tuple(
        model.model_copy(update={"enabled": False})
        if model.runtime_config["component"] == "weight"
        else model
        for model in catalog.models
    )
    result = build_template_plan(goal, context, altered, (data,), catalog.registry)
    assert result.candidate_workflow is None
    result = build_template_plan(
        goal,
        context.model_copy(update={"required_outputs": ("tidal_velocity",)}),
        catalog.models,
        (data,),
        catalog.registry,
    )
    assert any(item.code == "OUTPUT_UNSUPPORTED" for item in result.missing_conditions)
    result = build_template_plan(
        goal,
        context,
        catalog.models,
        (data,),
        catalog.registry,
        selected_data={"made_up.input": {"id": data.id, "version": 1}},
    )
    assert any(item.code == "SELECTION_UNKNOWN" for item in result.missing_conditions)


def test_provider_candidate_cannot_invent_models_or_bypass_hard_preflight():
    from coastmas.core.llm import ProviderProposal
    from coastmas.core.planning import validate_provider_proposal

    catalog, data, context = inputs()
    deterministic = build_template_plan(
        parse_template_goal("可持续性评价：等权综合评价"),
        context,
        catalog.models,
        (data,),
        catalog.registry,
    )
    graph = deterministic.candidate_workflow
    proposal = ProviderProposal.model_validate(
        {
            "management_goal": "sustainability",
            "task_graph": ["normalize", "weight", "aggregate"],
            "required_data": ["indicator_frame"],
            "required_capabilities": ["normalize", "weight", "composite"],
            "missing_conditions": [],
            "rationale": ["test proposal"],
            "candidate_workflow": {
                "nodes": [
                    {
                        "id": node.id,
                        "model": {"id": node.model_id, "version": node.model_version},
                        "parameters": [
                            {"name": name, "value": value}
                            for name, value in node.parameters.items()
                        ],
                    }
                    for node in graph.nodes
                ],
                "edges": [item.model_dump(mode="json") for item in graph.edges],
                "input_bindings": [
                    {"source": item.source.model_dump(), "target": item.target.model_dump()}
                    for item in graph.input_bindings
                ],
                "output_definition": [item.model_dump() for item in graph.output_definition],
            },
        }
    )
    checked = validate_provider_proposal(
        proposal, context, catalog.models, (data,), catalog.registry
    )
    assert checked.input_bindings[0].status == "VALIDATED"
    payload = proposal.model_dump(mode="json")
    payload["candidate_workflow"]["nodes"][0]["model"]["id"] = "hallucinated-model"
    with pytest.raises(CoastMASError):
        validate_provider_proposal(
            ProviderProposal.model_validate(payload),
            context,
            catalog.models,
            (data,),
            catalog.registry,
        )
    payload = proposal.model_dump(mode="json")
    payload["candidate_workflow"]["nodes"][1]["parameters"][0]["value"] = 100
    with pytest.raises(CoastMASError):
        validate_provider_proposal(
            ProviderProposal.model_validate(payload),
            context,
            catalog.models,
            (data,),
            catalog.registry,
        )
    payload = proposal.model_dump(mode="json")
    payload["candidate_workflow"]["nodes"][1]["parameters"].append({"name": "method", "value": 0})
    with pytest.raises(CoastMASError):
        validate_provider_proposal(
            ProviderProposal.model_validate(payload),
            context,
            catalog.models,
            (data,),
            catalog.registry,
        )
    with pytest.raises(CoastMASError):
        validate_provider_proposal(
            proposal.model_copy(update={"missing_conditions": ("tidal model",)}),
            context,
            catalog.models,
            (data,),
            catalog.registry,
        )


def test_distinct_selected_data_produce_distinct_workflow_identity():
    catalog, data, context = inputs()
    other = data.model_copy(update={"id": "different-data"})
    goal = parse_template_goal("可持续性评价：等权综合评价")
    first = build_template_plan(goal, context, catalog.models, (data,), catalog.registry)
    second = build_template_plan(goal, context, catalog.models, (other,), catalog.registry)
    assert first.candidate_workflow.id != second.candidate_workflow.id


def test_equivalent_scene_dictionary_order_has_same_workflow_identity():
    from coastmas.core.contracts import SceneSpec

    catalog, data, context = inputs()
    goal = parse_template_goal("可持续性评价：等权综合评价")
    payload = context.model_dump(mode="json")
    payload["scenario_conditions"] = {"scenario_label": "test", "metadata": {"a": 1, "b": 2}}
    first = SceneSpec.model_validate(payload)
    payload["scenario_conditions"] = {"metadata": {"b": 2, "a": 1}, "scenario_label": "test"}
    second = SceneSpec.model_validate(payload)
    first_plan = build_template_plan(goal, first, catalog.models, (data,), catalog.registry)
    second_plan = build_template_plan(goal, second, catalog.models, (data,), catalog.registry)
    assert first_plan.candidate_workflow is not None
    assert second_plan.candidate_workflow is not None
    assert first_plan.candidate_workflow.id == second_plan.candidate_workflow.id
