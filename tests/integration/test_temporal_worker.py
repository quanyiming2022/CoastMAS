"""Explicit temporal support through real storage, database and immutable worker output."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from coastmas.adapters.storage import ArtifactRecord
from coastmas.core.contracts import RunManifest
from coastmas.core.data_inspection import inspect_data
from coastmas.core.errors import CoastMASError
from coastmas.core.validation import validate_workflow
from coastmas.domain.adaptation_catalog import adaptation_catalog
from coastmas.persistence.jobs import read_job, read_result, submit_job
from coastmas.persistence.resources import create_resource
from coastmas.runtime_bootstrap import BuiltinRuntimeRegistry
from coastmas.worker.runtime import WorkflowWorker
from tests.factories import asset, scene, workflow


def temporal_case(storage, project, method="mean"):
    model = adaptation_catalog(project).models[0]
    point = method in {"nearest", "interpolation"}
    source = {
        "variable": "precipitation" if method == "sum" else "temperature",
        "unit": "mm" if method == "sum" else "degC",
        "output_unit": "m" if method == "sum" else "kelvin",
        "aggregation_type": "extensive" if method == "sum" else "intensive",
        "support": "point" if point else "interval",
        "method": method,
        "observations": [
            {
                "start": "2025-01-01T00:00:00Z",
                "end": "2025-01-01T00:00:00Z" if point else "2025-01-01T01:00:00Z",
                "value": 10,
            },
            {
                "start": "2025-01-01T04:00:00Z" if point else "2025-01-01T01:00:00Z",
                "end": "2025-01-01T04:00:00Z",
                "value": 20,
            },
        ],
    }
    if point:
        source["target_time"] = "2025-01-01T02:00:00Z"
    else:
        source.update(window_start="2025-01-01T00:00:00Z", window_end="2025-01-01T04:00:00Z")
    content = json.dumps({"request": source}).encode()
    blob = storage.put(f"{project}/temporal/{uuid4()}.json", content)
    data = asset(
        id="temporal-" + uuid4().hex,
        type="table",
        format="JSON",
        crs=None,
        vertical_datum=None,
        spatial_extent=None,
        uri=blob.uri,
        checksum=blob.sha256,
        variables=model.inputs,
        time_resolution="explicit_support",
        time_start=source["observations"][0]["start"],
        time_end=source["observations"][-1]["end"],
        quality={"size_bytes": blob.size},
    )
    measured = inspect_data(content, data)
    data = data.model_copy(update={"quality": {**data.quality, **measured.metadata}})
    view = scene(
        id="temporal-scene-" + uuid4().hex,
        time_range={
            "start": source.get("target_time", source.get("window_start")),
            "end": source.get("target_time", source.get("window_end")),
        },
        required_outputs=["result"],
    )
    draft = workflow().model_dump(mode="json")
    draft.update(
        id="temporal-wf-" + uuid4().hex,
        nodes=[{"id": "adapt", "model_id": model.id, "model_version": 1, "parameters": {}}],
        output_definition=[{"node_id": "adapt", "variable": "result"}],
    )
    draft["input_bindings"][0].update(
        source={"id": data.id, "version": 1}, target={"node_id": "adapt", "variable": "request"}
    )
    graph = workflow(**draft)
    return model, data, view, graph, content


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("nearest", 283.15),
        ("interpolation", 288.15),
        ("mean", 290.65),
        ("sum", 0.03),
        ("min", 283.15),
        ("max", 293.15),
    ],
)
def test_six_temporal_methods_publish_real_worker_result(
    engine, actors, storage, tmp_path, method, expected
):
    user, _, _, project = actors
    model, data, view, graph, _ = temporal_case(storage, project, method)
    report = validate_workflow(graph, [model], [data], view)
    assert report.valid, report.issues
    run = RunManifest(
        scene=view,
        workflow=graph,
        models=(model,),
        data_assets=(data,),
        parameters=(),
        bindings=graph.input_bindings,
        software_version="test",
        container_image="local-test",
        timestamp=datetime.now(UTC),
        random_seed=42,
        environment={},
    )
    with Session(engine) as session, session.begin():
        for kind, resource in [
            ("model", model),
            ("data", data),
            ("scene", view),
            ("workflow", graph),
        ]:
            create_resource(
                session,
                user_id=user,
                project_id=project,
                kind=kind,
                identifier=resource.id,
                name=resource.name,
                spec=resource.model_dump(mode="json"),
            )
        job = submit_job(
            session,
            user_id=user,
            project_id=project,
            idempotency_key=str(uuid4()),
            manifest=run.model_dump(mode="json"),
        )
    runner = WorkflowWorker(
        engine, BuiltinRuntimeRegistry(Path("sample-data")), storage, work_root=tmp_path
    )
    runner.run(job.id)
    with Session(engine) as session:
        current = read_job(session, user_id=user, job_id=job.id)
        assert current.status == "SUCCEEDED", current.error
        reference = read_result(session, user_id=user, job_id=job.id)
    payload = json.loads(
        storage.read(
            ArtifactRecord(storage.bucket, reference["key"], reference["sha256"], reference["size"])
        )
    )
    result = payload["outputs"]["adapt.result"]
    assert result["value"] == pytest.approx(expected, abs=1e-12)
    assert result["method"] == method
    assert result["unit"] == ("m" if method == "sum" else "kelvin")
    assert result["observations_used"] == (1 if method == "nearest" else 2)
    assert result["nodata_policy"] == "propagate"
    assert payload["llm_calls"] == 0


def test_temporal_upload_rejects_forged_coverage_and_numeric_cadence(storage):
    _, data, _, _, content = temporal_case(storage, "check")
    assert data.quality["temporal_method"] == "mean"
    for updates in [
        {"time_start": datetime(2024, 1, 1, tzinfo=UTC)},
        {"time_resolution": "1 hour"},
    ]:
        with pytest.raises(CoastMASError, match="support|coverage"):
            inspect_data(content, data.model_copy(update=updates))


def test_temporal_marker_cannot_bypass_model_cadence_limits(storage):
    model, data, view, graph, _ = temporal_case(storage, "bounded")
    limited = model.model_copy(
        update={"temporal_scale": model.temporal_scale.model_copy(update={"minimum": 1.0})}
    )
    report = validate_workflow(graph, [limited], [data], view)
    assert not report.valid
    assert "TEMPORAL_SCALE" in [item.code for item in report.issues]


def test_temporal_preflight_rejects_target_that_differs_from_frozen_request(storage):
    model, data, view, graph, _ = temporal_case(storage, "target-check")
    changed = view.model_copy(
        update={
            "time_range": view.time_range.model_copy(
                update={"end": datetime(2025, 1, 1, 2, tzinfo=UTC)}
            )
        }
    )
    report = validate_workflow(graph, [model], [data], changed)
    assert not report.valid
    assert "TEMPORAL_TARGET" in [issue.code for issue in report.issues]
