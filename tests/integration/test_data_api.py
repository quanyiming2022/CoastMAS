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


def test_data_history_download_and_archive_preserve_exact_bytes(authenticated, storage):
    client, csrf, project, _ = authenticated
    client.app.state.artifact_store = storage
    source = asset(
        id=uuid4().hex, format="CSV", type="table", variables=[variable(data_type="array")]
    )
    content = b"height,label\n0,zero\n2,two\n"
    headers = {"X-CSRF-Token": csrf}
    uploaded = client.post(
        "/api/v1/data-assets/upload",
        headers=headers,
        data={"project_id": project, "metadata": source.model_dump_json()},
        files={"file": ("data.csv", content, "text/csv")},
    )
    assert uploaded.status_code == 201, uploaded.text
    checked = client.post(
        f"/api/v1/data-assets/{source.id}/validate", headers=headers, json={"expected_version": 1}
    )
    assert checked.status_code == 200
    history = client.get(f"/api/v1/data-assets/{source.id}/versions")
    assert history.status_code == 200, history.text
    assert [row["version"] for row in history.json()] == [1, 2]
    downloaded = client.get(f"/api/v1/data-assets/{source.id}/download?version=1")
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == content
    assert downloaded.headers["cache-control"] == "no-store"
    archived = client.delete(f"/api/v1/data-assets/{source.id}", headers=headers)
    assert archived.status_code == 204, archived.text
    assert source.id not in [
        item["id"]
        for item in client.get("/api/v1/data-assets", params={"project_id": project}).json()
    ]
    assert client.get(f"/api/v1/data-assets/{source.id}/download?version=1").content == content


def test_data_download_cannot_use_forged_catalog_to_read_other_project(authenticated, storage):
    client, csrf, project, _ = authenticated
    client.app.state.artifact_store = storage
    content = b"height\n42\n"
    artifact = storage.put("another-project/data/private.csv", content)
    forged = asset(
        id=uuid4().hex,
        format="CSV",
        type="table",
        uri=artifact.uri,
        checksum=hashlib.sha256(content).hexdigest(),
        quality={"size_bytes": len(content)},
        variables=[variable(data_type="array")],
    )
    created = client.post(
        "/api/v1/data-assets",
        headers={"X-CSRF-Token": csrf},
        json={"project_id": project, "spec": forged.model_dump(mode="json")},
    )
    assert created.status_code == 201
    for action in ("download", "preview"):
        response = client.get(f"/api/v1/data-assets/{forged.id}/{action}")
        assert response.status_code == 403, response.text
