import json
import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from celery.contrib.testing.worker import start_worker
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from coastmas.adapters.runtime import PythonFunctionAdapter
from coastmas.core.contracts import RunManifest
from coastmas.core.execution import ExecutionRegistry
from coastmas.persistence.jobs import cancel_job, read_job, read_result, submit_job
from coastmas.persistence.resources import create_resource
from coastmas.persistence.schema import Job, Membership, ResultBundle
from coastmas.worker.runtime import WorkflowWorker, create_queue
from tests.factories import asset, model, scene, variable, workflow


def prepare_worker(engine, actors, storage, tmp_path, handler):
    user, _, _, project = actors
    suffix = uuid4().hex
    blob = storage.put(f"{project}/input/height.json", b'{"height":[1,2]}')
    data = asset(
        id="dem-" + suffix,
        type="table",
        format="JSON",
        uri=blob.uri,
        checksum=blob.sha256,
        variables=(variable(data_type="array"),),
        quality={"size_bytes": blob.size, "validated": True},
    )
    spec = model(
        id="screen-" + suffix,
        inputs=(variable(data_type="array"),),
        outputs=(variable("result", data_type="array"),),
    )
    view = scene(id="scene-" + suffix)
    base = workflow().model_dump(mode="json")
    base["id"] = "wf-" + suffix
    base["nodes"][0]["model_id"] = spec.id
    base["input_bindings"][0]["source"]["id"] = data.id
    graph = workflow(**base)
    run = RunManifest(
        scene=view,
        workflow=graph,
        models=(spec,),
        data_assets=(data,),
        parameters=(),
        software_version="test",
        container_image="local-test",
        timestamp=datetime.now(UTC),
        random_seed=42,
        bindings=graph.input_bindings,
        environment={},
    )
    with Session(engine) as session, session.begin():
        for kind, resource in [
            ("model", spec),
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
    registry = ExecutionRegistry()
    registry.register(spec, PythonFunctionAdapter({"handler": handler}), "handler")
    runner = WorkflowWorker(engine, registry, storage, work_root=tmp_path)
    return runner, job


def test_real_redis_worker_to_postgres_and_minio_publishes_once(engine, actors, storage, tmp_path):
    user, _, _, project = actors

    def add(inputs, parameters):
        return {"result": [value + parameters["increment"] for value in inputs["height"]]}

    runner, job = prepare_worker(engine, actors, storage, tmp_path, add)
    queue = "coastmas-test-" + uuid4().hex
    app = create_queue(runner, broker_url="redis://127.0.0.1:56379/15", queue_name=queue)
    try:
        with start_worker(app, perform_ping_check=False, pool="solo", shutdown_timeout=10):
            app.send_task("coastmas.execute", args=[job.id], queue=queue)
            app.send_task("coastmas.execute", args=[job.id], queue=queue)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                with Session(engine) as session:
                    current = read_job(session, user_id=user, job_id=job.id)
                if current.status in ("SUCCEEDED", "FAILED", "CANCELLED"):
                    break
                time.sleep(0.1)
            assert current.status == "SUCCEEDED", current.error
            with Session(engine) as session:
                result = read_result(session, user_id=user, job_id=job.id)
                assert read_job(session, user_id=user, job_id=job.id).attempt == 1
            from coastmas.adapters.storage import ArtifactRecord

            record = ArtifactRecord(storage.bucket, result["key"], result["sha256"], result["size"])
            outputs = json.loads(storage.read(record))
            assert outputs["outputs"] == {"screen-node.result": [1.5, 2.5]}
            assert outputs["llm_calls"] == 0
            view = outputs["result_view"]
            assert view["binding_status"] == "NOT_APPLICABLE"
            assert view["objects"][0]["source_pointer"] == "/outputs/screen-node.result"
            assert view["objects"][0]["model"]["id"] == job.manifest["models"][0]["id"]
            assert not list(tmp_path.iterdir())
    finally:
        app.close()


@pytest.mark.parametrize("action", ["cancel", "revoke"])
def test_running_worker_stops_on_cancel_or_permission_revocation(
    engine, actors, storage, tmp_path, action
):
    def slow(inputs, parameters):
        import time

        time.sleep(20)
        return {"result": inputs["height"]}

    user, _, _, project = actors
    runner, job = prepare_worker(engine, actors, storage, tmp_path, slow)
    queue = "coastmas-test-" + uuid4().hex
    app = create_queue(runner, broker_url="redis://127.0.0.1:56379/15", queue_name=queue)
    try:
        with start_worker(app, perform_ping_check=False, pool="solo", shutdown_timeout=10):
            app.send_task("coastmas.execute", args=[job.id], queue=queue)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                with Session(engine) as session:
                    status = session.get(Job, job.id).status
                if status == "RUNNING":
                    break
                time.sleep(0.05)
            assert status == "RUNNING"
            with Session(engine) as session, session.begin():
                if action == "cancel":
                    cancel_job(session, user_id=user, job_id=job.id)
                else:
                    session.execute(
                        delete(Membership).where(
                            Membership.project_id == project, Membership.user_id == user
                        )
                    )
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                with Session(engine) as session:
                    status = session.get(Job, job.id).status
                if status in ("FAILED", "CANCELLED", "SUCCEEDED"):
                    break
                time.sleep(0.05)
            assert status == ("CANCELLED" if action == "cancel" else "FAILED")
            with Session(engine) as session:
                assert (
                    session.scalar(select(ResultBundle).where(ResultBundle.job_id == job.id))
                    is None
                )
            assert not list(tmp_path.iterdir())
    finally:
        app.close()


@pytest.mark.parametrize("field,value", [("enabled", False), ("archived", True)])
def test_manifest_rechecks_cached_resource_lifecycle(
    engine, actors, storage, tmp_path, field, value
):
    from coastmas.core.errors import CoastMASError
    from coastmas.persistence.schema import Resource

    def add(inputs, parameters):
        return {"result": [item + parameters["increment"] for item in inputs["height"]]}

    runner, job = prepare_worker(engine, actors, storage, tmp_path, add)
    manifest = RunManifest.model_validate(job.manifest)
    with Session(engine) as session:
        cached = session.get(Resource, manifest.data_assets[0].id)
        assert cached.enabled and not cached.archived
        with Session(engine) as change, change.begin():
            setattr(change.get(Resource, cached.id), field, value)
        with pytest.raises(CoastMASError):
            runner._verify_manifest(session, job, manifest)


def test_worker_rejects_catalog_references_to_other_project_objects(
    engine, actors, storage, tmp_path, monkeypatch
):
    from coastmas.core.errors import CoastMASError

    put = storage.put
    monkeypatch.setattr(storage, "put", lambda key, content: put("other-project/" + key, content))
    runner, job = prepare_worker(engine, actors, storage, tmp_path, lambda inputs, parameters: {})
    with Session(engine) as session, pytest.raises(CoastMASError, match="project"):
        runner._verify_manifest(session, job, RunManifest.model_validate(job.manifest))
