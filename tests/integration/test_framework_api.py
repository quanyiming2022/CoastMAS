import json
from uuid import uuid4

from sqlalchemy.orm import Session

from coastmas.persistence.resources import create_resource
from tests.factories import asset, variable
from tests.unit.test_indicator_framework import framework, observations


def test_framework_versions_materialize_real_bytes_and_pin_both_dependencies(
    authenticated, storage, engine
):
    client, csrf, project, user = authenticated
    client.app.state.artifact_store = storage
    headers = {"X-CSRF-Token": csrf}
    identifier = uuid4().hex
    spec = framework(id=identifier).model_dump(mode="json")
    created = client.post(
        "/api/v1/indicator-frameworks", headers=headers, json={"project_id": project, "spec": spec}
    )
    assert created.status_code == 201, created.text
    payload = json.dumps({"frame": observations().model_dump(mode="json")}).encode()
    data_id = uuid4().hex
    stored = storage.put(f"{project}/data/{data_id}/input.json", payload)
    data = asset(
        id=data_id,
        name="Synthetic observations",
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
            )
        ],
        time_start="2020-01-01T00:00:00Z",
        time_end="2022-12-31T00:00:00Z",
        quality={"validated": True, "size_bytes": stored.size},
    )
    with Session(engine) as session, session.begin():
        create_resource(
            session,
            user_id=user,
            project_id=project,
            kind="data",
            identifier=data_id,
            name=data.name,
            spec=data.model_dump(mode="json"),
        )
    body = {
        "expected_version": 1,
        "data": {"id": data_id, "version": 1},
        "idempotency_key": "prepare-once",
    }
    response = client.post(
        f"/api/v1/indicator-frameworks/{identifier}/prepare", headers=headers, json=body
    )
    assert response.status_code == 201, response.text
    derived = response.json()["spec"]
    assert derived["quality"]["validated"] is True
    content = client.get(f"/api/v1/data-assets/{derived['id']}/download").json()
    assert content["frame"]["values"] == [[[0, 0], [1, 1]], [[1, 0], [2, 1]]]
    assert content["framework"] == {"id": identifier, "version": 1}
    assert content["weight_method"] == "manual"
    lineage = client.get(f"/api/v1/indicator-frameworks/for-asset/{derived['id']}")
    assert lineage.status_code == 200, lineage.text
    assert [(row["resource_id"], row["version"]) for row in lineage.json()["frameworks"]] == [
        (identifier, 1)
    ]
    assert [(row["resource_id"], row["version"]) for row in lineage.json()["observations"]] == [
        (data_id, 1)
    ]
    rechecked = client.post(
        f"/api/v1/data-assets/{derived['id']}/validate",
        headers=headers,
        json={"expected_version": 1},
    )
    assert rechecked.status_code == 200, rechecked.text
    assert (
        client.get(f"/api/v1/indicator-frameworks/for-asset/{derived['id']}?version=2").json()
        == lineage.json()
    )
    repeated = client.post(
        f"/api/v1/indicator-frameworks/{identifier}/prepare", headers=headers, json=body
    )
    assert repeated.json() == response.json()
    revision = {**spec, "version": 2, "name": "Revised references"}
    updated = client.put(
        f"/api/v1/indicator-frameworks/{identifier}",
        headers=headers,
        json={"expected_version": 1, "spec": revision},
    )
    assert updated.status_code == 200, updated.text
    conflict = client.post(
        f"/api/v1/indicator-frameworks/{identifier}/prepare", headers=headers, json=body
    )
    assert conflict.status_code == 409
    historical = client.get(f"/api/v1/indicator-frameworks/{identifier}?version=1")
    assert historical.json() == created.json()
    assert [
        row["version"]
        for row in client.get(f"/api/v1/indicator-frameworks/{identifier}/versions").json()
    ] == [1, 2]
    assert (
        client.delete(f"/api/v1/indicator-frameworks/{identifier}", headers=headers).status_code
        == 409
    )
    assert client.delete(f"/api/v1/data-assets/{data_id}", headers=headers).status_code == 409
    assert client.get(f"/api/v1/indicator-frameworks?project_id={uuid4()}").status_code == 403
    demo = client.get("/api/v1/indicator-frameworks/demo-categories")
    assert demo.json()["label"] == "DEMO FRAMEWORK"
    assert len(demo.json()["categories"]) == 5


def test_framework_plan_pins_prepared_data_and_framework_weight_method(
    authenticated, storage, engine, tmp_path
):
    from coastmas.domain.builtin_catalog import assessment_catalog
    from tests.factories import scene

    client, csrf, project, user = authenticated
    client.app.state.artifact_store = storage
    catalog = assessment_catalog(project)
    client.app.state.registry = catalog.registry
    identifier = uuid4().hex
    data_id = uuid4().hex
    context = scene(
        id=uuid4().hex,
        required_outputs=["scores", "change"],
        time_range={"start": "2020-01-01T00:00:00Z", "end": "2022-12-31T00:00:00Z"},
    )
    payload = json.dumps({"frame": observations().model_dump(mode="json")}).encode()
    stored = storage.put(f"{project}/data/{data_id}/input.json", payload)
    source = asset(
        id=data_id,
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
            )
        ],
        time_start="2020-01-01T00:00:00Z",
        time_end="2022-12-31T00:00:00Z",
        quality={"validated": True, "size_bytes": stored.size},
    )
    with Session(engine) as session, session.begin():
        for kind, item in [("scene", context), ("data", source)] + [
            ("model", model) for model in catalog.models
        ]:
            create_resource(
                session,
                user_id=user,
                project_id=project,
                kind=kind,
                identifier=item.id,
                name=item.name,
                spec=item.model_dump(mode="json"),
            )
    headers = {"X-CSRF-Token": csrf}
    assert (
        client.post(
            "/api/v1/indicator-frameworks",
            headers=headers,
            json={"project_id": project, "spec": framework(id=identifier).model_dump(mode="json")},
        ).status_code
        == 201
    )
    prepared = client.post(
        f"/api/v1/indicator-frameworks/{identifier}/prepare",
        headers=headers,
        json={
            "expected_version": 1,
            "data": {"id": data_id, "version": 1},
            "idempotency_key": "prepare",
        },
    ).json()
    body = {
        "framework_version": 1,
        "data": {"id": prepared["resource_id"], "version": 1},
        "scene": {"id": context.id, "version": 1},
        "assessment_method": "composite",
        "idempotency_key": "plan",
    }
    response = client.post(
        f"/api/v1/indicator-frameworks/{identifier}/plan", headers=headers, json=body
    )
    assert response.status_code == 201, response.text
    plan = response.json()["artifact"]
    assert plan["missing_conditions"] == []
    assert plan["management_goal"]["weight_method"] == "manual"
    assert plan["management_goal"]["template"] == "temporal_change"
    assert plan["candidate_workflow"]["input_bindings"][0]["source"] == body["data"]
    assert (
        client.post(
            f"/api/v1/indicator-frameworks/{identifier}/plan", headers=headers, json=body
        ).json()
        == response.json()
    )
    denied = client.post(
        f"/api/v1/indicator-frameworks/{identifier}/plan",
        headers=headers,
        json={**body, "data": {"id": data_id, "version": 1}, "idempotency_key": "forged"},
    )
    assert denied.status_code == 409
    rejected = client.post(
        f"/api/v1/indicator-frameworks/{identifier}/plan",
        headers=headers,
        json={**body, "assessment_method": "topsis", "idempotency_key": "bad-temporal"},
    )
    assert rejected.status_code == 422

    # Save a scientific assessment object, then execute and retrieve its actual run.
    from coastmas.worker.runtime import WorkflowWorker

    saved = client.post(
        "/api/v1/assessments", headers=headers, json={"planning_trace_id": response.json()["id"]}
    )
    assert saved.status_code == 201, saved.text
    record = saved.json()
    assert record["spec"]["framework"] == {"id": identifier, "version": 1}
    assert record["spec"]["data"] == body["data"]
    assert (
        client.post(
            "/api/v1/assessments",
            headers=headers,
            json={"planning_trace_id": response.json()["id"]},
        ).json()
        == record
    )
    assert client.get(f"/api/v1/assessments/{record['resource_id']}").json() == record
    submitted = client.post(
        f"/api/v1/assessments/{record['resource_id']}/run",
        headers={**headers, "Idempotency-Key": "assessment-run"},
        json={"assessment_version": 1, "random_seed": 7},
    )
    assert submitted.status_code == 202, submitted.text
    job_id = submitted.json()["id"]
    worker = WorkflowWorker(engine, catalog.registry, storage, work_root=tmp_path)
    worker.run(job_id)
    runs = client.get(f"/api/v1/assessments/{record['resource_id']}/runs?version=1")
    assert runs.status_code == 200, runs.text
    assert len(runs.json()) == 1
    assert runs.json()[0]["job"]["id"] == job_id
    assert runs.json()[0]["job"]["status"] == "SUCCEEDED"
    result = client.get(f"/api/v1/results/{runs.json()[0]['result_id']}/content")
    assert result.status_code == 200
    assert result.json()["outputs"]["composite.scores"]["values"] == [[0.25, 0.375], [0.625, 0.75]]
    assert (
        client.delete(
            f"/api/v1/workflows/{record['spec']['workflow']['id']}", headers=headers
        ).status_code
        == 409
    )
    copied = client.get(f"/api/v1/workflows/{record['spec']['workflow']['id']}").json()["spec"]
    copied.update(id=uuid4().hex, name="Unreferenced workflow copy")
    assert (
        client.post(
            "/api/v1/workflows", headers=headers, json={"project_id": project, "spec": copied}
        ).status_code
        == 201
    )
    for _ in range(2):
        deleted = client.delete(f"/api/v1/workflows/{copied['id']}", headers=headers)
        assert deleted.status_code == 204, deleted.text
