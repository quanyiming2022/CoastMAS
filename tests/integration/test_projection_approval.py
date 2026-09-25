import hashlib
import json

from sqlalchemy.orm import Session

from coastmas.persistence.schema import Membership


def test_only_project_admin_can_approve_verified_provided_model(
    authenticated, engine, monkeypatch, tmp_path
):
    client, csrf, project, user = authenticated
    # Verified technical release is deployment configuration, never supplied in the API body.
    release = tmp_path / "release.json"
    proof = json.dumps(
        {
            "image": "sha256:" + "a" * 64,
            "clustering_pair_disagreements": 0,
            "regression_max_abs_error": 0.0,
            "scope": "technical_iris_fixture_not_coastal_scientific_validation",
        }
    ).encode()
    release.with_suffix(".proof.json").write_bytes(proof)
    release.write_text(
        json.dumps(
            {
                "image": "sha256:" + "a" * 64,
                "proof_sha256": hashlib.sha256(proof).hexdigest(),
                "source_sha256": "c" * 64,
                "clustering_pair_disagreements": 0,
                "regression_max_abs_error": 0.0,
            }
        )
    )
    monkeypatch.setenv("COASTMAS_PROJECTION_RELEASE", str(release))
    headers = {"X-CSRF-Token": csrf}
    created = client.post(
        "/api/v1/models/provided-packages",
        headers=headers,
        json={"project_id": project, "method": "ppci_mcdc"},
    )
    assert created.status_code == 201, created.text
    listed = client.get("/api/v1/models/provided-packages", params={"project_id": project}).json()
    assert listed["can_register"] is True
    assert len(listed["models"]) == 2
    assert listed["models"][0]["registered"] is True
    assert listed["models"][0]["id"] == created.json()["spec"]["id"]
    assert listed["models"][1]["registered"] is False
    spec = created.json()["spec"]
    assert spec["execution_status"] == "NOT_EXECUTABLE"
    endpoint = f"/api/v1/models/{spec['id']}/approve-provided-runtime"
    denied = client.post(endpoint, headers=headers, json={"expected_version": 1})
    assert denied.status_code == 403
    with Session(engine) as session, session.begin():
        session.get(Membership, (project, user)).role = "ADMIN"
    approved = client.post(endpoint, headers=headers, json={"expected_version": 1})
    assert approved.status_code == 200, approved.text
    assert approved.json()["version"] == 2
    assert approved.json()["spec"]["execution_status"] == "EXECUTABLE"
    stale = client.post(endpoint, headers=headers, json={"expected_version": 1})
    assert stale.status_code == 409
    original = client.get(f"/api/v1/models/{spec['id']}?version=1").json()["spec"]
    assert original["execution_status"] == "NOT_EXECUTABLE"


def test_missing_runtime_is_visible_unavailability_not_internal_error(authenticated, monkeypatch):
    client, _, project, _ = authenticated
    monkeypatch.setenv("COASTMAS_PROJECTION_RELEASE", "")
    response = client.get("/api/v1/models/provided-packages", params={"project_id": project})
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["models"] == []
    assert "not configured" in response.json()["reason"]
