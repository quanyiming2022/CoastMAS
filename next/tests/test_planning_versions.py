"""Independent planning sets: publication is configuration, not solver approval."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def endpoint(project, kind="objectives"):
    return f"/api/v1/projects/{project}/planning/{kind}"


def new(client, project, kind="objectives", name="Engineering objective set"):
    response = client.post(endpoint(project, kind), json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def save(client, project, item, body, kind="objectives"):
    return client.put(
        endpoint(project, kind) + "/" + item["id"],
        headers={"If-Match": f'"{item["revision"]}"'},
        json={"name": item["name"], "body": body},
    )


def test_sets_exist_without_problem_and_freeze_versions(workspace):
    _, store, client, project = workspace
    item = new(client, project)
    assert item["revision"] == 1 and item["versions"] == []
    body = {"mode": "single_objective", "items": [{"metric": "minimize_construction_cost"}]}
    response = save(client, project, item, body)
    assert response.status_code == 200, response.text
    saved = response.json()
    url = endpoint(project) + "/" + item["id"]
    version = client.post(url + "/versions", headers={"If-Match": '"2"'}).json()
    assert version["version"] == 1 and version["body"] == body
    assert len(version["sha256"]) == 64
    assert version["validation_state"] == "configuration_validated"
    response = save(client, project, saved, {"mode": "pareto_multiobjective", "items": []})
    assert response.status_code == 200
    assert client.get(url + "/versions/" + version["id"]).json() == version
    assert client.post(url + "/versions", headers={"If-Match": '"3"'}).status_code == 422
    # Even an accidental raw UPDATE must not alter a published object.
    with store.engine.begin() as c:
        with pytest.raises(DBAPIError):
            c.execute(
                text("UPDATE objective_set_revisions SET body='{}' WHERE id=:id"),
                {"id": version["id"]},
            )


def test_required_etag_conflicts_and_permissions(workspace):
    settings, store, client, project = workspace
    item = new(client, project)
    url = endpoint(project) + "/" + item["id"]
    proposed = {"name": "mine", "body": item["body"]}
    assert client.put(url, json=proposed).status_code == 428
    assert client.put(url, headers={"If-Match": '"1"'}, json=proposed).status_code == 200
    conflict = client.put(url, headers={"If-Match": '"1"'}, json={**proposed, "name": "stale"})
    assert conflict.status_code == 412
    assert conflict.json()["details"]["current"]["name"] == "mine"
    response = client.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    )
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    assert client.get(url).status_code == 200
    assert client.post(endpoint(project), json={"name": "no"}).status_code == 403
    assert client.post(url + "/versions", headers={"If-Match": '"2"'}).status_code == 403
    assert client.get(endpoint("foreign")).status_code == 404


def test_constraints_need_explicit_business_basis_and_decisions_have_own_contract(workspace):
    _, _, client, project = workspace
    constraint = new(client, project, "constraints")
    body = {"items": [{"recipe": "development_quota", "limit": 30.0, "unit": "m^2", "basis": ""}]}
    saved = save(client, project, constraint, body, "constraints")
    assert saved.status_code == 200
    url = endpoint(project, "constraints") + "/" + constraint["id"]
    assert client.post(url + "/versions", headers={"If-Match": '"2"'}).status_code == 422
    body["items"][0]["basis"] = "Explicit engineering fixture quota; not a policy default"
    saved = save(client, project, saved.json(), body, "constraints")
    assert client.post(url + "/versions", headers={"If-Match": '"3"'}).status_code == 201
    decision = new(client, project, "decisions")
    response = save(
        client,
        project,
        decision,
        {"template": "RestorationPlanning", "actions": ["restore"]},
        "decisions",
    )
    assert response.status_code == 200
    response = client.post(
        endpoint(project, "decisions") + "/" + decision["id"] + "/versions",
        headers={"If-Match": '"2"'},
    )
    assert response.status_code == 201, response.text
    assert response.json()["body"]["template"] == "RestorationPlanning"
    assert save(client, project, decision, {"items": []}, "decisions").status_code in {404, 422}


def test_apply_is_explicit_versioned_and_does_not_upgrade(workspace):
    _, _, client, project = workspace
    item = new(client, project)
    body = {"mode": "single_objective", "items": [{"metric": "maximize_restoration_gain"}]}
    item = save(client, project, item, body).json()
    version = client.post(
        endpoint(project) + "/" + item["id"] + "/versions", headers={"If-Match": '"2"'}
    ).json()
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "Plan", "task_type": "planning"}
    ).json()
    applied = client.post(
        "/api/v1/tasks/" + task["id"] + "/planning/bindings",
        headers={"If-Match": f'"{task["revision"]}"'},
        json={"kind": "objectives", "object_id": item["id"], "version_id": version["id"]},
    )
    assert applied.status_code == 200, applied.text
    fixed = applied.json()["draft"]["options"]["planning_refs"]["objectives"]
    assert fixed["sha256"] == version["sha256"]
    # Browsing and publishing version 2 do not write to the task.
    before = client.get("/api/tasks/" + task["id"]).json()
    changed = save(
        client,
        project,
        item,
        {"mode": "single_objective", "items": [{"metric": "minimize_construction_cost"}]},
    ).json()
    assert (
        client.post(
            endpoint(project) + "/" + item["id"] + "/versions",
            headers={"If-Match": f'"{changed["revision"]}"'},
        ).status_code
        == 201
    )
    assert client.get("/api/tasks/" + task["id"]).json() == before


def test_real_metric_and_constraint_compilation_respects_units_and_domains():
    from coastmas_next.planning_recipes import compile_constraints, objective_values

    units = [
        {
            "id": "a",
            "area_m2": 10.0,
            "construction_cost": 2.0,
            "restoration_gain": 4.0,
            "forbidden": False,
        },
        {
            "id": "b",
            "area_m2": 20.0,
            "construction_cost": 5.0,
            "restoration_gain": 8.0,
            "forbidden": True,
        },
    ]
    decision = {"template": "RestorationPlanning", "actions": ["restore"]}
    values = objective_values(
        {
            "mode": "pareto_multiobjective",
            "items": [
                {"metric": "minimize_construction_cost"},
                {"metric": "maximize_restoration_gain"},
            ],
        },
        units,
        decision,
    )
    assert values == {
        "minimize_construction_cost": [2.0, 5.0],
        "maximize_restoration_gain": [4.0, 8.0],
    }
    constraints = compile_constraints(
        {
            "items": [
                {"recipe": "development_quota", "limit": 0.002, "unit": "ha", "basis": "fixture"},
                {"recipe": "ecological_redline_exclusion", "basis": "fixture"},
            ]
        },
        units,
    )
    assert constraints[0]["coefficients"] == [10.0, 20.0] and constraints[0]["upper"] == 20.0
    assert constraints[1]["upper_bounds"] == [1, 0]
    from coastmas_next.store import Problem

    with pytest.raises(Problem):
        objective_values(
            {"mode": "single_objective", "items": [{"metric": "maximize_restoration_gain"}]},
            units,
            {"template": "FacilityLocation", "actions": ["select_site"]},
        )
    with pytest.raises(Problem):
        compile_constraints(
            {
                "items": [
                    {"recipe": "development_quota", "limit": 3.0, "unit": "m", "basis": "fixture"}
                ]
            },
            units,
        )
    with pytest.raises(Problem):
        objective_values(
            {"mode": "single_objective", "items": [{"metric": "minimize_construction_cost"}]},
            [{"id": "missing"}],
            decision,
        )


def test_simultaneous_writers_cannot_lose_updates(workspace):
    from fastapi.testclient import TestClient

    from coastmas_next.app import create_app

    settings, _, client, project = workspace
    item = new(client, project)

    def write(name):
        other = TestClient(create_app(settings))
        other.cookies.update(client.cookies)
        other.headers.update(client.headers)
        return other.put(
            endpoint(project) + "/" + item["id"],
            headers={"If-Match": '"1"'},
            json={"name": name, "body": item["body"]},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, ["first", "second"])) == [200, 412]


def test_project_and_task_binding_guards(workspace):
    _, store, client, project = workspace
    item = new(client, project)
    item = save(
        client,
        project,
        item,
        {"mode": "single_objective", "items": [{"metric": "minimize_construction_cost"}]},
    ).json()
    version = client.post(
        endpoint(project) + "/" + item["id"] + "/versions", headers={"If-Match": '"2"'}
    ).json()
    other = store.create_project(client.get("/api/session").json()["id"], "Other project")
    task = client.post(
        "/api/tasks", json={"project_id": other, "title": "Plan elsewhere", "task_type": "planning"}
    ).json()
    binding = {"kind": "objectives", "object_id": item["id"], "version_id": version["id"]}
    response = client.post(
        "/api/v1/tasks/" + task["id"] + "/planning/bindings",
        headers={"If-Match": '"1"'},
        json=binding,
    )
    assert response.status_code == 404
    assessment = client.post(
        "/api/tasks", json={"project_id": project, "title": "Assessment", "task_type": "assessment"}
    ).json()
    response = client.post(
        "/api/v1/tasks/" + assessment["id"] + "/planning/bindings",
        headers={"If-Match": '"1"'},
        json=binding,
    )
    assert response.status_code == 422


def test_pareto_does_not_require_or_ignore_weights(workspace):
    _, _, client, project = workspace
    item = new(client, project)
    body = {
        "mode": "pareto_multiobjective",
        "items": [
            {"metric": "minimize_construction_cost"},
            {"metric": "maximize_restoration_gain"},
        ],
    }
    item = save(client, project, item, body).json()
    url = endpoint(project) + "/" + item["id"] + "/versions"
    assert client.post(url, headers={"If-Match": '"2"'}).status_code == 201
    body["items"][0]["weight"] = 0.5
    item = save(client, project, item, body).json()
    assert client.post(url, headers={"If-Match": '"3"'}).status_code == 422


def test_new_planning_reports_engineering_gap_not_a_legacy_method_request(workspace):
    _, _, client, project = workspace
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "New planning", "task_type": "planning"}
    ).json()
    check = client.get("/api/tasks/" + task["id"] + "/preflight").json()
    codes = {i["code"] for i in check["issues"]}
    assert "PLANNING_COMPILER_NOT_READY" in codes
    assert "METHOD_REQUIRED" not in codes
    assert check["ready"] is False
    response = client.post(
        "/api/tasks/" + task["id"] + "/execute",
        json={
            "expected_revision": task["revision"],
            "idempotency_key": "cannot-run-legacy-for-new-planning",
        },
    )
    assert response.status_code == 422


def test_binding_race_uses_same_412_contract(workspace, monkeypatch):
    _, _, client, project = workspace
    item = new(client, project)
    item = save(
        client,
        project,
        item,
        {"mode": "single_objective", "items": [{"metric": "minimize_construction_cost"}]},
    ).json()
    version = client.post(
        endpoint(project) + "/" + item["id"] + "/versions", headers={"If-Match": '"2"'}
    ).json()
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "Race", "task_type": "planning"}
    ).json()
    # Exercise the actual CAS failure at persistence, after the endpoint's read.
    from coastmas_next.store import Store

    original = Store.save_task

    def concurrent_update(self, actor, id, revision, draft, connection=None):
        if id == task["id"]:
            original(self, actor, id, revision, draft, connection)
        return original(self, actor, id, revision, draft, connection)

    monkeypatch.setattr(Store, "save_task", concurrent_update)
    response = client.post(
        "/api/v1/tasks/" + task["id"] + "/planning/bindings",
        headers={"If-Match": '"1"'},
        json={"kind": "objectives", "object_id": item["id"], "version_id": version["id"]},
    )
    assert response.status_code == 412
