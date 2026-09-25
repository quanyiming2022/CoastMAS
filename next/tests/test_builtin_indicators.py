"""Public indicator use: no technical contract fields supplied by the analyst."""

import io
import json

import numpy as np
import rasterio
from rasterio.transform import from_origin
from test_preparation_steps import research

from coastmas_next.worker import Worker


def spectral(client, project, descriptions, values, tags=None, name="观测.tif"):
    values = np.array(values, dtype="float64")
    with rasterio.MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            width=values.shape[2],
            height=values.shape[1],
            count=len(values),
            dtype="float64",
            crs="EPSG:6933",
            transform=from_origin(400000, 2500000, 10, 10),
            nodata=-9999,
        ) as ds:
            ds.write(values)
            for i, role in enumerate(descriptions, 1):
                ds.set_band_description(i, role)
                ds.set_band_unit(i, "1")
                ds.update_tags(i, common_name=role, physical_quantity="surface_reflectance")
            if tags:
                ds.update_tags(**tags)
        payload = mem.read()
    response = client.post(
        f"/api/projects/{project}/assets", files={"file": (name, io.BytesIO(payload), "image/tiff")}
    )
    assert response.status_code == 201, response.text
    return response.json()["asset"]


def catalog(client, task):
    response = client.get(f"/api/v1/tasks/{task['id']}/indicators")
    assert response.status_code == 200, response.text
    return {r["indicator_id"]: r for r in response.json()["items"]}


def add(client, task, indicator_id, **extra):
    response = client.post(
        f"/api/v1/tasks/{task['id']}/indicators",
        json={
            "expected_revision": task["revision"],
            "idempotency_key": indicator_id,
            "items": [{"indicator_id": indicator_id, **extra}],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def execute(client, store, task, selection):
    response = client.post(
        f"/api/v1/tasks/{task['id']}/indicators/{selection}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "run-" + selection},
    )
    assert response.status_code == 202, response.text
    assert Worker(store).run_once()
    result = client.get(f"/api/jobs/{response.json()['id']}/result")
    assert result.status_code == 200, result.text
    return result.json()


def test_A_B_D_J_selection_autobinding_and_fixed_algorithm(workspace):
    settings, store, client, project = workspace
    red = spectral(client, project, ["red"], [[[0.2, 0.2]]])
    task = research(client, project, [red])
    ndvi = catalog(client, task)["indicator.ndvi"]
    assert ndvi["status"] == "missing" and ndvi["missing"] == ["近红外波段"]
    assert "schema" not in ndvi and "input_roles" not in ndvi
    image = spectral(client, project, ["red", "nir"], [[[0.2, 0, -9999]], [[0.6, 0, 0.8]]])
    # Library discovery is read-only until an explicit indicator selection.
    ndvi = catalog(client, task)["indicator.ndvi"]
    assert ndvi["status"] == "ready"
    assert len(client.get("/api/tasks/" + task["id"]).json()["draft"]["selection"]) == 1
    receipt = add(client, task, "indicator.ndvi")
    task = receipt["task"]
    selected = receipt["items"][0]
    assert selected["status"] == "ready"
    assert image["id"] in [r["asset_id"] for r in task["draft"]["selection"]]
    result = execute(client, store, task, selected["selection_id"])
    with rasterio.open(settings.storage_root / result["data"]["files"][0]["key"]) as ds:
        np.testing.assert_allclose(ds.read(1, masked=True).compressed(), [0.5], rtol=1e-12)
        assert ds.read(1, masked=True).mask.tolist() == [[False, True, True]]
    assert result["manifest"]["method"]["definition"]["algorithm_version"] == "spectral/1.0.0"
    assert result["manifest"]["method"]["definition"]["default_parameters_version"] == 1
    assert result["data"]["scope"] == "full_grid"
    assert client.get("/api/tasks/" + task["id"]).json() == task
    product = client.get(f"/api/tasks/{task['id']}/stage-products").json()[0]
    descriptor = client.get(f"/api/jobs/{product['job_id']}/descriptor").json()
    assert descriptor["statistics"] == {
        "scope": "full_grid", "total_pixels": 3, "valid_pixels": 1, "invalid_pixels": 2
    }
    assert descriptor["primary"]["sha256"] == result["data"]["files"][0]["sha256"]
    other = research(client, project, [client.get("/api/assets/" + product["asset_id"]).json()])
    reused = add(
        client, other, "indicator.ndvi", candidate_key="existing:" + product["asset_id"] + ":1"
    )
    assert reused["items"][0]["mode"] == "existing"
    assert reused["task"]["draft"]["mapping"][0]["concept"] == "NDVI"
    # Selecting never rewrites or reruns a historical manifest.
    before = json.dumps(result, sort_keys=True)
    assert (
        json.dumps(client.get("/api/jobs/" + product["job_id"] + "/result").json(), sort_keys=True)
        == before
    )


def test_unknown_rgb_does_not_guess_nir_or_allow_contract_injection(workspace):
    _, _, client, project = workspace
    image = spectral(client, project, ["red", "green", "blue"], [[[0.2]], [[0.3]], [[0.4]]])
    task = research(client, project, [image])
    item = catalog(client, task)["indicator.ndvi"]
    assert item["status"] == "missing" and item["missing"] == ["近红外波段"]
    r = client.post(
        f"/api/v1/tasks/{task['id']}/indicators",
        json={
            "expected_revision": task["revision"],
            "idempotency_key": "injection",
            "items": [{"indicator_id": "indicator.ndvi", "algorithm_entry": "evil.py"}],
        },
    )
    assert r.status_code == 422
    r = add(client, task, "indicator.ndvi")
    assert r["items"][0]["status"] == "missing"
    blocked = client.post(
        f"/api/v1/tasks/{task['id']}/indicators/{r['items'][0]['selection_id']}/execute",
        json={"expected_revision": r["task"]["revision"], "idempotency_key": "cannot-run"},
    )
    assert blocked.status_code == 422


def test_registry_published_entries_have_verified_runner_and_private_definition(workspace):
    from coastmas_next.indicator_registry import definitions, require_definition

    records = definitions()
    assert len(records) >= 62
    for item in records:
        if item["status"] == "published":
            assert item["tests"] and item["implementation_sha256"]
            assert require_definition(item["indicator_id"], item["version"]) == item
    _, _, client, project = workspace
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "goal": "comprehensive-assessment", "title": "Empty"},
    ).json()
    ui = catalog(client, task)
    assert ui["indicator.npp"]["status"] == "not_installed"
    assert ui["indicator.ndwi"]["name"].startswith("NDWI")
