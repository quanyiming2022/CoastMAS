"""Streaming, immutable byte storage and atomic task attachment."""

import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from .contracts import TaskDraft
from .profiles import inspect_file
from .store import Problem, audit_event, identifier, metadata, revisions, tasks

assets = Table(
    "assets",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", ForeignKey("projects.id"), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("name", String, nullable=False),
    Column("sha256", String, nullable=False),
    Column("size", Integer, nullable=False),
    Column("object_key", String, nullable=False),
    Column("facts", JSON, nullable=False),
    Column("created", Float, nullable=False),
)


class Intake:
    def __init__(self, store):
        self.store = store

    def local_file(self, project, path):
        path = Path(path)
        if (
            path.is_symlink()
            or not path.is_file()
            or not any(
                path.resolve().is_relative_to(root.resolve())
                for root in self.store.settings.local_sources
            )
        ):
            raise Problem(403, "SOURCE_NOT_AUTHORIZED", "本地文件不在授权来源中")
        return path.resolve()

    def read_asset(self, actor, asset_id, connection=None):
        if connection is None:
            with self.store.engine.connect() as c:
                return self.read_asset(actor, asset_id, c)
        asset = connection.execute(select(assets).where(assets.c.id == asset_id)).mappings().first()
        if asset is None:
            raise Problem(404, "ASSET_UNAVAILABLE", "资料不可用")
        self.store.permission(connection, actor, asset["project_id"])
        return dict(asset)

    def ingest(
        self,
        actor,
        project,
        source,
        name,
        task_id=None,
        expected_revision=None,
        validate_source=None,
        intent=None,
        commit_guard=None,
    ):
        from .logical_intake import sidecar
        if sidecar(name):
            raise Problem(422, "SIDECAR_REQUIRES_PRIMARY", "附件需与对应主件成组导入，不能独立作为指标。")
        with self.store.engine.connect() as c:
            self.store.permission(c, actor, project, write=True)
            if task_id:
                current = self.store.task(actor, task_id, write=True, connection=c)
                if current["project_id"] != project:
                    raise Problem(422, "TASK_PROJECT", "资料与任务必须位于同一项目")
                if expected_revision != current["revision"]:
                    raise Problem(409, "DRAFT_CONFLICT", "任务已改变，请重新核对当前任务")
        root = self.store.settings.storage_root
        temporary = root / ("incoming-" + uuid4().hex)
        digest, size = hashlib.sha256(), 0
        try:
            with temporary.open("xb") as output:
                while chunk := source.read(1024**2):
                    size += len(chunk)
                    if size > self.store.settings.max_upload_bytes:
                        raise Problem(413, "UPLOAD_LIMIT", "文件超过配置的接入上限")
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if validate_source is not None:
                validate_source()
            checksum = digest.hexdigest()
            with self.store.engine.connect() as c:
                existing = (
                    c.execute(
                        select(assets).where(
                            assets.c.project_id == project, assets.c.sha256 == checksum
                        )
                    )
                    .mappings()
                    .first()
                )
            facts = (existing["facts"] if existing and not existing["facts"].get("logical_package")
                     else inspect_file(temporary))
            object_key = checksum[:2] + "/" + checksum
            target = root / object_key
            target.parent.mkdir(exist_ok=True)
            try:
                os.link(temporary, target)
            except FileExistsError:
                pass
            asset_id = (
                hashlib.sha256(json.dumps([actor, project, intent]).encode()).hexdigest()[:32]
                if intent is not None
                else identifier()
            )
            asset = {
                "id": asset_id,
                "project_id": project,
                "revision": 1,
                "name": Path(name).name,
                "sha256": checksum,
                "size": size,
                "object_key": object_key,
                "facts": facts,
                "created": time.time(),
            }
            reused_blob = existing is not None
            replayed = False
            with self.store.engine.begin() as c:
                self.store.permission(c, actor, project, write=True)
                from .management_catalog import require_available
                require_available(c, "projects", project)
                if commit_guard is not None:
                    commit_guard(c)
                try:
                    with c.begin_nested():
                        c.execute(insert(assets).values(**asset))
                except IntegrityError:
                    row = (
                        c.execute(select(assets).where(assets.c.id == asset_id)).mappings().first()
                    )
                    if row is None:
                        raise
                    if any(
                        row[key] != asset[key] for key in ["project_id", "sha256", "size", "name"]
                    ):
                        raise Problem(
                            409, "INGESTION_INTENT_CONFLICT", "同一接入意图不能用于不同资料"
                        ) from None
                    asset, replayed = dict(row), True
                if task_id:
                    current = self.store.task(actor, task_id, write=True, connection=c)
                    draft = current["draft"]
                    if not any(r["asset_id"] == asset["id"] for r in draft["selection"]):
                        from .reuse import Reuse

                        reuse = Reuse(self.store)
                        reuse.bind(
                            draft,
                            asset,
                            reuse.suggestions(actor, asset["id"], asset=asset, connection=c),
                        )
                    draft = TaskDraft.model_validate(draft).model_dump(mode="json")
                    changed = c.execute(
                        update(tasks)
                        .where(tasks.c.id == task_id, tasks.c.revision == expected_revision)
                        .values(draft=draft, revision=expected_revision + 1, updated=time.time())
                    ).rowcount
                    if changed != 1:
                        raise Problem(409, "DRAFT_CONFLICT", "任务已有更新；未覆盖已保存内容")
                    c.execute(
                        insert(revisions).values(
                            task_id=task_id,
                            revision=expected_revision + 1,
                            draft=draft,
                            actor=actor,
                            created=time.time(),
                        )
                    )
                audit_event(
                    c, actor, project, "replay_ingest" if replayed else "ingest_asset", asset["id"]
                )
            return {
                "asset": asset,
                "reused_blob": reused_blob,
                "replayed": replayed,
                "task": self.store.task(actor, task_id) if task_id else None,
            }
        finally:
            temporary.unlink(missing_ok=True)
