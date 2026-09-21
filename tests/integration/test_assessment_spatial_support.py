import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from coastmas.adapters.datasource import StoredDataResolver
from coastmas.core.contracts import RunManifest, VersionReference
from coastmas.core.execution import execute_workflow
from coastmas.core.planning import ManagementGoal, build_template_plan
from coastmas.domain.builtin_catalog import assessment_catalog
from coastmas.domain.coastal_catalog import coastal_catalog
from tests.factories import asset, scene, variable
from tests.unit.test_indicator_frames import frame


@pytest.mark.parametrize(
    "support", ["management_unit", "administrative_unit", "custom_polygon", "grid"]
)
def test_assessment_executes_with_exact_spatial_support_and_preserves_legacy_models(
    storage, tmp_path, support
):
    catalog = coastal_catalog("spatial-project", Path("sample-data"))
    for legacy in assessment_catalog("spatial-project").models:
        assert next(item for item in catalog.models if item.id == legacy.id) == legacy
    content = json.dumps({"frame": frame(periods=True).model_dump(mode="json")}).encode()
    stored = storage.put("spatial/frame.json", content)
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
                spatial_support=support,
                temporal_support="declared_period",
                nodata_policy="reject",
            )
        ],
        time_start="2020-01-01T00:00:00Z",
        time_end="2023-01-01T00:00:00Z",
        quality={"validated": True, "size_bytes": stored.size},
    )
    context = scene(
        entity_types=[support],
        required_outputs=["scores", "change"],
        time_range={"start": "2020-01-01T00:00:00Z", "end": "2023-01-01T00:00:00Z"},
    )
    plan = build_template_plan(
        ManagementGoal(original_text="Explicit spatial evaluation", template="temporal_change"),
        context,
        catalog.models,
        (data,),
        catalog.registry,
        selected_data={"normalize.frame": VersionReference(id=data.id, version=1)},
    )
    assert not plan.missing_conditions, plan.missing_conditions
    workflow = plan.candidate_workflow
    assert workflow is not None
    models = tuple(
        item for item in catalog.models if item.id in {node.model_id for node in workflow.nodes}
    )
    assert {
        item.spatial_support for model in models for item in (*model.inputs, *model.outputs)
    } == {support}
    if support == "management_unit":
        assert {model.id for model in models} == {
            f"builtin:spatial-project:{component}"
            for component in ("normalize", "weight", "composite", "change")
        }
    manifest = RunManifest(
        scene=context,
        workflow=workflow,
        models=models,
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
    assert result.outputs["composite.scores"]["unit_ids"] == ["U1", "U2", "U3", "U4"]
    np.testing.assert_allclose(
        result.outputs["composite.scores"]["values"][0], [0.2, 0.4, 0.6, 0.8]
    )
    np.testing.assert_allclose(result.outputs["change.change"]["trend"], [0.1] * 4)
