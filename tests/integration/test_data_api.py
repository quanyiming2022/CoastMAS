import hashlib
from uuid import uuid4

from tests.factories import asset, variable


def test_upload_reads_real_csv_and_validates_versioned_catalog(authenticated, storage):
    client, csrf, project, _ = authenticated
    client.app.state.artifact_store = storage
    content = b"height,label\n1,a\n2,b\n"
    source = asset(
        id=uuid4().hex, format="CSV", type="table", variables=[variable(data_type="array")]
    )
    headers = {"X-CSRF-Token": csrf}
    response = client.post(
        "/api/v1/data-assets/upload",
        headers=headers,
        data={"project_id": project, "metadata": source.model_dump_json()},
        files={"file": ("../../untrusted.csv", content, "text/csv")},
    )
    assert response.status_code == 201, response.text
    spec = response.json()["spec"]
    assert spec["checksum"] == hashlib.sha256(content).hexdigest()
    assert spec["quality"]["validated"] is True
    assert "untrusted.csv" not in spec["uri"]
    assert spec["quality"]["row_count"] == 2
    preview = client.get(f"/api/v1/data-assets/{source.id}/preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["preview"]["rows"][0]["height"] == "1"
    checked = client.post(
        f"/api/v1/data-assets/{source.id}/validate", headers=headers, json={"expected_version": 1}
    )
    assert checked.status_code == 200, checked.text
    assert checked.json()["version"] == 2
    assert client.get(f"/api/v1/data-assets/{source.id}", params={"version": 1}).status_code == 200


def test_catalog_metadata_cannot_self_certify_quality(authenticated):
    client, csrf, project, _ = authenticated
    source = asset(id=uuid4().hex)
    response = client.post(
        "/api/v1/data-assets",
        headers={"X-CSRF-Token": csrf},
        json={"project_id": project, "spec": source.model_dump(mode="json")},
    )
    assert response.status_code == 201
    assert response.json()["spec"]["quality"]["validated"] is False


def test_corrupt_upload_does_not_create_catalog_resource(authenticated, storage):
    client, csrf, project, _ = authenticated
    client.app.state.artifact_store = storage
    source = asset(id=uuid4().hex)
    response = client.post(
        "/api/v1/data-assets/upload",
        headers={"X-CSRF-Token": csrf},
        data={"project_id": project, "metadata": source.model_dump_json()},
        files={"file": ("fake.tif", b"not-a-raster", "image/tiff")},
    )
    assert response.status_code == 422
    assert client.get(f"/api/v1/data-assets/{source.id}").status_code == 404
