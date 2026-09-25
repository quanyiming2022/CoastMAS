"""Real asset-derived decisions use approved science, no manual matrix or guessed cost."""

import csv
import io
import json
import zipfile

from coastmas_next.worker import Worker


def prepare(client, project, purpose, content, mappings, configuration, options=None):
    method = client.post(
        f"/api/projects/{project}/templates",
        json={
            "title": "Engineering method, not a coastal conclusion",
            "purpose": "method",
            "profiles": ["csv"],
            "basis": "Explicit independent technical test specification",
            "configuration": configuration,
        },
    ).json()
    client.post(f"/api/templates/{method['id']}/approve", json={"revision": 1})
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Decision from actual table", "purpose": purpose},
    ).json()
    response = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("observations.csv", content)},
        data={"task_id": task["id"], "expected_revision": "1"},
    ).json()
    task = response["task"]
    asset = response["asset"]
    task["draft"]["mapping"] = [
        {"asset_id": asset["id"], "field": "table/" + field, **spec}
        for field, spec in mappings.items()
    ]
    task["draft"]["method_id"] = method["id"]
    task["draft"]["options"] = {"method_revision": 1, **(options or {})}
    task = client.put(
        f"/api/tasks/{task['id']}",
        json={"expected_revision": task["revision"], "draft": task["draft"]},
    ).json()
    return task


def test_assessment_reads_whole_table_converts_units_and_preserves_identity(workspace):
    _, store, client, project = workspace
    method = {
        "task": "assessment",
        "method": "weighted",
        "indicators": [
            {
                "concept": "distance",
                "unit": "km",
                "lower": 0,
                "upper": 2,
                "positive": True,
                "weight": 0.5,
            },
            {
                "concept": "pressure",
                "unit": "1",
                "lower": 0,
                "upper": 10,
                "positive": False,
                "weight": 0.5,
            },
        ],
    }
    mappings = {
        "id": {"role": "identity"},
        "distance": {"role": "feature", "concept": "distance", "unit": "m", "support": "point"},
        "pressure": {"role": "feature", "concept": "pressure", "unit": "1", "support": "point"},
    }
    task = prepare(
        client,
        project,
        "assessment",
        b"id,distance,pressure\n001,1000,2\n002,2000,8\n",
        mappings,
        method,
    )
    run = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "assessment"},
    )
    assert run.status_code == 202, run.text
    assert Worker(store).run_once()
    result = client.get(f"/api/jobs/{run.json()['id']}/result").json()
    assert result["data"]["row_ids"] == ["001", "002"]
    assert abs(result["data"]["scores"][0] - 0.65) < 1e-12
    assert abs(result["data"]["scores"][1] - 0.6) < 1e-12
    assert result["data"]["method_snapshot"]["revision"] == 1
    assert result["states"]["business_validated"] is False


def test_optimization_bulk_loads_protection_and_never_invents_missing_cost(workspace):
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
        "additivity_basis": "Engineering additive independent unit test only",
        "budget": 3,
        "minimum_area": 1,
        "maximum_ecological_cost": 10,
        "maximum_risk": 10,
        "time_limit": 5,
    }
    mappings = {
        "id": {"role": "identity"},
        "protected": {"role": "constraint", "concept": "protected"},
    }
    mappings.update(
        {
            name: {
                "role": "feature",
                "concept": name,
                "unit": spec["unit"],
                "support": "management_unit",
            }
            for name, spec in quantities.items()
        }
    )
    data = (
        b"id,benefit,cost,area,ecological_cost,risk,protected\n"
        b"001,10,2,3,0,0,false\n002,9,2,3,0,0,false\n003,999,1,3,0,0,true\n"
    )
    task = prepare(client, project, "optimization", data, mappings, config)
    run = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "optimization"},
    )
    assert run.status_code == 202, run.text
    Worker(store).run_once()
    result = client.get(f"/api/jobs/{run.json()['id']}/result").json()["data"]
    assert result["selected"] == ["001"]
    assert result["constraints_satisfied"] is True
    assert result["cost"] == 2
    exported = client.get(f"/api/jobs/{run.json()['id']}/bundle")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        records = list(
            csv.DictReader(io.StringIO(archive.read("allocations.csv").decode("utf-8-sig")))
        )
        assert [r["id"] for r in records] == ["001", "002", "003"]
        assert [r["selected"] for r in records] == ["true", "false", "false"]
        assert records[2]["allowed"] == "false"
        assert float(records[0]["cost"]) == 2
        metadata = json.loads(archive.read("allocations.csv-metadata.json"))
        columns = {c["name"]: c for c in metadata["tableSchema"]["columns"]}
        assert columns["id"]["datatype"] == "string"
        assert columns["selected"]["datatype"] == "boolean"
        assert columns["area"]["titles"] == ["area", "Area (m^2)"]
        assert "observations.csv" not in archive.namelist()
    imported = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("allocation-results.zip", exported.content)},
    )
    assert imported.status_code == 201, imported.text
    facts = imported.json()["asset"]["facts"]
    assert facts["profile"] == "csvw"
    assert not facts["issues"]
    bad = prepare(
        client, project, "optimization", data.replace(b"001,10,2,", b"001,10,,"), mappings, config
    )
    check = client.get(f"/api/tasks/{bad['id']}/preflight").json()
    assert check["ready"] is False
    assert any(issue["code"] == "OBSERVATION_MISSING" for issue in check["issues"])


def test_optimization_area_threshold_uses_declared_unit_and_protection_is_required(workspace):
    _, store, client, project = workspace
    quantities = {
        name: {"concept": name, "unit": "ha" if name == "area" else "1"}
        for name in ["benefit", "cost", "area", "ecological_cost", "risk"]
    }
    config = {
        "task": "optimization",
        "method": "binary_allocation",
        "quantities": quantities,
        "protected_concept": "protected",
        "risk_aggregation": "additive_index",
        "additivity_basis": "Explicit test area threshold",
        "budget": 10,
        "minimum_area": 2,
        "maximum_ecological_cost": 10,
        "maximum_risk": 10,
        "time_limit": 5,
    }
    mappings = {
        "id": {"role": "identity"},
        "protected": {"role": "constraint", "concept": "protected"},
    }
    mappings.update(
        {
            name: {
                "role": "feature",
                "concept": name,
                "unit": spec["unit"],
                "support": "management_unit",
            }
            for name, spec in quantities.items()
        }
    )
    task = prepare(
        client,
        project,
        "optimization",
        b"id,benefit,cost,area,ecological_cost,risk,protected\n001,10,1,1,0,0,false\n",
        mappings,
        config,
    )
    run = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "area"},
    )
    assert run.status_code == 202, run.text
    Worker(store).run_once()
    result = client.get(f"/api/jobs/{run.json()['id']}/result").json()["data"]
    assert result["status"] == "INFEASIBLE"
    assert result["selected"] == []
    assert result["allocations"][0]["selected"] is None
    bad = prepare(
        client,
        project,
        "optimization",
        b"id,benefit,cost,area,ecological_cost,risk,protected\n001,10,1,3,0,0,\n",
        mappings,
        config,
    )
    check = client.get(f"/api/tasks/{bad['id']}/preflight").json()
    assert any(issue["code"] == "PROTECTION_UNKNOWN" for issue in check["issues"])


def test_method_authoring_uses_server_draft_and_atomic_publication(workspace):
    _, _, client, project = workspace
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Reviewed method", "purpose": "assessment"},
    ).json()
    draft = task["draft"]
    draft["options"]["editor"] = "method"
    draft["options"]["definition"] = {
        "basis": "Explicit engineering reference",
        "profiles": ["csv"],
        "configuration": {
            "task": "assessment",
            "method": "weighted",
            "indicators": [
                {
                    "concept": "distance",
                    "unit": "m",
                    "lower": 0,
                    "upper": 10,
                    "positive": True,
                    "weight": 1,
                }
            ],
        },
    }
    task = client.put(
        f"/api/tasks/{task['id']}", json={"expected_revision": 1, "draft": draft}
    ).json()
    response = client.post(
        f"/api/tasks/{task['id']}/publish-method",
        json={"expected_revision": task["revision"], "approve": True},
    )
    assert response.status_code == 201, response.text
    published = response.json()
    assert published["template"]["approved"] is True
    assert (
        published["task"]["draft"]["options"]["publication"]["template_id"]
        == published["template"]["id"]
    )
    repeated = client.post(
        f"/api/tasks/{task['id']}/publish-method",
        json={"expected_revision": task["revision"], "approve": True},
    )
    assert repeated.status_code == 201
    assert repeated.json()["template"]["id"] == published["template"]["id"]
    assert len(client.get(f"/api/projects/{project}/templates").json()) == 1


def test_invalid_method_and_unauthorized_approval_leave_no_partial_publication(workspace):
    _, store, client, project = workspace
    response = client.post(
        f"/api/projects/{project}/method-drafts",
        json={"title": "Invalid unit test", "purpose": "assessment"},
    )
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["draft"]["options"]["editor"] == "method"
    draft = task["draft"]
    draft["options"]["definition"] = {
        "basis": "Test only",
        "profiles": ["csv"],
        "configuration": {
            "task": "assessment",
            "method": "weighted",
            "indicators": [
                {
                    "concept": "unknown",
                    "unit": "not_a_real_unit_39814",
                    "lower": 0,
                    "upper": 10,
                    "positive": True,
                    "weight": 1,
                }
            ],
        },
    }
    saved = client.put(
        f"/api/tasks/{task['id']}", json={"expected_revision": task["revision"], "draft": draft}
    ).json()
    invalid = client.post(
        f"/api/tasks/{task['id']}/publish-method",
        json={"expected_revision": saved["revision"], "approve": True},
    )
    assert invalid.status_code == 422, invalid.text
    assert client.get(f"/api/tasks/{task['id']}").json()["revision"] == saved["revision"]
    assert client.get(f"/api/projects/{project}/templates").json() == []
    owner = store.project_list(client.get("/api/session").json()["id"])[0]
    analyst = store.create_account("analyst@example.test", "safe-password-for-tests")
    actor = client.get("/api/session").json()["id"]
    store.set_member(actor, owner["id"], analyst, "analyst")
    login = client.post(
        "/api/session",
        json={"email": "analyst@example.test", "password": "safe-password-for-tests"},
    ).json()
    client.headers["X-CSRF-Token"] = login["csrf"]
    denied = client.post(
        f"/api/tasks/{task['id']}/publish-method",
        json={"expected_revision": saved["revision"], "approve": True},
    )
    assert denied.status_code == 403
    assert client.get(f"/api/projects/{project}/templates").json() == []


def test_method_revision_keeps_one_lineage_and_old_definition(workspace):
    _, _, client, project = workspace
    task = client.post(
        f"/api/projects/{project}/method-drafts",
        json={"title": "Versioned method", "purpose": "assessment"},
    ).json()
    task["draft"]["options"]["definition"] = {
        "basis": "Technical test",
        "profiles": ["csv"],
        "configuration": {
            "task": "assessment",
            "method": "weighted",
            "indicators": [
                {
                    "concept": "distance",
                    "unit": "m",
                    "lower": 0,
                    "upper": 10,
                    "positive": True,
                    "weight": 1,
                }
            ],
        },
    }
    saved = client.put(
        f"/api/tasks/{task['id']}",
        json={"expected_revision": task["revision"], "draft": task["draft"]},
    ).json()
    first = client.post(
        f"/api/tasks/{task['id']}/publish-method",
        json={"expected_revision": saved["revision"], "approve": True},
    ).json()
    draft = first["task"]["draft"]
    draft["options"]["definition"]["configuration"]["indicators"][0]["upper"] = 20
    saved = client.put(
        f"/api/tasks/{task['id']}",
        json={"expected_revision": first["task"]["revision"], "draft": draft},
    ).json()
    response = client.post(
        f"/api/tasks/{task['id']}/publish-method",
        json={"expected_revision": saved["revision"], "approve": False},
    )
    assert response.status_code == 201, response.text
    second = response.json()["template"]
    assert second["id"] == first["template"]["id"]
    assert second["revision"] == 2 and second["approved"] is False
    history = client.get(f"/api/templates/{second['id']}/history").json()
    assert history[0]["spec"]["configuration"]["indicators"][0]["upper"] == 10
    assert history[1]["spec"]["configuration"]["indicators"][0]["upper"] == 20
    assert len(client.get(f"/api/projects/{project}/templates").json()) == 1
