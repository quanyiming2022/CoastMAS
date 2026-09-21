import json
from uuid import uuid4

import numpy as np
from sqlalchemy.orm import Session

from coastmas.domain.builtin_catalog import assessment_catalog
from coastmas.persistence.resources import create_resource
from coastmas.persistence.schema import Resource
from coastmas.worker.runtime import WorkflowWorker
from tests.factories import asset, scene
from tests.integration.test_llm_provider import server as server
from tests.unit.test_indicator_frames import frame


def prepare(engine, actors, storage, client):
    owner, _, _, project = actors
    catalog = assessment_catalog(project)
    client.app.state.registry = catalog.registry
    client.app.state.artifact_store = storage
    normalizer = next(
        item for item in catalog.models if item.runtime_config["component"] == "normalize"
    )
    payload = json.dumps({"frame": frame().model_dump(mode="json")}).encode()
    blob = storage.put(f"{project}/plan/frame.json", payload)
    data = asset(
        id="data-" + uuid4().hex,
        type="json",
        format="JSON",
        variables=normalizer.inputs,
        uri=blob.uri,
        checksum=blob.sha256,
        quality={"validated": True, "size_bytes": blob.size},
    )
    context = scene(id="scene-" + uuid4().hex, required_outputs=["scores"])
    with Session(engine) as session, session.begin():
        for kind, spec in [("model", item) for item in catalog.models] + [
            ("data", data),
            ("scene", context),
        ]:
            create_resource(
                session,
                user_id=owner,
                project_id=project,
                kind=kind,
                identifier=spec.id,
                name=spec.name,
                spec=spec.model_dump(mode="json"),
            )
    return catalog, data, context


def test_plan_parse_recommend_build_share_artifact_then_run_real_workflow(
    authenticated,
    engine,
    actors,
    storage,
    tmp_path,
):
    client, csrf, project, _ = authenticated
    catalog, data, context = prepare(engine, actors, storage, client)
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": uuid4().hex}
    request = {
        "project_id": project,
        "scene": {"id": context.id, "version": 1},
        "goal": "可持续性评价：等权综合评价",
        "allow_external": False,
    }
    response = client.post("/api/v1/plans", headers=headers, json=request)
    assert response.status_code == 201, response.text
    plan = response.json()
    identifier = plan["id"]
    assert plan["artifact"]["candidate_workflow"]
    assert plan["reserved_requests"] == 0
    assert client.post("/api/v1/plans", headers=headers, json=request).json()["id"] == identifier
    for operation in ("parse", "recommend", "build-workflow"):
        result = client.post(f"/api/v1/plans/{identifier}/{operation}", headers=headers)
        assert result.status_code == 200, result.text
        assert result.json()["artifact"] == plan["artifact"]
        assert result.json()["reserved_requests"] == 0
    saved = client.post(f"/api/v1/plans/{identifier}/workflow", headers=headers)
    assert saved.status_code == 201, saved.text
    workflow_id = saved.json()["id"]
    assert (
        client.post(f"/api/v1/plans/{identifier}/workflow", headers=headers).json()["id"]
        == workflow_id
    )
    run = client.post(
        f"/api/v1/workflows/{workflow_id}/run",
        headers=headers,
        json={
            "workflow_version": 1,
            "scene_id": context.id,
            "scene_version": 1,
        },
    )
    assert run.status_code == 202, run.text
    worker = WorkflowWorker(engine, catalog.registry, storage, work_root=tmp_path)
    worker.run(run.json()["id"])
    assert client.get("/api/v1/jobs/" + run.json()["id"]).json()["status"] == "SUCCEEDED"
    result_id = client.get("/api/v1/results", params={"project_id": project}).json()[0]["id"]
    values = client.get(f"/api/v1/results/{result_id}/content").json()["outputs"][
        "composite.scores"
    ]["values"][0]
    np.testing.assert_allclose(values, [0.2, 0.4, 0.6, 0.8], rtol=0, atol=1e-12)
    with Session(engine) as session, session.begin():
        session.get(Resource, data.id).enabled = False
    unavailable = client.post(f"/api/v1/plans/{identifier}/recommend", headers=headers)
    assert unavailable.status_code == 422


def test_unrecognized_goal_is_preserved_and_external_access_not_assumed(
    authenticated, engine, actors, storage
):
    client, csrf, project, _ = authenticated
    _, _, context = prepare(engine, actors, storage, client)
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": uuid4().hex}
    goal = "同时模拟2050年潮汐与极端风暴，不能忽略相互作用"
    response = client.post(
        "/api/v1/plans",
        headers=headers,
        json={
            "project_id": project,
            "scene": {"id": context.id, "version": 1},
            "goal": goal,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["unresolved_goal"] == goal
    assert response.json()["artifact"] is None
    followup = client.post("/api/v1/plans/" + response.json()["id"] + "/parse", headers=headers)
    assert followup.status_code == 422
    assert followup.json()["error_code"] == "EXTERNAL_NOT_AUTHORIZED"


def test_external_endpoints_use_one_trace_and_do_not_export_source_uris(
    authenticated,
    engine,
    actors,
    storage,
    server,
):
    from coastmas.core.llm import OpenAICompatibleProvider, ProviderSettings

    client, csrf, project, _ = authenticated
    _, _, context = prepare(engine, actors, storage, client)
    client.app.state.llm_provider = OpenAICompatibleProvider(
        ProviderSettings(
            base_url=server[0],
            model="local-protocol-fixture",
            api_key="local-fixture-only",
            allow_private=True,
        )
    )
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": uuid4().hex}
    created = client.post(
        "/api/v1/plans",
        headers=headers,
        json={
            "project_id": project,
            "scene": {"id": context.id, "version": 1},
            "goal": "请分析尚未定义的复合海岸风险并报告缺失条件",
            "allow_external": True,
        },
    )
    assert created.status_code == 201, created.text
    identifier = created.json()["id"]
    server[2]["choices"][0]["finish_reason"] = "length"
    invalid = client.post(f"/api/v1/plans/{identifier}/parse", headers=headers)
    assert invalid.status_code == 422
    assert invalid.json()["error_code"] == "PROVIDER_TRUNCATED"
    server[2]["choices"][0]["finish_reason"] = "stop"
    repaired = client.post(f"/api/v1/plans/{identifier}/recommend", headers=headers)
    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["reserved_requests"] == 2
    final = client.post(f"/api/v1/plans/{identifier}/build-workflow", headers=headers)
    assert final.status_code == 200
    assert final.json()["artifact"] == repaired.json()["artifact"]
    assert len(server[1]) == 2
    prompt = json.loads(server[1][0]["messages"][1]["content"])
    assert len(prompt["models"]) <= 6
    assert "s3://" not in json.dumps(prompt)
    assert "local-fixture-only" not in json.dumps(prompt)
