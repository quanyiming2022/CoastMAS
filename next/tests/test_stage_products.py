"""Computed inputs remain task-scoped and reusable without another upload."""

from test_preparation_steps import execute, raster, research


def test_ndvi_stage_is_managed_and_reused_without_mutating_original_draft(workspace):
    settings, store, client, project = workspace
    asset = raster(client, project, [[[1, 2]], [[3, 2]]])
    task = research(client, project, [asset])
    execute(
        client,
        store,
        task,
        asset,
        "ndvi",
        {"red_band": 1, "nir_band": 2, "qa_policy": "source_mask"},
    )
    response = client.get(f"/api/tasks/{task['id']}/stage-products")
    assert response.status_code == 200, response.text
    products = response.json()
    assert len(products) == 1 and products[0]["applicable"] is True
    product = products[0]
    assert product["concept"] == "NDVI" and product["role"] == "raw_indicator"
    registered = client.get("/api/assets/" + product["asset_id"]).json()
    assert registered["facts"]["lineage"]["job_id"] == product["job_id"]
    assert client.get("/api/tasks/" + task["id"]).json() == task
    # Changing unrelated weights does not invalidate the raw indicator.
    draft = task["draft"]
    draft["options"]["unrelated_weight_trial"] = [1]
    saved = client.put(
        "/api/tasks/" + task["id"], json={"expected_revision": task["revision"], "draft": draft}
    ).json()
    assert client.get(f"/api/tasks/{task['id']}/stage-products").json()[0]["applicable"] is True
    # A different band recipe must not reuse the previous output.
    draft["options"]["preparation"] = {
        "ndvi": {"asset_id": asset["id"], "red_band": 2, "nir_band": 1, "qa_policy": "source_mask"}
    }
    client.put(
        "/api/tasks/" + task["id"], json={"expected_revision": saved["revision"], "draft": draft}
    )
    assert client.get(f"/api/tasks/{task['id']}/stage-products").json()[0]["applicable"] is False


def test_produced_indicator_flows_into_real_assessment_and_old_run_stays_fixed(workspace):
    import numpy as np
    import rasterio

    from coastmas_next.worker import Worker

    settings, store, client, project = workspace
    original = raster(client, project, [[[1, 2]], [[3, 2]]])
    task = research(client, project, [original])
    produced = execute(
        client,
        store,
        task,
        original,
        "ndvi",
        {"red_band": 1, "nir_band": 2, "qa_policy": "source_mask"},
    )
    method = client.post(
        f"/api/projects/{project}/templates",
        json={
            "title": "工程夹具 NDVI 分数，非业务结论",
            "purpose": "method",
            "profiles": ["geotiff"],
            "basis": "独立工程夹具：NDVI [-1,1] 线性正向，权重1",
            "configuration": {
                "task": "assessment",
                "method": "weighted",
                "indicators": [
                    {
                        "concept": "NDVI",
                        "unit": "1",
                        "lower": -1.0,
                        "upper": 1.0,
                        "positive": True,
                        "weight": 1.0,
                    }
                ],
            },
        },
    ).json()
    assert (
        client.post(f"/api/templates/{method['id']}/approve", json={"revision": 1}).status_code
        == 200
    )
    task = client.post(
        f"/api/tasks/{task['id']}/apply-method",
        json={
            "expected_revision": task["revision"],
            "method_id": method["id"],
            "method_revision": 1,
        },
    ).json()
    check = client.get(f"/api/tasks/{task['id']}/preflight")
    assert check.json()["ready"], check.text
    run = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "composite"},
    )
    assert run.status_code == 202, run.text
    assert Worker(store).run_once()
    result = client.get(f"/api/jobs/{run.json()['id']}/result").json()
    with rasterio.open(settings.storage_root / result["data"]["files"][0]["key"]) as ds:
        np.testing.assert_allclose(ds.read(1), [[0.75, 0.5]])
    assert result["manifest"]["draft"]["options"]["stage_products"][0]["concept"] == "NDVI"
    assert len(client.get("/api/tasks/" + task["id"]).json()["draft"]["selection"]) == 1
    # Removing the raw input invalidates derived reuse, not the historical output.
    task["draft"]["selection"] = []
    task["draft"]["mapping"] = []
    client.put(
        "/api/tasks/" + task["id"],
        json={"expected_revision": task["revision"], "draft": task["draft"]},
    )
    assert not client.get(f"/api/tasks/{task['id']}/stage-products").json()[0]["applicable"]
    assert client.get(f"/api/jobs/{run.json()['id']}/result").json() == result
    assert produced["statistics"]["valid_pixels"] == 2


def test_independent_scoring_consumes_produced_indicator_with_actual_mask(workspace):
    import numpy as np
    import rasterio

    settings, store, client, project = workspace
    original = raster(client, project, [[[1, 2, 0]], [[3, 2, 0]]])
    task = research(client, project, [original])
    execute(
        client,
        store,
        task,
        original,
        "ndvi",
        {"red_band": 1, "nir_band": 2, "qa_policy": "source_mask"},
    )
    product = client.get(f"/api/tasks/{task['id']}/stage-products").json()[0]
    result = execute(
        client,
        store,
        task,
        {"id": product["asset_id"]},
        "score",
        {
            "concept": "NDVI",
            "unit": "1",
            "lower": -1.0,
            "upper": 1.0,
            "positive": True,
            "missing_policy": "preserve_mask",
            "basis": "工程夹具明确参考范围，非正式业务评分",
        },
    )
    with rasterio.open(settings.storage_root / result["files"][0]["key"]) as ds:
        values = ds.read(1, masked=True)
        np.testing.assert_allclose(values.compressed(), [0.75, 0.5])
        assert values.mask.tolist() == [[False, False, True]]
    products = client.get(f"/api/tasks/{task['id']}/stage-products").json()
    assert len(products) == 2 and all(p["applicable"] for p in products)
    assert {p["role"] for p in products} == {"raw_indicator", "indicator"}
