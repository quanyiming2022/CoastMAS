from uuid import uuid4

from coastmas.adapters.source_connectors import HTTPSource
from coastmas.adapters.source_registry import RegisteredSource
from tests.factories import asset, variable
from tests.integration.test_source_connectors import source_server as source_server


def test_registered_source_import_has_fixed_lineage_and_idempotent_snapshot(
    authenticated, storage, source_server
):
    client, csrf, project, _ = authenticated
    client.app.state.artifact_store = storage
    client.app.state.source_registry = {
        "test-http": RegisteredSource(
            label="Synthetic HTTP",
            projects=frozenset({project}),
            revision=1,
            source=HTTPSource(url=source_server + "/data", allow_private=True),
        )
    }
    output = asset(
        name="Source snapshot", format="CSV", type="table", variables=[variable(data_type="array")]
    ).model_dump(mode="json")
    for key in ("id", "version", "uri", "checksum", "quality"):
        output.pop(key)
    identifier = uuid4().hex
    spec = {
        "id": identifier,
        "name": "Registered source",
        "version": 1,
        "connector_id": "test-http",
        "kind": "http",
        "output": output,
    }
    headers = {"X-CSRF-Token": csrf}
    registered = client.post(
        "/api/v1/data-sources", headers=headers, json={"project_id": project, "spec": spec}
    )
    assert registered.status_code == 201, registered.text
    request = {"expected_version": 1, "idempotency_key": "same-import"}
    imported = client.post(
        f"/api/v1/data-sources/{identifier}/snapshots", headers=headers, json=request
    )
    assert imported.status_code == 201, imported.text
    data = imported.json()["spec"]
    assert data["quality"]["validated"] is True
    assert data["quality"]["row_count"] == 2
    repeated = client.post(
        f"/api/v1/data-sources/{identifier}/snapshots", headers=headers, json=request
    )
    assert repeated.json() == imported.json()
    assert (
        client.get(f"/api/v1/data-assets/{data['id']}/download").content
        == b"height,label\n0,zero\n2,two\n"
    )
    lineage = client.get(f"/api/v1/data-sources/for-asset/{data['id']}")
    assert lineage.status_code == 200
    assert [(row["resource_id"], row["version"]) for row in lineage.json()] == [(identifier, 1)]
    updated = client.post(
        f"/api/v1/data-assets/{data['id']}/validate", headers=headers, json={"expected_version": 1}
    )
    assert updated.status_code == 200
    assert (
        client.get(f"/api/v1/data-sources/for-asset/{data['id']}?version=2").json()
        == lineage.json()
    )
    blocked = client.delete(f"/api/v1/data-sources/{identifier}", headers=headers)
    assert blocked.status_code == 409
    unknown = {**spec, "id": uuid4().hex, "connector_id": "not-approved"}
    denied = client.post(
        "/api/v1/data-sources", headers=headers, json={"project_id": project, "spec": unknown}
    )
    assert denied.status_code == 422
    allowed = client.get("/api/v1/data-sources/connectors", params={"project_id": project})
    assert allowed.status_code == 200
    assert allowed.json() == [
        {"id": "test-http", "name": "Synthetic HTTP", "kind": "http", "revision": 1}
    ]
    assert source_server not in allowed.text


def test_database_source_api_import_and_project_scope(authenticated, storage, engine):
    from sqlalchemy import text

    from coastmas.adapters.source_connectors import PostgreSQLSource

    client, csrf, project, _ = authenticated
    client.app.state.artifact_store = storage
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE approved_observations (id integer primary key, height numeric)")
        )
        connection.execute(text("INSERT INTO approved_observations VALUES (2, 2.25), (1, 0)"))
    connector = PostgreSQLSource(
        dsn=engine.url.render_as_string(hide_password=False),
        schema="public",
        table="approved_observations",
        columns=("id", "height"),
        order_by=("id",),
    )
    client.app.state.source_registry = {
        "database": RegisteredSource(
            label="Approved table", projects=frozenset({project}), revision=1, source=connector
        ),
        "other-project": RegisteredSource(
            label="Other table", projects=frozenset({str(uuid4())}), revision=1, source=connector
        ),
    }
    output = asset(
        name="Database measurements",
        type="table",
        format="CSV",
        variables=[variable(data_type="array")],
    ).model_dump(mode="json")
    for key in ("id", "version", "uri", "checksum", "quality"):
        output.pop(key)
    identifier = uuid4().hex
    spec = {
        "id": identifier,
        "name": "Registered database",
        "version": 1,
        "connector_id": "database",
        "kind": "postgresql",
        "output": output,
    }
    headers = {"X-CSRF-Token": csrf}
    registered = client.post(
        "/api/v1/data-sources", headers=headers, json={"project_id": project, "spec": spec}
    )
    assert registered.status_code == 201, registered.text
    imported = client.post(
        f"/api/v1/data-sources/{identifier}/snapshots",
        headers=headers,
        json={"expected_version": 1, "idempotency_key": "postgres-snapshot"},
    )
    assert imported.status_code == 201, imported.text
    data = imported.json()["spec"]
    assert (
        client.get(f"/api/v1/data-assets/{data['id']}/download").content
        == b"id,height\n1,0\n2,2.25\n"
    )
    conflict = client.post(
        f"/api/v1/data-sources/{identifier}/snapshots",
        headers=headers,
        json={"expected_version": 2, "idempotency_key": "postgres-snapshot"},
    )
    assert conflict.status_code == 409
    denied = client.post(
        "/api/v1/data-sources",
        headers=headers,
        json={
            "project_id": project,
            "spec": {**spec, "id": uuid4().hex, "connector_id": "other-project"},
        },
    )
    assert denied.status_code == 403
    available = client.get("/api/v1/data-sources/connectors", params={"project_id": project}).json()
    assert [item["id"] for item in available] == ["database"]
