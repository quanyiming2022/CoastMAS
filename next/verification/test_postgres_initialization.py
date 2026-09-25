"""Concurrent clean PostgreSQL initialization against an explicitly isolated host."""

import concurrent.futures
import io
import json
import os
import threading
from pathlib import Path
from uuid import uuid4

from coastmas_next.config import Settings
from coastmas_next.intake import Intake
from coastmas_next.store import Store
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


def test_two_process_roles_can_initialize_one_clean_database(tmp_path):
    config_path = os.environ.get("COASTMAS_NEXT_TEST_CONFIG")
    if not config_path:
        raise RuntimeError("Explicit isolated PostgreSQL config required")
    config = json.loads(Path(config_path).read_text())
    original = make_url(config["database_url"])
    assert (original.database or "").startswith("coastmas_next_")
    database = "coastmas_next_init_test_" + uuid4().hex
    control = create_engine(original.set(database="postgres"), isolation_level="AUTOCOMMIT")
    stores = []
    with control.connect() as connection:
        connection.execute(text('CREATE DATABASE "' + database + '"'))
    try:
        settings = Settings(
            database_url=original.set(database=database).render_as_string(hide_password=False),
            storage_root=tmp_path / "objects",
        )
        stores = [Store(settings), Store(settings)]
        barrier = threading.Barrier(2)

        def initialize(store):
            barrier.wait()
            store.initialize()
            with store.engine.connect() as connection:
                return connection.execute(text("SELECT COUNT(*) FROM projects")).scalar_one()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(initialize, stores))
        assert results == [0, 0]
        store = stores[0]
        actor = store.create_account("identity@example.test", "isolated-password-for-testing")
        project = store.create_project(actor, "Asset identity upgrade test")
        with store.engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE assets ADD CONSTRAINT previous_project_sha "
                    "UNIQUE (project_id, sha256)"
                )
            )
        first = Intake(store).ingest(actor, project, io.BytesIO(b"id,v\n001,0"), "original.csv")[
            "asset"
        ]
        barrier = threading.Barrier(2)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(initialize, stores))
        assert results == [1, 1]
        second = Intake(store).ingest(
            actor, project, io.BytesIO(b"id,v\n001,0"), "new-context.csv"
        )["asset"]
        assert first["id"] != second["id"] and first["object_key"] == second["object_key"]
        assert Intake(store).read_asset(actor, first["id"])["name"] == "original.csv"
        from coastmas_next.resource_catalog import (
            CatalogOperations,
            CatalogQuery,
            MetadataEdit,
            Operation,
            list_assets,
        )

        catalog = CatalogOperations(store)
        catalog.edit(
            actor,
            first["id"],
            MetadataEdit(
                expected_revision=0,
                display_name="中文目录",
                tags=["海岸"],
                description="实际PostgreSQL查询",
            ),
        )
        with store.engine.connect() as connection:
            page = list_assets(
                connection, project, CatalogQuery(query="海岸", profile="csv"), 0, 20
            )
            assert page["total"] == 1 and page["items"][0]["id"] == first["id"]
        plan = catalog.preview(
            actor, project, Operation(action="recycle", selection={"ids": [first["id"]]})
        )
        applied = catalog.apply(actor, project, plan["id"])
        assert applied["items"][0]["status"] == "applied"
        assert catalog.apply(actor, project, plan["id"]) == applied
        with store.engine.connect() as connection:
            assert not any(
                set(item["column_names"]) == {"project_id", "sha256"}
                for item in inspect(connection).get_unique_constraints("assets")
            )
    finally:
        for store in stores:
            store.engine.dispose()
        with control.connect() as connection:
            connection.execute(text('DROP DATABASE "' + database + '"'))
        control.dispose()
