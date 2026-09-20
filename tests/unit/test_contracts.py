"""Contract boundary tests: malformed scientific metadata cannot become valid objects."""

import pytest
from pydantic import ValidationError

from coastmas.core.contracts import (
    ParameterSpec,
    TimeRange,
    VariableSpec,
    WorkflowEdge,
    WorkflowNode,
    WorkflowSpec,
)


def variable(**changes):
    payload = dict(
        name="height",
        standard_name="elevation",
        description="Elevation",
        data_type="raster",
        unit="m",
        dimension="[length]",
        semantic_type="continuous",
        spatial_support="grid",
        temporal_support="instant",
        aggregation_type="intensive",
        nodata_policy="mask",
        required=True,
    )
    payload.update(changes)
    return VariableSpec(**payload)


def test_variable_is_frozen_and_rejects_unknown_fields():
    item = variable()
    with pytest.raises(ValidationError):
        item.unit = "s"
    with pytest.raises(ValidationError):
        variable(guessed_datum="sea")


@pytest.mark.parametrize(
    "changes",
    [{"unit": "madeupunit"}, {"dimension": "[time]"}, {"name": ""}, {"aggregation_type": "guess"}],
)
def test_variable_rejects_invalid_scientific_metadata(changes):
    with pytest.raises(ValidationError):
        variable(**changes)


@pytest.mark.parametrize("minimum,maximum,default", [(2, 1, 1), (0, 1, 2), (0, 1, float("nan"))])
def test_parameter_rejects_invalid_ranges(minimum, maximum, default):
    with pytest.raises(ValidationError):
        ParameterSpec(
            name="increment",
            unit="m",
            minimum=minimum,
            maximum=maximum,
            default=default,
            required=True,
        )


def test_time_range_rejects_reversed_and_naive_times():
    with pytest.raises(ValidationError):
        TimeRange(start="2026-02-01T00:00:00Z", end="2026-01-01T00:00:00Z")
    with pytest.raises(ValidationError):
        TimeRange(start="2026-01-01T00:00:00", end="2026-02-01T00:00:00")


def node(identifier):
    return WorkflowNode(id=identifier, model_id="registered", model_version=1)


def edge(source, target):
    return WorkflowEdge(
        source_node=source, source_variable="out", target_node=target, target_variable="in"
    )


def workflow(nodes, edges):
    return WorkflowSpec(
        id="wf",
        name="test",
        version=1,
        scene_type="custom",
        nodes=nodes,
        edges=edges,
        input_bindings=(),
        parameter_bindings=(),
        constraints=(),
        validation_rules=(),
        execution_policy={"timeout_seconds": 60, "max_retries": 0},
        output_definition=(),
    )


def test_workflow_rejects_cycles_and_dangling_nodes():
    with pytest.raises(ValidationError, match="cycle"):
        workflow((node("a"), node("b")), (edge("a", "b"), edge("b", "a")))
    with pytest.raises(ValidationError, match="unknown"):
        workflow((node("a"),), (edge("a", "missing"),))


def test_workflow_rejects_duplicate_ids_and_multiple_producers():
    with pytest.raises(ValidationError, match="duplicate"):
        workflow((node("a"), node("a")), ())
    with pytest.raises(ValidationError, match="producer"):
        workflow((node("a"), node("b"), node("c")), (edge("a", "c"), edge("b", "c")))


def test_workflow_preserves_valid_dag():
    item = workflow((node("a"), node("b")), (edge("a", "b"),))
    assert item.nodes[0].model_version == 1
    assert WorkflowSpec.model_validate_json(item.model_dump_json()) == item


def test_target_grid_rejects_excessive_allocation_and_singular_transform():
    from coastmas.core.contracts import TargetGridSpec

    with pytest.raises(ValueError):
        TargetGridSpec(crs="EPSG:32650", transform=(1, 0, 0, 0, -1, 0), width=10000, height=10000)
    with pytest.raises(ValueError):
        TargetGridSpec(crs="EPSG:32650", transform=(0, 0, 0, 0, 0, 0), width=2, height=2)
