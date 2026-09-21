from sqlalchemy.orm import Session

from coastmas.persistence.schema import Membership
from tests.factories import model


def test_project_archive_hides_ui_records_without_deleting_history(authenticated, engine):
    client, csrf, project, owner = authenticated
    headers = {"X-CSRF-Token": csrf}
    created = client.post(
        "/api/v1/models",
        headers=headers,
        json={
            "project_id": project,
            "spec": model(
                id="archive-model",
                validation_status="UNVALIDATED",
                execution_status="NOT_EXECUTABLE",
            ).model_dump(mode="json"),
        },
    )
    assert created.status_code == 201, created.text
    url = f"/api/v1/projects/{project}/archive"
    assert client.post(url, headers=headers, json={"archived": True}).status_code == 403
    with Session(engine) as session, session.begin():
        session.get(Membership, (project, owner)).role = "ADMIN"
    archived = client.post(url, headers=headers, json={"archived": True})
    assert archived.status_code == 200, archived.text
    assert all(item["id"] != project for item in client.get("/api/v1/projects").json())
    history = client.get("/api/v1/projects?include_archived=true")
    assert next(item for item in history.json() if item["id"] == project)["archived"] is True
    saved = client.get("/api/v1/models/archive-model?version=1")
    assert saved.status_code == 200
    assert saved.json()["checksum"] == created.json()["checksum"]
    restored = client.post(url, headers=headers, json={"archived": False})
    assert restored.status_code == 200, restored.text
    assert any(item["id"] == project for item in client.get("/api/v1/projects").json())
    audit = client.get("/api/v1/admin/audit", params={"project_id": project})
    assert [
        item["new_value"]["archived"]
        for item in audit.json()
        if item["action"] == "ARCHIVE_PROJECT"
    ] == [False, True]
