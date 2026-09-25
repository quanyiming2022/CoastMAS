"""Nondestructive next-namespace schema upgrade: asset identity is not blob identity."""

import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from sqlalchemy import MetaData, func, inspect, select
from sqlalchemy.schema import CreateTable


def separate_asset_identity(connection, settings):
    from .intake import assets
    from .store import projects

    constraints = [
        item
        for item in inspect(connection).get_unique_constraints("assets")
        if set(item["column_names"]) == {"project_id", "sha256"}
    ]
    if not constraints:
        return False
    dialect = connection.dialect.name
    quote = connection.dialect.identifier_preparer.quote
    if dialect == "postgresql":
        for constraint in constraints:
            connection.exec_driver_sql(
                "ALTER TABLE assets DROP CONSTRAINT " + quote(constraint["name"])
            )
    elif dialect == "sqlite":
        columns = {item["name"] for item in inspect(connection).get_columns("assets")}
        if columns != set(assets.c.keys()):
            raise RuntimeError("Unknown asset schema; refusing to discard any fields")
        # Keep a private pre-upgrade snapshot. Reading via another connection is safe
        # while BEGIN IMMEDIATE excludes other writers; originals are never replaced.
        database = connection.engine.url.database
        if database and database != ":memory:" and Path(database).is_file():
            directory = settings.storage_root / "schema-backups"
            directory.mkdir(exist_ok=True, mode=0o700)
            backup = directory / ("before-asset-identity-" + uuid4().hex + ".sqlite")
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            with sqlite3.connect(database) as source, sqlite3.connect(backup) as target:
                source.backup(target)
        temporary = MetaData()
        projects.to_metadata(temporary)
        replacement = assets.to_metadata(temporary, name="assets_identity_upgrade")
        connection.execute(CreateTable(replacement))
        names = ", ".join(quote(column) for column in assets.c.keys())
        before = connection.scalar(select(func.count()).select_from(assets))
        connection.exec_driver_sql(
            f"INSERT INTO assets_identity_upgrade ({names}) SELECT {names} FROM assets"
        )
        after = connection.scalar(select(func.count()).select_from(replacement))
        if before != after:
            raise RuntimeError("Asset count mismatch; schema transaction must roll back")
        connection.exec_driver_sql("DROP TABLE assets")
        connection.exec_driver_sql("ALTER TABLE assets_identity_upgrade RENAME TO assets")
        if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("Reference integrity failed; schema transaction must roll back")
    else:
        raise RuntimeError("Asset identity upgrade is only verified for SQLite/PostgreSQL")
    return True
