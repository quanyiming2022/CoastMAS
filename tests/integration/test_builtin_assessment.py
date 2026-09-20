import json
from datetime import UTC, datetime

import numpy as np
import pytest

from coastmas.adapters.datasource import StoredDataResolver
from coastmas.core.contracts import RunManifest, WorkflowSpec
from coastmas.core.execution import execute_workflow
from coastmas.core.validation import validate_workflow
from coastmas.domain.builtin_catalog import assessment_catalog
from tests.factories import asset, scene, variable
from tests.unit.test_indicator_frames import frame


@pytest.mark.parametrize("temporal", [False, True])
def test_registered_assessment_nodes_execute_real_stored_frames_as_dag(storage, tmp_path, temporal):
    catalog = assessment_catalog("project-demo")
    components = {item.runtime_config["component"]: item for item in catalog.models}
    source = frame(periods=temporal)
    payload = json.dumps({"frame": source.model_dump(mode="json")}).encode()
    stored = storage.put("indicator/frame.json", payload)
    data = asset(
        type="json",
        format="JSON",
        uri=stored.uri,
        checksum=stored.sha256,
        variables=[
            variable(
                name="frame",
                standard_name="indicator_frame",
                data_type="json",
                unit="1",
                dimension="dimensionless",
                spatial_support="management_unit",
                temporal_support="declared_period",
                nodata_policy="reject",
            )
        ],
        time_start="2020-01-01T00:00:00Z",
        time_end="2023-01-01T00:00:00Z",
        quality={"validated": True, "size_bytes": stored.size},
    )
    nodes = [
        {"id": name, "model_id": components[name].id, "model_version": 1}
        for name in ("normalize", "weight", "composite")
    ]
    edges = [
        {
            "source_node": "normalize",
            "source_variable": "frame",
            "target_node": target,
            "target_variable": "frame",
        }
        for target in ("weight", "composite")
    ]
    edges.append(
        {
            "source_node": "weight",
            "source_variable": "weights",
            "target_node": "composite",
            "target_variable": "weights",
        }
    )
    outputs = [{"node_id": "composite", "variable": "scores"}]
    if temporal:
        nodes.append({"id": "change", "model_id": components["change"].id, "model_version": 1})
        edges.append(
            {
                "source_node": "composite",
                "source_variable": "scores",
                "target_node": "change",
                "target_variable": "scores",
            }
        )
        outputs.append({"node_id": "change", "variable": "change"})
    graph = WorkflowSpec.model_validate(
        {
            "id": "assessment",
            "name": "assessment",
            "version": 1,
            "scene_type": "C" if temporal else "B",
            "nodes": nodes,
            "edges": edges,
            "input_bindings": [
                {
                    "source": {"id": data.id, "version": 1},
                    "target": {"node_id": "normalize", "variable": "frame"},
                    "semantic_mapping": "exact_standard_name",
                    "unit_conversion": None,
                    "crs_transform": None,
                    "resampling": None,
                    "temporal_transform": None,
                    "quality_check": [],
                    "status": "MANUAL_REVIEW",
                }
            ],
            "parameter_bindings": [],
            "constraints": [],
            "validation_rules": [],
            "execution_policy": {"timeout_seconds": 30, "max_retries": 0},
            "output_definition": outputs,
        }
    )
    context = scene(time_range={"start": "2020-01-01T00:00:00Z", "end": "2023-01-01T00:00:00Z"})
    used = {node.model_id for node in graph.nodes}
    manifest = RunManifest(
        scene=context,
        workflow=graph,
        models=tuple(item for item in catalog.models if item.id in used),
        data_assets=(data,),
        parameters=(),
        bindings=graph.input_bindings,
        random_seed=42,
        software_version="test",
        container_image="local-test",
        timestamp=datetime.now(UTC),
        environment={},
    )
    report = validate_workflow(graph, list(manifest.models), [data], context)
    assert report.valid, report.issues
    result = execute_workflow(
        manifest,
        registry=catalog.registry,
        resolver=StoredDataResolver(storage),
        work_root=tmp_path,
    )
    scores = result.outputs["composite.scores"]
    assert scores["unit_ids"] == ["U1", "U2", "U3", "U4"]
    np.testing.assert_allclose(scores["values"][0], [0.2, 0.4, 0.6, 0.8])
    if temporal:
        np.testing.assert_allclose(result.outputs["change.change"]["trend"], [0.1] * 4)
    assert result.executed_nodes == tuple(node["id"] for node in nodes)
    assert all(item.validation_metrics["golden_max_abs_error"] <= 1e-12 for item in catalog.models)
