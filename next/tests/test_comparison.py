"""Comparability is scientific, not just equal-length result arrays."""

import copy

import pytest
from coastmas_next.comparison import compare


def assessment(weights=(0.5, 0.5), scores=(0.65, 0.6), ids=("001", "002")):
    config = {
        "task": "assessment",
        "method": "weighted",
        "indicators": [
            {
                "concept": "distance",
                "unit": "km",
                "lower": 0,
                "upper": 2,
                "positive": True,
                "weight": weights[0],
            },
            {
                "concept": "pressure",
                "unit": "1",
                "lower": 0,
                "upper": 10,
                "positive": False,
                "weight": weights[1],
            },
        ],
    }
    return {
        "manifest": {
            "draft": {
                "purpose": "assessment",
                "selection": [{"asset_id": "asset", "revision": 1, "layer": "table"}],
                "mapping": [
                    {"asset_id": "asset", "field": "table/id", "role": "identity"},
                    {
                        "asset_id": "asset",
                        "field": "table/distance",
                        "concept": "distance",
                        "unit": "m",
                        "role": "feature",
                        "support": "point",
                    },
                ],
                "options": {},
            },
            "assets": [{"id": "asset", "sha256": "a" * 64}],
            "method": {"id": "method", "revision": 1, "spec": {"configuration": config}},
        },
        "data": {
            "row_ids": list(ids),
            "scores": list(scores),
            "ranks": [1, 2],
            "weights": list(weights),
            "scope": "complete_selected_observations",
        },
        "states": {"business_validated": False},
    }


def test_assessment_aligns_string_ids_and_explains_weight_sensitivity():
    left = assessment()
    right = assessment((0.2, 0.8), (0.36, 0.74), ("002", "001"))
    compared = compare(left, right)
    assert compared["comparable"] is True
    assert compared["mode"] == "method_sensitivity"
    assert compared["rows"][0]["id"] == "001"
    assert compared["rows"][0]["right"] == 0.74
    assert compared["rows"][0]["difference"] == pytest.approx(0.09)
    assert compared["rows"][1]["difference"] == pytest.approx(-0.24)
    assert compared["policy_decision"] is False
    assert compared["business_validated"] is False
    assert any(d["field"] == "weights" for d in compared["differences"])


@pytest.mark.parametrize(
    "change,code",
    [
        ("source", "SOURCE_DIFFERENT"),
        ("normalization", "NORMALIZATION_DIFFERENT"),
        ("method", "METHOD_DIFFERENT"),
        ("mapping", "MAPPING_DIFFERENT"),
        ("rows", "IDENTITY_DIFFERENT"),
        ("duplicate", "IDENTITY_INVALID"),
        ("scope", "SCOPE_DIFFERENT"),
        ("unknown", "UNIT_UNKNOWN"),
    ],
)
def test_incompatible_results_never_emit_a_numeric_difference(change, code):
    left, right = assessment(), assessment()
    if change == "source":
        right["manifest"]["assets"][0]["sha256"] = "b" * 64
    if change == "normalization":
        right["manifest"]["method"]["spec"]["configuration"]["indicators"][0]["upper"] = 3
    if change == "method":
        right["manifest"]["method"]["spec"]["configuration"]["method"] = "topsis"
    if change == "mapping":
        right["manifest"]["draft"]["mapping"][1]["support"] = "area"
    if change == "rows":
        right["data"]["row_ids"][0] = "different"
    if change == "duplicate":
        right["data"]["row_ids"] = ["001", "001"]
    if change == "scope":
        right["data"]["scope"] = "sample"
    if change == "unknown":
        right["manifest"]["method"]["spec"]["configuration"]["indicators"][0]["unit"] = "madeupunit"
    compared = compare(left, right)
    assert not compared["comparable"]
    assert code in {i["code"] for i in compared["issues"]}
    assert compared["rows"] == []


def test_equivalent_reference_units_convert_without_changing_meaning():
    left, right = assessment(), assessment()
    indicator = right["manifest"]["method"]["spec"]["configuration"]["indicators"][0]
    indicator.update(unit="m", upper=2000)
    result = compare(left, right)
    assert result["comparable"]
    assert result["rows"][0]["difference"] == 0
    assert result["adaptations"][0]["from_unit"] == "m"
    assert result["adaptations"][0]["to_unit"] == "km"


def test_temporal_native_calendar_and_actual_unit_conversion():
    left = assessment()
    left["manifest"]["draft"]["purpose"] = "temporal"
    left["data"] = {
        "variable": "height",
        "method": "mean",
        "calendar": "360_day",
        "start": "2022-02-29",
        "end": "2022-03-02",
        "value": 2,
        "conversion": {"source_unit": "m", "target_unit": "m"},
        "scope": "declared_interval",
        "source_observation_indices": [0, 1, 2],
        "adaptation": {"approximate": False},
    }
    right = copy.deepcopy(left)
    right["data"]["value"] = 200
    right["data"]["conversion"]["target_unit"] = "cm"
    compared = compare(left, right)
    assert compared["comparable"]
    assert compared["rows"][0]["right"] == 2
    assert compared["rows"][0]["difference"] == 0
    right["data"]["calendar"] = "standard"
    compared = compare(left, right)
    assert not compared["comparable"]
    assert "TEMPORAL_SUPPORT_DIFFERENT" in {i["code"] for i in compared["issues"]}


def test_optimization_infeasible_is_unknown_not_unselected():
    left = assessment()
    left["manifest"]["draft"]["purpose"] = "optimization"
    config = {
        "task": "optimization",
        "method": "binary_allocation",
        "quantities": {
            k: {"concept": k, "unit": "m^2" if k == "area" else "1"}
            for k in ["benefit", "cost", "area", "ecological_cost", "risk"]
        },
        "protected_concept": "protected",
        "risk_aggregation": "additive_index",
        "additivity_basis": "Engineering only",
        "budget": 3,
        "minimum_area": 1,
        "maximum_ecological_cost": 10,
        "maximum_risk": 10,
        "time_limit": 5,
    }
    left["manifest"]["method"]["spec"]["configuration"] = config
    left["data"] = {
        "scope": "complete_selected_units",
        "constraints_satisfied": True,
        "allocations": [
            {
                "id": "001",
                "selected": True,
                "allowed": True,
                "benefit": 2,
                "cost": 1,
                "area": 3,
                "ecological_cost": 0,
                "risk": 0,
            }
        ],
    }
    right = copy.deepcopy(left)
    right["manifest"]["method"]["spec"]["configuration"]["budget"] = 0
    right["data"]["constraints_satisfied"] = False
    right["data"]["allocations"][0]["selected"] = None
    compared = compare(left, right)
    assert not compared["comparable"]
    assert compared["rows"] == []
    assert "INFEASIBLE_RESULT" in {i["code"] for i in compared["issues"]}
    assert any(d["field"] == "budget" for d in compared["differences"])


def completed_assessment(store, client, project):
    from coastmas_next.worker import Worker
    from test_decisions import prepare

    task = prepare(
        client,
        project,
        "assessment",
        b"id,x\n001,2\n002,8\n",
        {
            "id": {"role": "identity"},
            "x": {"role": "feature", "concept": "x", "unit": "m", "support": "point"},
        },
        {
            "task": "assessment",
            "method": "weighted",
            "indicators": [
                {
                    "concept": "x",
                    "unit": "m",
                    "lower": 0,
                    "upper": 10,
                    "positive": True,
                    "weight": 1,
                }
            ],
        },
    )
    ids = []
    for key in ["left", "right"]:
        reply = client.post(
            f"/api/tasks/{task['id']}/execute",
            json={"expected_revision": task["revision"], "idempotency_key": key},
        )
        assert reply.status_code == 202, reply.text
        ids.append(reply.json()["id"])
        assert Worker(store).run_once()
    return ids


def comparison_task(client, project, ids):
    reply = client.post(
        "/api/tasks",
        json={
            "project_id": project,
            "purpose": "comparison",
            "title": "Actual immutable result comparison",
        },
    )
    assert reply.status_code == 201, reply.text
    task = reply.json()
    task["draft"]["options"] = {"left_job_id": ids[0], "right_job_id": ids[1]}
    response = client.put(
        f"/api/tasks/{task['id']}", json={"expected_revision": 1, "draft": task["draft"]}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_actual_comparison_persists_runs_exports_and_isolates_project(workspace):
    import csv
    import io
    import json
    import zipfile

    from coastmas_next.worker import Worker

    _, store, client, project = workspace
    ids = completed_assessment(store, client, project)
    task = comparison_task(client, project, ids)
    listing = client.get(f"/api/projects/{project}/completed-results?limit=1").json()
    assert listing["total"] == 2
    assert len(listing["items"]) == 1
    assert listing["items"][0]["title"] == "Decision from actual table"
    assert listing["items"][0]["draft_revision"] >= 2
    assert (
        client.get(f"/api/tasks/{task['id']}").json()["draft"]["options"]["left_job_id"] == ids[0]
    )
    preflight = client.get(f"/api/tasks/{task['id']}/preflight").json()
    assert preflight["ready"], preflight
    run = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "compare"},
    )
    assert run.status_code == 202, run.text
    assert Worker(store).run_once()
    result = client.get(f"/api/jobs/{run.json()['id']}/result").json()
    assert result["data"]["rows"][0] == {
        "id": "001",
        "left": 0.2,
        "right": 0.2,
        "difference": 0.0,
        "unit": "1",
    }
    assert result["data"]["business_validated"] is False
    assert result["manifest"]["comparison_inputs"][0]["job_id"] == ids[0]
    exported = client.get(f"/api/jobs/{run.json()['id']}/bundle")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read("comparison.csv").decode("utf-8-sig"))))
        assert len(rows) == 2 and rows[0]["id"] == "001"
        metadata = json.loads(archive.read("comparison.csv-metadata.json"))
        assert metadata["tableSchema"]["columns"][0]["datatype"] == "string"
    imported = client.post(
        f"/api/projects/{project}/assets", files={"file": ("comparison.zip", exported.content)}
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["asset"]["facts"]["profile"] == "csvw"
    assert not imported.json()["asset"]["facts"]["issues"]
    actor = client.get("/api/session").json()["id"]
    other_project = store.create_project(actor, "Different project, same actor")
    foreign = comparison_task(client, other_project, ids)
    blocked = client.get(f"/api/tasks/{foreign['id']}/preflight").json()
    assert not blocked["ready"]
    assert blocked["issues"][0]["code"] == "RESULT_PROJECT_MISMATCH"


def test_result_integrity_rechecked_by_worker_and_read_only_role_cannot_execute(workspace):
    from coastmas_next.app import create_app
    from coastmas_next.worker import Worker
    from fastapi.testclient import TestClient

    settings, store, client, project = workspace
    ids = completed_assessment(store, client, project)
    task = comparison_task(client, project, ids)
    viewer = TestClient(create_app(settings))
    login = viewer.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    ).json()
    viewer.headers["X-CSRF-Token"] = login["csrf"]
    assert viewer.get(f"/api/projects/{project}/completed-results").status_code == 200
    assert (
        viewer.post(
            f"/api/tasks/{task['id']}/execute",
            json={"expected_revision": task["revision"], "idempotency_key": "denied"},
        ).status_code
        == 403
    )
    run = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "integrity"},
    )
    assert run.status_code == 202, run.text
    original = client.get(f"/api/jobs/{ids[0]}").json()
    (settings.storage_root / original["output_key"]).write_text("{}")
    assert Worker(store).run_once()
    failed = client.get(f"/api/jobs/{run.json()['id']}").json()
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "COMPARISON_INPUT_CHANGED"


def test_actual_cf_result_contract_and_changed_interpolation_evidence():
    left = assessment()
    left["manifest"]["draft"]["purpose"] = "temporal"
    left["data"] = {
        "variable": "height",
        "method": "interpolate",
        "calendar": "360_day",
        "target": "2022-02-29",
        "value": 2,
        "conversion": {"source_unit": "m", "target_unit": "m"},
        "scope": "declared_instant",
        "source_observation_indices": [0, 1],
        "source_times": [0, 2],
        "time_axis_unit": "days since 2022-02-28",
        "cell_methods": "time: point",
        "standard_version": "CF-1.12",
        "adaptation": {
            "approximate": True,
            "basis": "explicit engineering assumption",
            "weights": [0.5, 0.5],
            "nearest_tolerance": None,
            "tie_choice": None,
        },
    }
    right = copy.deepcopy(left)
    right["data"]["conversion"]["target_unit"] = "cm"
    right["data"]["value"] = 200
    assert compare(left, right)["comparable"]
    right["data"]["adaptation"]["basis"] = "different assumption"
    blocked = compare(left, right)
    assert not blocked["comparable"]
    assert "TEMPORAL_SUPPORT_DIFFERENT" in {i["code"] for i in blocked["issues"]}


def test_comparison_bundle_carries_hash_verified_parent_results(workspace):
    import hashlib
    import io
    import json
    import zipfile

    from coastmas_next.worker import Worker

    _, store, client, project = workspace
    ids = completed_assessment(store, client, project)
    task = comparison_task(client, project, ids)
    run = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "provenance"},
    ).json()
    assert Worker(store).run_once()
    exported = client.get(f"/api/jobs/{run['id']}/bundle")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        result = json.loads(archive.read("result.json"))
        for side, reference in zip(
            ["left", "right"], result["manifest"]["comparison_inputs"], strict=True
        ):
            raw = archive.read(f"inputs/{side}.json")
            assert hashlib.sha256(raw).hexdigest() == reference["sha256"]
            assert json.loads(raw)["data"]["row_ids"] == ["001", "002"]


def test_actual_optimization_constraint_sensitivity_preserves_protected_units(workspace):
    from coastmas_next.worker import Worker
    from test_decisions import prepare

    _, store, client, project = workspace
    quantities = {
        name: {"concept": name, "unit": "m^2" if name == "area" else "1"}
        for name in ["benefit", "cost", "area", "ecological_cost", "risk"]
    }
    config = {
        "task": "optimization",
        "method": "binary_allocation",
        "quantities": quantities,
        "protected_concept": "protected",
        "risk_aggregation": "additive_index",
        "additivity_basis": "Explicit engineering additive quantities",
        "budget": 3,
        "minimum_area": 1,
        "maximum_ecological_cost": 10,
        "maximum_risk": 10,
        "time_limit": 5,
    }
    mappings = {
        "id": {"role": "identity"},
        "protected": {"role": "constraint", "concept": "protected"},
        **{
            name: {
                "role": "feature",
                "concept": name,
                "unit": spec["unit"],
                "support": "management_unit",
            }
            for name, spec in quantities.items()
        },
    }
    data = (
        b"id,benefit,cost,area,ecological_cost,risk,protected\n"
        b"001,10,2,3,0,0,false\n002,9,2,3,0,0,false\n003,999,1,3,0,0,true\n"
    )
    ids = []
    for budget in [3, 4]:
        task = prepare(
            client, project, "optimization", data, mappings, {**config, "budget": budget}
        )
        run = client.post(
            f"/api/tasks/{task['id']}/execute",
            json={"expected_revision": task["revision"], "idempotency_key": "real-allocation"},
        )
        assert run.status_code == 202, run.text
        ids.append(run.json()["id"])
        assert Worker(store).run_once()
    task = comparison_task(client, project, ids)
    run = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "allocation-comparison"},
    )
    assert run.status_code == 202, run.text
    assert Worker(store).run_once()
    result = client.get(f"/api/jobs/{run.json()['id']}/result").json()["data"]
    assert result["mode"] == "constraint_sensitivity"
    assert result["rows"] == [
        {"id": "001", "left": True, "right": True, "difference": 0, "unit": "selection"},
        {"id": "002", "left": False, "right": True, "difference": 1, "unit": "selection"},
        {"id": "003", "left": False, "right": False, "difference": 0, "unit": "selection"},
    ]
    assert result["differences"] == [{"field": "budget", "left": 3.0, "right": 4.0}]
    assert result["policy_decision"] is False


def test_temperature_difference_is_an_increment_not_an_absolute_temperature():
    left = assessment()
    left["manifest"]["draft"]["purpose"] = "temporal"
    left["data"] = {
        "variable": "temperature",
        "method": "mean",
        "calendar": "standard",
        "start": "2022-01-01",
        "end": "2022-01-02",
        "scope": "declared_interval",
        "conversion": {"source_unit": "degC", "target_unit": "degC"},
        "value": 20,
    }
    right = copy.deepcopy(left)
    right["data"]["conversion"]["target_unit"] = "K"
    right["data"]["value"] = 294.15
    result = compare(left, right)
    assert result["comparable"]
    assert result["rows"][0]["difference"] == pytest.approx(1)
    assert result["rows"][0]["difference_unit"] == "delta_degree_Celsius"
