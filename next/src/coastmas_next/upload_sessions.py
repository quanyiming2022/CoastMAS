"""Actor-owned resumable uploads; persisted chunks are content checked, never executed."""

import hashlib
import io
import os
import shutil
import time
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import Field, field_validator
from sqlalchemy import (
    JSON,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    func,
    insert,
    select,
    update,
)

from .contracts import Contract
from .intake import Intake
from .store import Problem, accounts, identifier, metadata

uploads = Table(
    "upload_sessions",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", ForeignKey("projects.id"), nullable=False),
    Column("actor", ForeignKey("accounts.id"), nullable=False),
    Column("request_key", String, nullable=False),
    Column("name", String, nullable=False),
    Column("size", Integer, nullable=False),
    Column("chunk_size", Integer, nullable=False),
    Column("parts", JSON, nullable=False),
    Column("status", String, nullable=False),
    Column("asset_id", ForeignKey("assets.id")),
    Column("error", JSON),
    Column("lease", String),
    Column("lease_until", Float),
    Column("created", Float, nullable=False),
    UniqueConstraint("project_id", "actor", "request_key"),
)


class NewUpload(Contract):
    name: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def basename(cls, value):
        if Path(value).name != value or "\\" in value:
            raise ValueError("File name only")
        return value


class PartReader(io.RawIOBase):
    """Sequential bounded stream; hash each persisted part again before accepting an asset."""

    def __init__(self, root, parts):
        self.root, self.parts = root, parts
        self.index = 0
        self.stream = None
        self.digest = None

    def readable(self):
        return True

    def read(self, size=-1):
        if size < 0:
            raise ValueError("unbounded read is forbidden")
        while self.index < len(self.parts):
            if self.stream is None:
                self.stream = (self.root / str(self.index)).open("rb")
                self.digest = hashlib.sha256()
            data = self.stream.read(size)
            if data:
                self.digest.update(data)
                return data
            self.stream.close()
            self.stream = None
            if self.digest.hexdigest() != self.parts[str(self.index)]["sha256"]:
                raise Problem(409, "PART_CHANGED", "暂存分段校验失败，请重新接入；原件未登记")
            self.index += 1
        return b""

    def close(self):
        if self.stream is not None:
            self.stream.close()
        super().close()


class Uploads:
    def __init__(self, store):
        self.store = store

    def owned(self, c, actor, session, write=False):
        row = (
            c.execute(select(uploads).where(uploads.c.id == session, uploads.c.actor == actor))
            .mappings()
            .first()
        )
        if row is None:
            raise Problem(404, "UPLOAD_UNAVAILABLE", "上传会话不可用")
        self.store.permission(c, actor, row["project_id"], write=write)
        return dict(row)

    def public(self, row):
        result = {
            key: row[key]
            for key in [
                "id",
                "project_id",
                "name",
                "size",
                "chunk_size",
                "parts",
                "status",
                "error",
                "asset_id",
            ]
        }
        result["received_bytes"] = sum(part["size"] for part in row["parts"].values())
        return result

    def read(self, actor, session):
        with self.store.engine.connect() as c:
            return self.public(self.owned(c, actor, session))

    def root(self, session):
        return self.store.settings.storage_root / "receiving" / session

    def create(self, actor, project, body):
        if body.size > self.store.settings.max_upload_bytes:
            raise Problem(413, "UPLOAD_LIMIT", "文件超过接入预算")
        if (body.size - 1) // self.store.settings.upload_chunk_bytes + 1 > 10000:
            raise Problem(413, "PART_LIMIT", "分段数量超过接收预算")
        with self.store.engine.begin() as c:
            self.store.permission(c, actor, project, write=True)
            # Serialize quota and idempotency decisions for this actor on SQLite/PostgreSQL.
            c.execute(update(accounts).where(accounts.c.id == actor).values(id=actor))
            row = (
                c.execute(
                    select(uploads).where(
                        uploads.c.project_id == project,
                        uploads.c.actor == actor,
                        uploads.c.request_key == body.idempotency_key,
                    )
                )
                .mappings()
                .first()
            )
            if row:
                if row["name"] != body.name or row["size"] != body.size:
                    raise Problem(409, "UPLOAD_KEY_CONFLICT", "同一上传意图不能用于不同文件")
                return self.public(row)
            reserved = c.scalar(
                select(func.coalesce(func.sum(uploads.c.size), 0)).where(
                    uploads.c.actor == actor, uploads.c.status.not_in(["ready", "cancelled"])
                )
            )
            if (
                shutil.disk_usage(self.store.settings.storage_root).free
                < 2 * (reserved + body.size) + 64 * 1024**2
            ):
                raise Problem(
                    507, "UPLOAD_DISK_BUDGET", "可用磁盘不足以安全接收与提交；请先处理未完成上传"
                )
            count = c.scalar(
                select(func.count())
                .select_from(uploads)
                .where(uploads.c.actor == actor, uploads.c.status.not_in(["ready", "cancelled"]))
            )
            if count >= 10:
                raise Problem(409, "UPLOAD_QUOTA", "未完成上传超过10份，请先恢复或取消已有上传")
            row = {
                "id": identifier(),
                "project_id": project,
                "actor": actor,
                "request_key": body.idempotency_key,
                "name": body.name,
                "size": body.size,
                "chunk_size": self.store.settings.upload_chunk_bytes,
                "parts": {},
                "status": "receiving",
                "asset_id": None,
                "error": None,
                "lease": None,
                "lease_until": None,
                "created": time.time(),
            }
            c.execute(insert(uploads).values(**row))
            return self.public(row)

    def part(self, actor, session, index, source, claimed_hash):
        with self.store.engine.connect() as c:
            row = self.owned(c, actor, session, True)
        count = (row["size"] - 1) // row["chunk_size"] + 1
        if index < 0 or index >= count:
            raise Problem(422, "PART_INDEX", "分段序号不在文件范围内")
        expected = min(row["chunk_size"], row["size"] - index * row["chunk_size"])
        root = self.root(session)
        root.mkdir(parents=True, exist_ok=True)
        temporary = root / ("incoming-" + uuid4().hex)
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary.open("xb") as output:
                while data := source.read(min(1024**2, expected + 1)):
                    size += len(data)
                    if size > expected:
                        raise Problem(413, "PART_SIZE", "分段超过已声明长度")
                    digest.update(data)
                    output.write(data)
                output.flush()
                os.fsync(output.fileno())
            if size != expected:
                raise Problem(422, "PART_SIZE", "分段不完整，请重试本段")
            checksum = digest.hexdigest()
            if checksum != claimed_hash:
                raise Problem(422, "PART_HASH", "分段内容校验失败")
            with self.store.engine.begin() as c:
                c.execute(
                    update(uploads)
                    .where(uploads.c.id == session, uploads.c.actor == actor)
                    .values(id=session)
                )
                row = self.owned(c, actor, session, True)
                if row["status"] == "cancelled":
                    raise Problem(409, "UPLOAD_CANCELLED", "上传已取消，请新建接入")
                previous = row["parts"].get(str(index))
                if previous:
                    if previous["sha256"] != checksum:
                        raise Problem(
                            409, "PART_CONFLICT", "重选文件内容与已接收分段不同，请建立新上传"
                        )
                    return self.public(row)
                if row["status"] not in {"receiving", "failed"}:
                    raise Problem(409, "UPLOAD_BUSY", "上传正在提交或已完成")
                os.replace(temporary, root / str(index))
                parts = {**row["parts"], str(index): {"sha256": checksum, "size": size}}
                c.execute(
                    update(uploads)
                    .where(uploads.c.id == session)
                    .values(parts=parts, status="receiving", error=None)
                )
                return self.public({**row, "parts": parts, "status": "receiving", "error": None})
        finally:
            temporary.unlink(missing_ok=True)

    def complete(self, actor, session, *, commit_guard=None):
        lease = uuid4().hex
        with self.store.engine.begin() as c:
            c.execute(
                update(uploads)
                .where(uploads.c.id == session, uploads.c.actor == actor)
                .values(id=session)
            )
            row = self.owned(c, actor, session, True)
            if row["asset_id"]:
                return {
                    "asset": Intake(self.store).read_asset(actor, row["asset_id"], c),
                    "upload": self.public(row),
                }
            if row["status"] == "cancelled":
                raise Problem(409, "UPLOAD_CANCELLED", "上传已取消，请重新选择资料开始新接入")
            count = (row["size"] - 1) // row["chunk_size"] + 1
            if len(row["parts"]) != count:
                raise Problem(409, "UPLOAD_INCOMPLETE", "仍有未接收分段，请继续上传")
            if row["status"] == "committing" and (row["lease_until"] or 0) > time.time():
                raise Problem(409, "UPLOAD_BUSY", "服务器正在提交原件，可稍后恢复查询")
            c.execute(
                update(uploads)
                .where(uploads.c.id == session)
                .values(status="committing", lease=lease, lease_until=time.time() + 600, error=None)
            )
        try:
            with PartReader(self.root(session), row["parts"]) as source:
                result = Intake(self.store).ingest(
                    actor, row["project_id"], source, row["name"], intent="upload:" + session,
                    commit_guard=commit_guard
                )
            with self.store.engine.begin() as c:
                self.store.permission(c, actor, row["project_id"], write=True)
                changed = c.execute(
                    update(uploads)
                    .where(uploads.c.id == session, uploads.c.lease == lease)
                    .values(
                        status="ready", asset_id=result["asset"]["id"], lease=None, lease_until=None
                    )
                ).rowcount
                if changed != 1:
                    raise Problem(409, "UPLOAD_LEASE", "本次提交租约已变化，请刷新查看服务器状态")
            # Keep only immutable source after confirmed registration; retry returns that asset.
            for index in row["parts"]:
                (self.root(session) / index).unlink(missing_ok=True)
            return {"asset": result["asset"], "upload": self.read(actor, session)}
        except Exception as exc:
            issue = (
                {"code": exc.code, "message": exc.message}
                if isinstance(exc, Problem)
                else {
                    "code": "UPLOAD_COMMIT_FAILED",
                    "message": "原件提交失败，已接收分段保留，可重试",
                }
            )
            with self.store.engine.begin() as c:
                c.execute(
                    update(uploads)
                    .where(uploads.c.id == session, uploads.c.lease == lease)
                    .values(status="failed", error=issue, lease=None, lease_until=None)
                )
            if isinstance(exc, Problem):
                raise
            raise Problem(422, issue["code"], issue["message"]) from exc


def router(store):
    routes = APIRouter()
    service = Uploads(store)

    @routes.post("/api/projects/{project}/uploads", status_code=201)
    def create(project: str, body: NewUpload, request: Request):
        return service.create(request.state.actor["id"], project, body)

    @routes.get("/api/projects/{project}/uploads")
    def pending(project: str, request: Request):
        actor = request.state.actor["id"]
        with store.engine.connect() as c:
            store.permission(c, actor, project)
            return [
                service.public(row)
                for row in c.execute(
                    select(uploads)
                    .where(
                        uploads.c.project_id == project,
                        uploads.c.actor == actor,
                        uploads.c.status.not_in(["ready", "cancelled"]),
                    )
                    .order_by(uploads.c.created)
                ).mappings()
            ]

    @routes.get("/api/uploads/{session}")
    def read(session: str, request: Request):
        return service.read(request.state.actor["id"], session)

    @routes.post("/api/uploads/{session}/parts/{index}")
    def part(
        session: str,
        index: int,
        request: Request,
        file: Annotated[UploadFile, File()],
        sha256: Annotated[str, Form(min_length=64, max_length=64)],
    ):
        return service.part(request.state.actor["id"], session, index, file.file, sha256)

    @routes.delete("/api/uploads/{session}")
    def cancel(session: str, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            c.execute(
                update(uploads)
                .where(uploads.c.id == session, uploads.c.actor == actor)
                .values(id=session)
            )
            row = service.owned(c, actor, session, True)
            if row["status"] in {"ready", "committing"}:
                raise Problem(409, "UPLOAD_BUSY", "原件已登记或正在提交，不能作为未完成上传取消")
            c.execute(update(uploads).where(uploads.c.id == session).values(status="cancelled"))
        for part in row["parts"]:
            (service.root(session) / part).unlink(missing_ok=True)
        return service.read(actor, session)

    @routes.post("/api/uploads/{session}/complete")
    def complete(session: str, request: Request):
        return service.complete(request.state.actor["id"], session)

    return routes
