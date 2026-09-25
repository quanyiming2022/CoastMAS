import json

from tests.integration.test_ingestion_api import raster_file


def test_preparation_creates_versioned_model_input_without_manual_json(
    authenticated, storage, tmp_path
):
    client, csrf, project, _ = authenticated
    client.app.state.artifact_store = storage
    headers = {"X-CSRF-Token": csrf}
    uploaded = client.post(
        "/api/v1/data-assets/ingest",
        headers=headers,
        data={
            "project_id": project,
            "declaration": json.dumps({"name": "source", "source": "test", "license": "test"}),
        },
        files={"file": ("source.tif", raster_file(tmp_path / "source.tif"), "image/tiff")},
    )
    source = uploaded.json()["spec"]
    response = client.post(
        "/api/v1/data-assets/prepare-raster-frame",
        headers=headers,
        json={
            "project_id": project,
            "name": "analysis observations",
            "features": [
                {
                    "asset_id": source["id"],
                    "version": 1,
                    "name": "declared_feature",
                    "unit": "1",
                    "band": 1,
                }
            ],
            "options": {"mode": "all", "standardize": False},
        },
    )
    assert response.status_code == 201, response.text
    prepared = response.json()["spec"]
    assert prepared["quality"]["lineage"][0]["checksum"] == source["checksum"]
    assert prepared["quality"]["business_validated"] is False
    assert prepared["time_start"] is None
    assert prepared["variables"][0]["standard_name"] == "projection_pursuit_frame"
    downloaded = client.get(f"/api/v1/data-assets/{prepared['id']}/download").json()
    assert downloaded["frame"]["values"] == [[0], [-1], [2], [1], [0]]
    assert downloaded["frame"]["row_ids"] == ["r0c0", "r0c1", "r0c2", "r1c1", "r1c2"]
    assert len(downloaded["locations"]) == 5

    from tests.unit.test_indicator_framework import framework

    definition = framework(spatial_support="grid").model_dump(mode="json")
    indicator = definition["indicators"][0]
    indicator.update(unit="1", source={"x": "declared_feature"})
    indicator["normalization"].update(lower=-1, upper=2)
    definition["indicators"] = [indicator]
    created = client.post(
        "/api/v1/indicator-frameworks",
        headers=headers,
        json={"project_id": project, "spec": definition},
    )
    assert created.status_code == 201, created.text
    evaluation = client.post(
        f"/api/v1/indicator-frameworks/{definition['id']}/prepare",
        headers=headers,
        json={
            "expected_version": 1,
            "data": {"id": prepared["id"], "version": 1},
            "idempotency_key": "real-raster-frame",
        },
    )
    assert evaluation.status_code == 201, evaluation.text
    assessed = evaluation.json()["spec"]
    assert assessed["variables"][0]["standard_name"] == "indicator_frame"
    assert assessed["quality"]["scope"] == "all_joint_valid_cells"
    assert assessed["quality"]["business_validated"] is False
    assessment_input = client.get(f"/api/v1/data-assets/{assessed['id']}/download").json()
    assert assessment_input["frame"]["values"] == [[0], [-1], [2], [1], [0]]
    assert assessment_input["locations"] == downloaded["locations"]
