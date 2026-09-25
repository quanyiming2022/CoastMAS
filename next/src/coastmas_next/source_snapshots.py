"""Durable, explicitly requested local-source copies into the managed library."""

import hashlib
import io
import os
import time
from pathlib import PurePosixPath

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import (
    JSON,
    Column,
    Float,
    ForeignKey,
    String,
    Table,
    and_,
    insert,
    or_,
    select,
    update,
)

from .batches import BatchIntake, source_grants
from .contracts import Contract
from .logical_intake import CompletePackage, PackageMember, complete_package, sidecar
from .management_catalog import require_available
from .store import Problem, identifier, metadata
from .upload_sessions import NewUpload, Uploads

snapshots = Table(
    "source_snapshot_jobs",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", ForeignKey("projects.id")),
    Column("actor", ForeignKey("accounts.id")),
    Column("intent", String, nullable=False),
    Column("source_id", String, nullable=False),
    Column("request", JSON, nullable=False),
    Column("members", JSON, nullable=False),
    Column("status", String, nullable=False),
    Column("asset_id", ForeignKey("assets.id")),
    Column("error", JSON),
    Column("lease", String),
    Column("lease_until", Float, nullable=False),
    Column("created", Float, nullable=False),
)


class SnapshotRequest(Contract):
    source_id: str
    paths: list[str] = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=100)


def signature(stream):
    info = os.fstat(stream.fileno())
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]


class SourceSnapshots:
    def __init__(self, store):
        self.store, self.sources, self.uploads = store, BatchIntake(store), Uploads(store)

    def create(self, actor, project, body):
        request = body.model_dump(mode="json")
        with self.store.engine.connect() as c:
            self.store.permission(c, actor, project, write=True)
            existing = [
                dict(r)
                for r in c.execute(
                    select(snapshots).where(
                        snapshots.c.project_id == project,
                        snapshots.c.actor == actor,
                        snapshots.c.intent == body.idempotency_key,
                    )
                ).mappings()
            ]
        if existing:
            if existing[0]["request"] != request:
                raise Problem(409, "SOURCE_INTENT_CONFLICT", "同一接入意图不能改用其他来源或资料")
            return {"items": existing}
        self.sources._root(actor, project, body.source_id)
        groups, consumed = [], set()
        paths = sorted(set(body.paths), key=lambda p: (sidecar(p), p))
        for path in paths:
            if path in consumed:
                continue
            main = PurePosixPath(path)
            if sidecar(main.name):
                raise Problem(422, "SIDECAR_REQUIRES_PRIMARY", "请选择对应TIFF主件，附件自动归组")
            related = [path]
            if main.suffix.lower() in {".tif", ".tiff"}:
                folder = "" if str(main.parent) == "." else str(main.parent)
                # Exact sibling matching; do not load arbitrary directory children as assets.
                names = {main.name.lower() + suffix for suffix in (".aux.xml", ".ovr", ".msk")}
                names |= {
                    main.stem.lower() + suffix for suffix in (".tfw", ".tifw", ".tiffw", ".wld")
                }
                listing = self.sources.browse(actor, project, body.source_id, folder)
                for offset in range(0, listing["total"], 100):
                    page = (
                        listing
                        if offset == 0
                        else self.sources.browse(actor, project, body.source_id, folder, offset)
                    )
                    related.extend(
                        e["path"]
                        for e in page["items"]
                        if not e["directory"] and e["name"].lower() in names
                    )
            members = []
            for related_path in sorted(set(related)):
                with self.sources.open_source(
                    actor, project, body.source_id, related_path
                ) as stream:
                    observed = signature(stream)
                if observed[2] <= 0 or observed[2] > self.store.settings.max_upload_bytes:
                    raise Problem(413, "UPLOAD_LIMIT", "资料为空或超过接入预算")
                members.append({"path": related_path, "signature": observed})
            consumed.update(related)
            groups.append(members)
        with self.store.engine.begin() as c:
            self.store.permission(c, actor, project, write=True)
            require_available(c, "projects", project)
            self.grant(c, project, body.source_id)
            # Parent lock serializes lost-response replay and concurrent identical requests.
            existing = [
                dict(r)
                for r in c.execute(
                    select(snapshots).where(
                        snapshots.c.project_id == project,
                        snapshots.c.actor == actor,
                        snapshots.c.intent == body.idempotency_key,
                    )
                ).mappings()
            ]
            if existing:
                if existing[0]["request"] != request:
                    raise Problem(409, "SOURCE_INTENT_CONFLICT", "接入意图已经用于不同资料")
                return {"items": existing}
            entries = []
            for members in groups:
                item = {
                    "id": identifier(),
                    "project_id": project,
                    "actor": actor,
                    "intent": body.idempotency_key,
                    "source_id": body.source_id,
                    "request": request,
                    "members": members,
                    "status": "queued",
                    "asset_id": None,
                    "error": None,
                    "lease": None,
                    "lease_until": 0.0,
                    "created": time.time(),
                }
                c.execute(insert(snapshots).values(**item))
                entries.append(item)
            return {"items": entries}

    @staticmethod
    def grant(c, project, source_id):
        if not c.scalar(
            select(source_grants.c.source_id).where(
                source_grants.c.project_id == project, source_grants.c.source_id == source_id
            )
        ):
            raise Problem(
                403, "SOURCE_NOT_AUTHORIZED", "项目来源授权已撤销，未继续导入；已有受管资料保留"
            )

    def run_once(self):
        lease = identifier()
        with self.store.engine.begin() as c:
            condition = or_(
                snapshots.c.status == "queued",
                and_(snapshots.c.status == "copying", snapshots.c.lease_until < time.time()),
            )
            row = (
                c.execute(select(snapshots).where(condition).order_by(snapshots.c.created).limit(1))
                .mappings()
                .first()
            )
            if row is None:
                return False
            if (
                c.execute(
                    update(snapshots)
                    .where(snapshots.c.id == row["id"], condition)
                    .values(status="copying", lease=lease, lease_until=time.time() + 120)
                ).rowcount
                != 1
            ):
                return False
            item = dict(row)
        try:
            actor, project = item["actor"], item["project_id"]

            def guard(c):
                self.grant(c, project, item["source_id"])
                owner = c.scalar(select(snapshots.c.lease).where(snapshots.c.id == item["id"]))
                if owner != lease:
                    raise Problem(409, "SOURCE_LEASE", "此导入已由其他进程恢复，请刷新状态")

            uploads = []
            for member in item["members"]:
                path = member["path"]
                size = member["signature"][2]
                upload = self.uploads.create(
                    actor,
                    project,
                    NewUpload(
                        name=PurePosixPath(path).name,
                        size=size,
                        idempotency_key=item["id"] + hashlib.sha256(path.encode()).hexdigest()[:32],
                    ),
                )
                uploads.append(PackageMember(upload_id=upload["id"], relative_path=path))
                if upload["status"] == "ready":
                    continue
                with self.sources.open_source(actor, project, item["source_id"], path) as stream:
                    if signature(stream) != member["signature"]:
                        raise Problem(
                            409,
                            "SOURCE_CHANGED",
                            "源文件已变化，请重新选择建立新快照；已有分段保留",
                        )
                    for index in range((size - 1) // upload["chunk_size"] + 1):
                        data = stream.read(upload["chunk_size"])
                        with self.store.engine.begin() as c:
                            self.store.permission(c, actor, project, write=True)
                            guard(c)
                            c.execute(
                                update(snapshots)
                                .where(snapshots.c.id == item["id"], snapshots.c.lease == lease)
                                .values(lease_until=time.time() + 120)
                            )
                        self.uploads.part(
                            actor,
                            upload["id"],
                            index,
                            io.BytesIO(data),
                            hashlib.sha256(data).hexdigest(),
                        )
                    if signature(stream) != member["signature"]:
                        raise Problem(409, "SOURCE_CHANGED", "读取期间源文件发生变化，未登记为资产")
            is_tiff = any(
                PurePosixPath(m.relative_path).suffix.lower() in {".tif", ".tiff"} for m in uploads
            )
            if is_tiff:
                result = complete_package(
                    self.store,
                    actor,
                    project,
                    CompletePackage(idempotency_key="source:" + item["id"], members=uploads),
                    commit_guard=guard,
                )
            else:
                result = self.uploads.complete(actor, uploads[0].upload_id, commit_guard=guard)
            with self.store.engine.begin() as c:
                c.execute(
                    update(snapshots)
                    .where(snapshots.c.id == item["id"], snapshots.c.lease == lease)
                    .values(
                        status="ready",
                        asset_id=result["asset"]["id"],
                        error=None,
                        lease=None,
                        lease_until=0,
                    )
                )
        except Exception as exc:
            error = (
                {"code": exc.code, "message": exc.message}
                if isinstance(exc, Problem)
                else {
                    "code": "SOURCE_SNAPSHOT_FAILED",
                    "message": "受管快照失败，原件及已接收分段保留",
                }
            )
            with self.store.engine.begin() as c:
                c.execute(
                    update(snapshots)
                    .where(snapshots.c.id == item["id"], snapshots.c.lease == lease)
                    .values(status="failed", error=error, lease=None, lease_until=0)
                )
            if not isinstance(exc, Problem):
                import logging

                logging.getLogger(__name__).exception("Source snapshot failed %s", item["id"])
        return True


def router(store):
    routes, service = APIRouter(), SourceSnapshots(store)

    @routes.post("/api/projects/{project}/source-snapshots", status_code=201)
    def create(project: str, body: SnapshotRequest, request: Request):
        return service.create(request.state.actor["id"], project, body)

    @routes.get("/api/projects/{project}/source-snapshots")
    def listing(project: str, request: Request):
        with store.engine.connect() as c:
            store.permission(c, request.state.actor["id"], project)
            return [
                dict(row)
                for row in c.execute(
                    select(snapshots)
                    .where(
                        snapshots.c.project_id == project,
                        snapshots.c.actor == request.state.actor["id"],
                    )
                    .order_by(snapshots.c.created.desc())
                    .limit(100)
                ).mappings()
            ]

    @routes.post("/api/source-snapshots/{key}/retry")
    def retry(key: str, request: Request):
        with store.engine.begin() as c:
            row = (
                c.execute(
                    select(snapshots).where(
                        snapshots.c.id == key, snapshots.c.actor == request.state.actor["id"]
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise Problem(404, "SOURCE_SNAPSHOT", "此接入不可用")
            store.permission(c, request.state.actor["id"], row["project_id"], write=True)
            require_available(c, "projects", row["project_id"])
            service.grant(c, row["project_id"], row["source_id"])
            if row["status"] == "failed":
                c.execute(
                    update(snapshots)
                    .where(snapshots.c.id == key, snapshots.c.status == "failed")
                    .values(status="queued", error=None)
                )
        return {"queued": True}

    return routes
