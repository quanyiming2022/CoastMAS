"""Planning units are full managed observations, not a policy or evaluation result."""

import copy
import hashlib
import json

import pytest
from pyproj import Geod
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from coastmas_next.worker import Worker


def polygons():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": name,
                "properties": {"cost": cost},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[x, 22], [x + 0.001, 22], [x + 0.001, 22.001], [x, 22.001], [x, 22]]
                    ],
                },
            }
            for name, x, cost in [("a", 113.0, 2), ("b", 113.001, 5)]
        ],
    }


def setup(client, project, content=None, name="engineering-units.geojson"):
    payload = json.dumps(content or polygons()).encode()
    uploaded = client.post(f"/api/projects/{project}/assets", files={"file": (name, payload)})
    assert uploaded.status_code == 201, uploaded.text
    asset = uploaded.json()["asset"]
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Engineering units", "task_type": "planning"},
    ).json()
    attached = client.post(
        f"/api/tasks/{task['id']}/inputs:attach",
        json={
            "expected_revision": task["revision"],
            "idempotency_key": "input",
            "inputs": [{"asset_id": asset["id"], "revision": asset["revision"]}],
        },
    )
    assert attached.status_code == 200, attached.text
    return asset, attached.json()["task"]


def enqueue(client, task, asset, key="units", parameters=None):
    response = client.post(
        f"/api/tasks/{task['id']}/processing-nodes",
        json={
            "expected_revision": task["revision"],
            "asset_id": asset["id"],
            "operator": "planning_units",
            "parameters": parameters or {},
            "idempotency_key": key,
        },
    )
    assert response.status_code == 201, response.text
    response = client.post(
        f"/api/processing-nodes/{response.json()['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": key},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_native_polygon_units_actual_area_artifacts_versions_and_no_draft_mutation(workspace):
    settings, store, client, project = workspace
    asset, task = setup(client, project)
    before = copy.deepcopy(task)
    job = enqueue(client, task, asset)
    assert job["status"] == "queued"
    assert client.get(f"/api/v1/tasks/{task['id']}/planning/units").json() == []
    assert Worker(store).run_once()
    response = client.get(f"/api/jobs/{job['id']}/result")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    descriptor = client.get(f"/api/jobs/{job['id']}/descriptor")
    assert descriptor.status_code == 200, descriptor.text
    assert descriptor.json()["statistics"] is None
    assert descriptor.json()["vector_statistics"]["unit_count"] == 2
    assert data["scope"] == "full_layer" and data["statistics"]["unit_count"] == 2
    assert data["statistics"]["overlap_check"] == "passed"
    units = data["units"]
    assert [r["id"] for r in units] == ["a", "b"]
    area, _ = Geod(ellps="WGS84").polygon_area_perimeter(
        [113, 113.001, 113.001, 113, 113], [22, 22, 22.001, 22.001, 22]
    )
    assert units[0]["area_m2"] == pytest.approx(abs(area), rel=1e-8)
    assert units[0]["properties"] == {"cost": 2}
    assert "construction_cost" not in units[0]  # names do not establish scientific meaning
    assert data["spatial_result"]["features"][0]["properties"]["area_m2"] == units[0]["area_m2"]
    for f in data["files"]:
        assert (
            hashlib.sha256((settings.storage_root / f["key"]).read_bytes()).hexdigest()
            == f["sha256"]
        )
    versions = client.get(f"/api/v1/tasks/{task['id']}/planning/units").json()
    assert len(versions) == 1 and versions[0]["applicable"] and versions[0]["version"] == 1
    assert versions[0]["job_id"] == job["id"] and versions[0]["source"]["sha256"] == asset["sha256"]
    assert versions[0]["algorithm_version"] == "1.0.0"
    assert client.get(f"/api/tasks/{task['id']}").json() == before
    assert client.get(f"/api/tasks/{task['id']}/jobs").json()["total"] == 1
    with store.engine.begin() as c:
        with pytest.raises(DBAPIError):
            c.execute(
                text("UPDATE planning_unit_set_revisions SET unit_count=0 WHERE id=:id"),
                {"id": versions[0]["id"]},
            )


@pytest.mark.parametrize("failure", ["overlap", "invalid", "mixed"])
def test_invalid_space_fails_without_publishing_or_partial_unit_set(workspace, failure):
    _, store, client, project = workspace
    content = polygons()
    if failure == "overlap":
        content["features"][1]["geometry"] = copy.deepcopy(content["features"][0]["geometry"])
    elif failure == "invalid":
        content["features"][1]["geometry"]["coordinates"] = [
            [[113, 22], [113.001, 22.001], [113.001, 22], [113, 22.001], [113, 22]]
        ]
    else:
        content["features"][1]["geometry"] = {"type": "Point", "coordinates": [113.001, 22]}
    asset, task = setup(client, project, content)
    job = enqueue(client, task, asset)
    assert Worker(store).run_once()
    result = client.get(f"/api/jobs/{job['id']}").json()
    assert result["status"] == "failed"
    assert (
        result["error"]["code"]
        == {
            "overlap": "UNIT_OVERLAP",
            "invalid": "UNIT_GEOMETRY_INVALID",
            "mixed": "UNIT_GEOMETRY_MIXED",
        }[failure]
    )
    assert client.get(f"/api/v1/tasks/{task['id']}/planning/units").json() == []


def test_points_have_no_invented_area_and_csv_needs_actual_coordinates(workspace):
    _, store, client, project = workspace
    content = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "site",
                "properties": {},
                "geometry": {"type": "Point", "coordinates": [113, 22]},
            }
        ],
    }
    asset, task = setup(client, project, content)
    job = enqueue(client, task, asset)
    assert Worker(store).run_once()
    data = client.get(f"/api/jobs/{job['id']}/result").json()["data"]
    assert data["units"][0]["area_m2"] is None and data["statistics"]["area_m2"] is None
    uploaded = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("no-location.csv", b"id,cost\na,2\nb,3\n")},
    ).json()["asset"]
    attached = client.post(
        f"/api/tasks/{task['id']}/inputs:attach",
        json={
            "expected_revision": task["revision"],
            "idempotency_key": "csv",
            "inputs": [{"asset_id": uploaded["id"], "revision": 1}],
        },
    ).json()["task"]
    node = client.post(
        f"/api/tasks/{task['id']}/processing-nodes",
        json={
            "expected_revision": attached["revision"],
            "asset_id": uploaded["id"],
            "operator": "planning_units",
            "idempotency_key": "csv",
        },
    )
    assert node.status_code == 201, node.text
    blocked = client.post(
        f"/api/processing-nodes/{node.json()['id']}/execute",
        json={"expected_revision": attached["revision"], "idempotency_key": "csv"},
    )
    assert blocked.status_code == 422 and "UNIT_LOCATION_REQUIRED" in blocked.text


def test_version_reuse_permissions_and_source_scope(workspace):
    _, store, client, project = workspace
    asset, task = setup(client, project)
    enqueue(client, task, asset)
    Worker(store).run_once()
    url = f"/api/v1/tasks/{task['id']}/planning/units"
    old = client.get(url).json()[0]
    task["draft"]["options"]["unrelated_weight_trial"] = [1]
    saved = client.put(
        f"/api/tasks/{task['id']}",
        json={"expected_revision": task["revision"], "draft": task["draft"]},
    ).json()
    assert client.get(url).json()[0]["applicable"]
    enqueue(client, saved, asset, key="new-version")
    Worker(store).run_once()
    current = client.get(url).json()
    assert [v["version"] for v in current] == [2, 1]
    assert current[1] == old
    saved["draft"]["selection"] = []
    saved["draft"]["mapping"] = []
    client.put(
        f"/api/tasks/{task['id']}",
        json={"expected_revision": saved["revision"], "draft": saved["draft"]},
    )
    assert all(not v["applicable"] for v in client.get(url).json())
    login = client.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    )
    client.headers["X-CSRF-Token"] = login.json()["csrf"]
    assert client.get(url).status_code == 200
    denied = client.post(
        f"/api/tasks/{task['id']}/processing-nodes",
        json={
            "expected_revision": saved["revision"],
            "asset_id": asset["id"],
            "operator": "planning_units",
            "idempotency_key": "viewer",
        },
    )
    assert denied.status_code == 403
    assert client.get("/api/v1/tasks/unavailable/planning/units").status_code == 404


def test_vector_download_and_view_feature_are_fixed_to_the_same_run(workspace):
    settings, store, client, project = workspace
    asset, task = setup(client, project)
    job = enqueue(client, task, asset)
    Worker(store).run_once()
    data = client.get(f"/api/jobs/{job['id']}/result").json()["data"]
    response = client.get(f"/api/jobs/{job['id']}/artifacts/1/download")
    assert response.status_code == 200
    assert hashlib.sha256(response.content).hexdigest() == data["files"][1]["sha256"]
    view = {
        "asset_id": None,
        "band": 1,
        "camera": None,
        "visible": True,
        "opacity": 0.6,
        "selected_feature_id": "a",
    }
    response = client.put(
        f"/api/jobs/{job['id']}/view-state", json={"expected_revision": 0, "state": view}
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"]["selected_feature_id"] == "a"
    view["selected_feature_id"] = "unrelated-run-feature"
    assert (
        client.put(
            f"/api/jobs/{job['id']}/view-state", json={"expected_revision": 1, "state": view}
        ).status_code
        == 422
    )
    artifact = settings.storage_root / data["files"][1]["key"]
    artifact.write_text(artifact.read_text().replace('"a"', '"z"'))
    assert client.get(f"/api/jobs/{job['id']}/artifacts/1/download").status_code == 409


def test_prepare_rejects_unapproved_hidden_parameters(workspace):
    _, _, client, project = workspace
    asset, task = setup(client, project)
    response = client.post(
        f"/api/tasks/{task['id']}/processing-nodes",
        json={
            "expected_revision": task["revision"],
            "asset_id": asset["id"],
            "operator": "planning_units",
            "parameters": {"ignore_overlap": True},
            "idempotency_key": "no-hidden-bypass",
        },
    )
    assert response.status_code == 422
    assert client.get(f"/api/tasks/{task['id']}/jobs").json()["total"] == 0


def test_preparation_budget_and_cancel_do_not_publish_partial_units(workspace, monkeypatch):
    from coastmas_next import planning_units

    settings, store, client, project = workspace
    asset, task = setup(client, project)
    monkeypatch.setattr(planning_units, "MAX_UNITS", 1)
    job = enqueue(client, task, asset)
    Worker(store).run_once()
    failed = client.get(f"/api/jobs/{job['id']}").json()
    assert failed["status"] == "failed" and failed["error"]["code"] == "OBSERVATION_BUDGET"
    assert client.get(f"/api/v1/tasks/{task['id']}/planning/units").json() == []
    monkeypatch.setattr(planning_units, "MAX_UNITS", 100000)
    job = enqueue(client, task, asset, key="cancel")
    client.post(f"/api/jobs/{job['id']}/cancel")
    Worker(store).run_once()
    assert client.get(f"/api/v1/tasks/{task['id']}/planning/units").json() == []


def test_removing_vector_from_map_preserves_input_and_immutable_unit_version(workspace):
    _, store, client, project = workspace
    asset, task = setup(client, project)
    job = enqueue(client, task, asset)
    Worker(store).run_once()
    url = f"/api/v1/tasks/{task['id']}/planning/units"
    before = client.get(url).json()
    response = client.put(
        f"/api/jobs/{job['id']}/view-state",
        json={
            "expected_revision": 0,
            "state": {
                "asset_id": None,
                "band": 1,
                "camera": None,
                "visible": True,
                "opacity": 0.9,
                "vector_present": False,
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"]["vector_present"] is False
    assert client.get(url).json() == before
    assert client.get(f"/api/tasks/{task['id']}").json() == task
