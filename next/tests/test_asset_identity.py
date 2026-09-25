"""Different intake intentions preserve identity while bytes and scoped knowledge may be reused."""

import io

import pytest
from coastmas_next.intake import Intake, assets
from coastmas_next.store import Problem, Store, projects
from sqlalchemy import MetaData, UniqueConstraint, inspect, select
from sqlalchemy.schema import CreateTable


def test_different_intentions_share_only_physical_bytes(workspace):
    _, store, client, project = workspace
    raw = b"id,value\n001,0\n"
    first = client.post(
        f"/api/projects/{project}/assets", files={"file": ("source-a.csv", raw)}
    ).json()["asset"]
    second = client.post(
        f"/api/projects/{project}/assets", files={"file": ("source-b.csv", raw)}
    ).json()["asset"]
    assert first["id"] != second["id"]
    assert first["name"] == "source-a.csv" and second["name"] == "source-b.csv"
    assert first["sha256"] == second["sha256"]
    assert first["object_key"] == second["object_key"]
    assert len(client.get(f"/api/projects/{project}/catalog").json()["items"]) == 2
    with store.engine.connect() as connection:
        assert (
            len(connection.execute(select(assets).where(assets.c.project_id == project)).all()) == 2
        )


def test_retry_of_one_internal_intent_is_exact_and_payload_conflict_fails(workspace):
    _, store, client, project = workspace
    actor = client.get("/api/session").json()["id"]
    intake = Intake(store)
    original = intake.ingest(
        actor, project, io.BytesIO(b"id,v\n1,2"), "facts.csv", intent="batch:test-item"
    )
    replay = intake.ingest(
        actor, project, io.BytesIO(b"id,v\n1,2"), "facts.csv", intent="batch:test-item"
    )
    assert replay["asset"]["id"] == original["asset"]["id"]
    assert replay["replayed"] is True
    with pytest.raises(Problem) as problem:
        intake.ingest(
            actor, project, io.BytesIO(b"id,v\n1,3"), "facts.csv", intent="batch:test-item"
        )
    assert problem.value.code == "INGESTION_INTENT_CONFLICT"


def test_sqlite_constraint_upgrade_preserves_existing_ids_and_references(workspace):
    settings, store, client, project = workspace
    # Reproduce the old next schema on an empty, isolated database (never the user's data).
    copied = MetaData()
    projects.to_metadata(copied)
    old = assets.to_metadata(copied)
    old.append_constraint(UniqueConstraint("project_id", "sha256", name="old_project_sha"))
    with store.engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE assets")
        connection.execute(CreateTable(old))
    first = client.post(
        f"/api/projects/{project}/assets", files={"file": ("original.csv", b"id,v\n001,2")}
    ).json()["asset"]
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Retained references", "purpose": "inspect"},
    ).json()
    attached = client.post(
        f"/api/tasks/{task['id']}/sources", json={"expected_revision": 1, "assets": [first["id"]]}
    )
    assert attached.status_code == 200
    Store(settings).initialize()
    Store(settings).initialize()  # schema change itself is idempotent
    with store.engine.connect() as connection:
        assert not any(
            set(item["column_names"]) == {"project_id", "sha256"}
            for item in inspect(connection).get_unique_constraints("assets")
        )
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    assert client.get(f"/api/assets/{first['id']}/download").content == b"id,v\n001,2"
    assert (
        client.get(f"/api/tasks/{task['id']}").json()["draft"]["selection"][0]["asset_id"]
        == first["id"]
    )
    second = client.post(
        f"/api/projects/{project}/assets", files={"file": ("new-context.csv", b"id,v\n001,2")}
    ).json()["asset"]
    assert second["id"] != first["id"] and second["name"] == "new-context.csv"


def test_other_project_blob_existence_is_not_disclosed_and_asset_is_not_accessible(workspace):
    _, store, client, project = workspace
    raw = b"id,v\n001,2"
    first = client.post(
        f"/api/projects/{project}/assets", files={"file": ("first.csv", raw)}
    ).json()["asset"]
    other = store.create_account("isolated@example.test", "safe-password-for-tests")
    other_project = store.create_project(other, "Private project")
    second = Intake(store).ingest(other, other_project, io.BytesIO(raw), "private.csv")
    assert second["reused_blob"] is False
    assert second["asset"]["id"] != first["id"]
    assert second["asset"]["object_key"] == first["object_key"]
    with pytest.raises(Problem) as problem:
        Intake(store).read_asset(other, first["id"])
    assert problem.value.status == 404
    assert problem.value.code == "PROJECT_UNAVAILABLE"
