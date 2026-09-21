"""Real S3 bytes -> isolated registered MILP -> entity-addressed result objects."""

import json
from datetime import UTC, datetime

import pytest

from coastmas.adapters.datasource import StoredDataResolver
from coastmas.core.contracts import RunManifest, WorkflowSpec
from coastmas.core.execution import execute_workflow
from coastmas.core.validation import validate_workflow
from coastmas.domain.optimization_catalog import optimization_catalog
from coastmas.domain.result_views import management_objects
from tests.factories import asset, scene
from tests.unit.test_optimization_frame import optimization_input


@pytest.mark.parametrize(
    "budget,expected_status,expected_ids", [(3, "OPTIMAL", ["b"]), (0, "INFEASIBLE", [])]
)
def test_registered_optimization_executes_actual_stored_input(
    storage, tmp_path, budget, expected_status, expected_ids
):
    catalog = optimization_catalog("optimization-test")
    model = catalog.models[0]
    assert model.model_type.value == "OPTIMIZATION"
    assert model.validation_metrics["golden_max_abs_error"] == 0
    payload = json.dumps({"candidates": optimization_input(budget=budget)}).encode()
    stored = storage.put("optimization/candidates.json", payload)
    data = asset(
        id="candidate-data",
        type="json",
        format="JSON",
        uri=stored.uri,
        checksum=stored.sha256,
        variables=model.inputs,
        crs=None,
        vertical_datum=None,
        spatial_extent=None,
        quality={"validated": True, "size_bytes": stored.size},
    )
    selected = scene(entity_types=["management_unit"], required_outputs=["allocation"])
    workflow = WorkflowSpec.model_validate(
        {
            "id": "allocation-workflow",
            "name": "SYNTHETIC MILP",
            "version": 1,
            "scene_type": "spatial_optimization",
            "nodes": [
                {
                    "id": "optimize",
                    "model_id": model.id,
                    "model_version": 1,
                    "parameters": {"time_limit": 5},
                }
            ],
            "edges": [],
            "input_bindings": [
                {
                    "source": {"id": data.id, "version": 1},
                    "target": {"node_id": "optimize", "variable": "candidates"},
                    "semantic_mapping": "exact_standard_name",
                    "unit_conversion": None,
                    "crs_transform": None,
                    "resampling": None,
                    "temporal_transform": None,
                    "quality_check": [],
                    "status": "VALIDATED",
                }
            ],
            "parameter_bindings": [],
            "constraints": [],
            "validation_rules": [],
            "execution_policy": {"timeout_seconds": 30, "max_retries": 0},
            "output_definition": [{"node_id": "optimize", "variable": "allocation"}],
        }
    )
    report = validate_workflow(workflow, list(catalog.models), [data], selected)
    assert report.valid, report.issues
    manifest = RunManifest(
        scene=selected,
        workflow=workflow,
        models=catalog.models,
        data_assets=(data,),
        parameters=(),
        bindings=workflow.input_bindings,
        random_seed=42,
        software_version="test",
        container_image="local-test",
        timestamp=datetime.now(UTC),
        environment={},
    )
    result = execute_workflow(
        manifest,
        registry=catalog.registry,
        resolver=StoredDataResolver(storage),
        work_root=tmp_path,
    )
    allocation = result.outputs["optimize.allocation"]
    assert allocation["status"] == expected_status
    assert allocation["selected"] == expected_ids
    objects = management_objects(
        "actual-optimization-job", workflow, catalog.models, result.outputs
    )
    assert {item.management_unit_id for item in objects} == {"a", "b", "protected"}
    indexed = {item.management_unit_id: item for item in objects}
    assert indexed["b"].values["selected"] == (1 if expected_status == "OPTIMAL" else None)
    assert indexed["b"].values["area"] == 20000
    assert indexed["b"].units["area"] == "m^2"
    assert indexed["protected"].values["allowed"] == 0
    assert indexed["a"].values["solution_status"] == expected_status
