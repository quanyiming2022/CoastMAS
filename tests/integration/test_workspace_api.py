from uuid import uuid4

from sqlalchemy.orm import Session

from coastmas.persistence.schema import User


def test_project_listing_and_dashboard_are_scoped_and_computed(authenticated, actors):
    client, csrf, project, owner = authenticated
    projects = client.get("/api/v1/projects")
    assert projects.status_code == 200, projects.text
    assert any(item["id"] == project for item in projects.json())
    dashboard = client.get("/api/v1/dashboard", params={"project_id": project})
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["counts"]["models"] == 0
    denied = client.get("/api/v1/dashboard", params={"project_id": str(uuid4())})
    assert denied.status_code == 403
    users = client.get("/api/v1/admin/users")
    assert users.status_code == 403


def test_admin_can_manage_users_memberships_and_audit_without_secret_exposure(
    authenticated,
    engine,
    actors,
):
    client, csrf, project, owner = authenticated
    with Session(engine) as session, session.begin():
        session.get(User, owner).is_admin = True
    headers = {"X-CSRF-Token": csrf}
    email = uuid4().hex + "@managed.test.invalid"
    password = "managed-test-password"
    created = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": email,
            "password": password,
        },
    )
    assert created.status_code == 201, created.text
    identifier = created.json()["id"]
    assert password not in created.text and "password_hash" not in created.text
    added = client.put(
        f"/api/v1/projects/{project}/members/{identifier}", headers=headers, json={"role": "VIEWER"}
    )
    assert added.status_code == 200, added.text
    members = client.get(f"/api/v1/projects/{project}/members")
    assert any(
        item["user_id"] == identifier and item["role"] == "VIEWER" for item in members.json()
    )
    disabled = client.patch(
        "/api/v1/admin/users/" + identifier, headers=headers, json={"active": False}
    )
    assert disabled.status_code == 200, disabled.text
    forbidden = client.patch(
        "/api/v1/admin/users/" + owner, headers=headers, json={"active": False}
    )
    assert forbidden.status_code == 422
    assert forbidden.json()["error_code"] == "LAST_ADMIN"
    audit = client.get("/api/v1/admin/audit", params={"project_id": project})
    assert audit.status_code == 200
    assert any(item["action"] == "SET_MEMBER" for item in audit.json())
    assert password not in audit.text and "password_hash" not in audit.text


def test_resource_lists_return_bounded_pages_and_safe_summary(authenticated):
    from tests.factories import model

    client, csrf, project, _ = authenticated
    for index in range(2):
        spec = model(
            id="listed-" + uuid4().hex,
            name=f"Model {index}",
            validation_status="UNVALIDATED",
            execution_status="NOT_EXECUTABLE",
        )
        response = client.post(
            "/api/v1/models",
            headers={"X-CSRF-Token": csrf},
            json={"project_id": project, "spec": spec.model_dump(mode="json")},
        )
        assert response.status_code == 201, response.text
    response = client.get("/api/v1/models", params={"project_id": project, "limit": 1, "offset": 1})
    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "2"
    assert len(response.json()) == 1 and response.json()[0]["name"] == "Model 1"
    assert response.json()[0]["summary"]["model_type"] == "RASTER"
    assert "runtime_config" not in response.json()[0]["summary"]


def test_builtin_enable_lifecycle_preserves_existing_runtime_evidence(authenticated, engine):
    from pathlib import Path

    from coastmas.domain.builtin_catalog import assessment_catalog
    from coastmas.persistence.resources import create_resource
    from coastmas.runtime_bootstrap import BuiltinRuntimeRegistry

    client, csrf, project, owner = authenticated
    model = assessment_catalog(project).models[0]
    with Session(engine) as session, session.begin():
        create_resource(
            session,
            user_id=owner,
            project_id=project,
            kind="model",
            identifier=model.id,
            name=model.name,
            spec=model.model_dump(mode="json"),
        )
    client.app.state.registry = BuiltinRuntimeRegistry(Path("sample-data"))
    for version, enabled in [(1, False), (2, True)]:
        response = client.post(
            "/api/v1/models/" + model.id + "/enabled",
            headers={"X-CSRF-Token": csrf},
            json={"expected_version": version, "enabled": enabled},
        )
        assert response.status_code == 200, response.text
        assert response.json()["spec"]["validation_status"] == "VALIDATED"
        assert response.json()["spec"]["execution_status"] == "EXECUTABLE"
    dashboard = client.get("/api/v1/dashboard", params={"project_id": project})
    assert dashboard.json()["counts"]["executable_models"] == 1
