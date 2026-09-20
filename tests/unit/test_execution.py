import threading
from datetime import UTC, datetime

import pytest

from coastmas.adapters.runtime import PythonFunctionAdapter
from coastmas.core.contracts import RunManifest
from coastmas.core.errors import CoastMASError
from coastmas.core.execution import ExecutionRegistry, execute_workflow
from tests.factories import asset, model, scene, variable, workflow


def manifest(work=None, models=None):
    return RunManifest(
        scene=scene(),
        workflow=work or workflow(),
        models=models or (model(),),
        data_assets=(asset(),),
        parameters=(),
        software_version="test",
        container_image="local-test",
        timestamp=datetime.now(UTC),
        random_seed=42,
        bindings=(work or workflow()).input_bindings,
        environment={},
    )


class Resolver:
    def __init__(self):
        self.calls = 0

    def resolve(self, asset_spec, variable_spec, binding, scene_spec):
        self.calls += 1
        return [[1.0, 2.0]]


def test_dag_executes_registered_models_and_real_subprocess_with_parameter_default(tmp_path):
    def add(inputs, parameters):
        return {"result": [[value + parameters["increment"] for value in inputs["height"][0]]]}

    spec = model()
    registry = ExecutionRegistry()
    registry.register(spec, PythonFunctionAdapter({"screen": add}), "screen")
    resolver = Resolver()
    output = execute_workflow(manifest(), registry=registry, resolver=resolver, work_root=tmp_path)
    assert output.outputs == {"screen-node.result": [[1.5, 2.5]]}
    assert output.executed_nodes == ("screen-node",)
    assert resolver.calls == 1
    assert not list(tmp_path.iterdir())


def test_dag_follows_dependencies_instead_of_user_node_order(tmp_path):
    first = model()
    second = model(
        id="second",
        name="second",
        inputs=(variable("result"),),
        outputs=(variable("final"),),
        parameters=(),
    )
    work = workflow(
        nodes=[
            {"id": "last", "model_id": "second", "model_version": 1},
            {
                "id": "screen-node",
                "model_id": "screen",
                "model_version": 1,
                "parameters": {"increment": 0.5},
            },
        ],
        edges=[
            {
                "source_node": "screen-node",
                "source_variable": "result",
                "target_node": "last",
                "target_variable": "result",
            }
        ],
        output_definition=[{"node_id": "last", "variable": "final"}],
    )
    registry = ExecutionRegistry()
    registry.register(
        first,
        PythonFunctionAdapter({"a": lambda inputs, parameters: {"result": inputs["height"]}}),
        "a",
    )
    registry.register(
        second,
        PythonFunctionAdapter({"b": lambda inputs, parameters: {"final": inputs["result"]}}),
        "b",
    )
    output = execute_workflow(
        manifest(work, (first, second)), registry=registry, resolver=Resolver(), work_root=tmp_path
    )
    assert output.executed_nodes == ("screen-node", "last")
    assert output.outputs == {"last.final": [[1.0, 2.0]]}


def test_no_model_or_data_execution_before_all_preflight_checks_pass(tmp_path):
    registry = ExecutionRegistry()
    resolver = Resolver()
    invalid = workflow(
        nodes=[
            {
                "id": "screen-node",
                "model_id": "screen",
                "model_version": 1,
                "parameters": {"increment": 100},
            }
        ]
    )
    with pytest.raises(CoastMASError, match="preflight"):
        execute_workflow(
            manifest(invalid), registry=registry, resolver=resolver, work_root=tmp_path
        )
    assert resolver.calls == 0
    assert not list(tmp_path.iterdir())


def test_registry_does_not_execute_edited_model_metadata_or_missing_outputs(tmp_path):
    registry = ExecutionRegistry()
    registry.register(
        model(description="different"), PythonFunctionAdapter({"a": lambda i, p: {}}), "a"
    )
    with pytest.raises(CoastMASError, match="registered"):
        execute_workflow(manifest(), registry=registry, resolver=Resolver(), work_root=tmp_path)
    registry = ExecutionRegistry()
    registry.register(model(), PythonFunctionAdapter({"a": lambda i, p: {"unexpected": 42}}), "a")
    with pytest.raises(CoastMASError, match="output"):
        execute_workflow(manifest(), registry=registry, resolver=Resolver(), work_root=tmp_path)


def test_precancelled_workflow_never_starts_model(tmp_path):
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(CoastMASError, match="cancel"):
        execute_workflow(
            manifest(),
            registry=ExecutionRegistry(),
            resolver=Resolver(),
            work_root=tmp_path,
            cancel=cancelled,
        )


def test_contextual_model_uses_immutable_manifest_scene_and_seed(tmp_path):
    def contextual(context, inputs, parameters):
        assert context["scene"]["id"] == "scene"
        assert context["node_id"] == "screen-node"
        assert context["random_seed"] == 42
        assert "environment" not in context
        return {"result": inputs["height"]}

    registry = ExecutionRegistry()
    registry.register(
        model(), PythonFunctionAdapter({}, contextual_handlers={"run": contextual}), "run"
    )
    result = execute_workflow(
        manifest(), registry=registry, resolver=Resolver(), work_root=tmp_path
    )
    assert result.outputs == {"screen-node.result": [[1.0, 2.0]]}
