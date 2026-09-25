"""Persistent intake items with bounded local access and append-only task binding."""

import hashlib
import logging
import os
import stat
import time
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile
from pydantic import Field, model_validator
from sqlalchemy import (
    JSON,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from .contracts import Contract
from .intake import Intake
from .reuse import Reuse
from .store import Problem, accounts, audit_event, identifier, metadata

logger = logging.getLogger(__name__)
imports = Table(
    "imports",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", ForeignKey("projects.id"), nullable=False),
    Column("actor", ForeignKey("accounts.id"), nullable=False),
    Column("task_id", ForeignKey("tasks.id"), nullable=False),
    Column("request_key", String, nullable=False),
    Column("fingerprint", String, nullable=False),
    Column("created", Float, nullable=False),
    UniqueConstraint("project_id", "request_key"),
)
items = Table(
    "import_items",
    metadata,
    Column("id", String, primary_key=True),
    Column("import_id", ForeignKey("imports.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("source", JSON, nullable=False),
    Column("status", String, nullable=False),
    Column("asset_id", ForeignKey("assets.id")),
    Column("lease", String),
    Column("lease_until", Float),
    Column("error", JSON),
    UniqueConstraint("import_id", "ordinal"),
)
source_grants = Table(
    "local_source_grants",
    metadata,
    Column("project_id", ForeignKey("projects.id"), primary_key=True),
    Column("source_id", String, primary_key=True),
    Column("actor", ForeignKey("accounts.id"), nullable=False),
)


class SourceItem(Contract):
    name: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0)
    source_id: str | None = None
    path: str | None = None

    @model_validator(mode="after")
    def coherent(self):
        if (self.source_id is None) != (self.path is None):
            raise ValueError("Local source and relative path must be supplied together")
        if Path(self.name).name != self.name or "\\" in self.name:
            raise ValueError("File name must not contain a directory")
        return self


class NewImport(Contract):
    task_id: str
    idempotency_key: str = Field(min_length=1, max_length=100)
    items: list[SourceItem] = Field(min_length=1, max_length=200)


class BatchIntake:
    def __init__(self, store):
        self.store = store
        self.intake = Intake(store)

    def sources(self, actor, project):
        with self.store.engine.connect() as c:
            role = self.store.permission(c, actor, project, write=True)
            admin = c.scalar(
                select(accounts.c.system_admin).where(
                    accounts.c.id == actor, accounts.c.active.is_(True)
                )
            )
            grants = set(
                c.scalars(
                    select(source_grants.c.source_id).where(source_grants.c.project_id == project)
                )
            )
        if role not in {"curator", "manager"}:
            return []
        return [
            {
                "id": hashlib.sha256(str(root.resolve()).encode()).hexdigest(),
                "name": root.name,
                "granted": hashlib.sha256(str(root.resolve()).encode()).hexdigest() in grants,
            }
            for root in self.store.settings.local_sources
            if admin or hashlib.sha256(str(root.resolve()).encode()).hexdigest() in grants
        ]

    def _root(self, actor, project, source_id):
        if source_id not in {s["id"] for s in self.sources(actor, project) if s["granted"]}:
            raise Problem(403, "SOURCE_NOT_AUTHORIZED", "当前项目与角色没有此本地来源的授权")
        return next(
            root.resolve()
            for root in self.store.settings.local_sources
            if hashlib.sha256(str(root.resolve()).encode()).hexdigest() == source_id
        )

    def _descriptor(self, actor, project, source_id, relative, *, directory=False):
        root = self._root(actor, project, source_id)
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative:
            raise Problem(403, "SOURCE_PATH", "仅允许授权目录内的相对路径")
        flags = os.O_RDONLY | os.O_NOFOLLOW
        fd = None
        try:
            fd = os.open(root, flags | os.O_DIRECTORY)
            for index, part in enumerate(path.parts):
                is_directory = index < len(path.parts) - 1 or directory
                child = os.open(part, flags | (os.O_DIRECTORY if is_directory else 0), dir_fd=fd)
                os.close(fd)
                fd = child
            info = os.fstat(fd)
            if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
                raise Problem(403, "SOURCE_TYPE", "仅接入普通文件，不跟随符号链接")
            return fd
        except (OSError, ValueError) as exc:
            if fd is not None:
                os.close(fd)
            raise Problem(403, "SOURCE_PATH", "来源不存在、已变化或包含不允许的链接") from exc
        except BaseException:
            if fd is not None:
                os.close(fd)
            raise

    def open_source(self, actor, project, source_id, relative):
        return os.fdopen(self._descriptor(actor, project, source_id, relative), "rb")

    def browse(self, actor, project, source_id, path="", offset=0, search=""):
        fd = self._descriptor(actor, project, source_id, path, directory=True)
        try:
            found = []
            with os.scandir(fd) as entries:
                for entry in entries:
                    if entry.is_symlink() or not (
                        entry.is_dir(follow_symlinks=False) or entry.is_file(follow_symlinks=False)
                    ):
                        continue
                    if search.casefold() not in entry.name.casefold():
                        continue
                    found.append(
                        {
                            "name": entry.name,
                            "path": str(PurePosixPath(path) / entry.name),
                            "directory": entry.is_dir(follow_symlinks=False),
                            "size": entry.stat(follow_symlinks=False).st_size,
                        }
                    )
                    if len(found) > 10000:
                        raise Problem(422, "DIRECTORY_LIMIT", "目录匹配项过多，请先使用名称筛选")
            found.sort(key=lambda entry: (not entry["directory"], entry["name"]))
            return {
                "items": found[offset : offset + 100],
                "total": len(found),
                "offset": offset,
                "limit": 100,
            }
        finally:
            os.close(fd)

    def read(self, actor, batch_id, *, write=False):
        with self.store.engine.connect() as c:
            row = c.execute(select(imports).where(imports.c.id == batch_id)).mappings().first()
            if row is None:
                raise Problem(404, "IMPORT_UNAVAILABLE", "接入批次不可用")
            self.store.permission(c, actor, row["project_id"], write=write)
            return {
                **dict(row),
                "items": [
                    dict(item)
                    for item in c.execute(
                        select(items).where(items.c.import_id == batch_id).order_by(items.c.ordinal)
                    ).mappings()
                ],
            }

    def create(self, actor, project, request):
        body = NewImport.model_validate(request)
        task = self.store.task(actor, body.task_id, write=True)
        if task["project_id"] != project:
            raise Problem(422, "TASK_PROJECT", "资料与任务必须在同一项目")
        fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
        observed = []
        for source in body.items:
            signature = None
            if source.size > self.store.settings.max_upload_bytes:
                raise Problem(413, "UPLOAD_LIMIT", "文件超过当前接入预算")
            if source.source_id:
                with self.open_source(actor, project, source.source_id, source.path) as stream:
                    info = os.fstat(stream.fileno())
                    signature = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]
                    if info.st_size != source.size:
                        raise Problem(409, "SOURCE_CHANGED", "源文件大小已变化，请刷新资料列表")
            observed.append(signature)
        with self.store.engine.begin() as c:
            self.store.permission(c, actor, project, write=True)
            existing = (
                c.execute(
                    select(imports).where(
                        imports.c.project_id == project,
                        imports.c.request_key == body.idempotency_key,
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise Problem(409, "IMPORT_KEY_CONFLICT", "同一请求标识不能用于不同批次")
                batch_id = existing["id"]
            else:
                batch_id = identifier()
                try:
                    with c.begin_nested():
                        c.execute(
                            insert(imports).values(
                                id=batch_id,
                                project_id=project,
                                actor=actor,
                                task_id=body.task_id,
                                request_key=body.idempotency_key,
                                fingerprint=fingerprint,
                                created=time.time(),
                            )
                        )
                        for ordinal, source in enumerate(body.items):
                            c.execute(
                                insert(items).values(
                                    id=identifier(),
                                    import_id=batch_id,
                                    ordinal=ordinal,
                                    source={
                                        **source.model_dump(),
                                        "observed_stat": observed[ordinal],
                                    },
                                    status="queued" if source.source_id else "awaiting_upload",
                                )
                            )
                except IntegrityError as exc:
                    raise Problem(
                        409, "IMPORT_RACE", "批次正在由另一请求创建，请以相同标识重试"
                    ) from exc
                audit_event(c, actor, project, "create_import", batch_id)
        return self.read(actor, batch_id)

    def attach(self, batch, asset_id):
        # Append to the latest draft, never rewrite the user's existing mappings.
        for _ in range(3):
            task = self.store.task(batch["actor"], batch["task_id"], write=True)
            if any(ref["asset_id"] == asset_id for ref in task["draft"]["selection"]):
                return
            try:
                Reuse(self.store).attach(batch["actor"], task["id"], task["revision"], [asset_id])
                return
            except Problem as exc:
                if exc.code != "DRAFT_CONFLICT":
                    raise
        raise Problem(409, "ATTACH_CONFLICT", "资料已受管，任务有并发修改；重试此项即可继续绑定")

    def process(self, batch, item, stream, validate_source=None):
        try:
            asset_id = item["asset_id"]
            if not asset_id:
                result = self.intake.ingest(
                    batch["actor"],
                    batch["project_id"],
                    stream,
                    item["source"]["name"],
                    validate_source=validate_source,
                    intent="batch:" + item["id"],
                )
                if result["asset"]["size"] != item["source"]["size"]:
                    raise Problem(409, "SOURCE_CHANGED", "读取字节数与已选择的文件大小不一致")
                asset_id = result["asset"]["id"]
                with self.store.engine.begin() as c:
                    c.execute(
                        update(items)
                        .where(items.c.id == item["id"], items.c.lease == item["lease"])
                        .values(asset_id=asset_id)
                    )
            with self.store.engine.connect() as c:
                if c.scalar(select(items.c.lease).where(items.c.id == item["id"])) != item["lease"]:
                    raise Problem(409, "IMPORT_LEASE_LOST", "接入处理资格已由恢复请求接管")
            self.attach(batch, asset_id)
            with self.store.engine.begin() as c:
                changed = c.execute(
                    update(items)
                    .where(items.c.id == item["id"], items.c.lease == item["lease"])
                    .values(status="ready", error=None, lease_until=None)
                ).rowcount
                if changed != 1:
                    raise Problem(409, "IMPORT_LEASE_LOST", "处理资格已变化")
            return next(
                i for i in self.read(batch["actor"], batch["id"])["items"] if i["id"] == item["id"]
            )
        except Exception as exc:
            problem = (
                exc
                if isinstance(exc, Problem)
                else Problem(
                    422,
                    "SOURCE_READ_FAILED",
                    "实际文件解析失败，请检查文件和批次错误；其他文件可继续",
                )
            )
            if not isinstance(exc, Problem):
                logger.exception("Intake item %s failed", item["id"])
            with self.store.engine.begin() as c:
                c.execute(
                    update(items)
                    .where(items.c.id == item["id"], items.c.lease == item["lease"])
                    .values(
                        status="failed",
                        lease_until=None,
                        error={"code": problem.code, "message": problem.message},
                    )
                )
            raise problem from exc

    def claim(self, batch_id=None, item_id=None):
        now = time.time()
        with self.store.engine.begin() as c:
            condition = or_(
                items.c.status.in_(
                    ["queued"] if item_id is None else ["awaiting_upload", "failed"]
                ),
                (items.c.status == "receiving") & (items.c.lease_until < now),
            )
            statement = (
                select(items)
                .where(condition)
                .order_by(items.c.ordinal)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if item_id:
                statement = statement.where(items.c.id == item_id, items.c.import_id == batch_id)
            row = c.execute(statement).mappings().first()
            if row is None:
                return None
            token = identifier()
            changed = c.execute(
                update(items)
                .where(items.c.id == row["id"], condition)
                .values(status="receiving", lease=token, lease_until=now + 1800, error=None)
            ).rowcount
            return {**dict(row), "lease": token} if changed else None

    def run_once(self):
        item = self.claim()
        if item is None:
            return False
        with self.store.engine.connect() as c:
            batch = dict(
                c.execute(select(imports).where(imports.c.id == item["import_id"])).mappings().one()
            )
        source = item["source"]
        try:
            if not source["source_id"]:
                raise Problem(409, "UPLOAD_INTERRUPTED", "上传中断，请重新选择原文件重试")
            with self.open_source(
                batch["actor"], batch["project_id"], source["source_id"], source["path"]
            ) as stream:
                before = os.fstat(stream.fileno())
                if source.get("observed_stat") != [
                    before.st_dev,
                    before.st_ino,
                    before.st_size,
                    before.st_mtime_ns,
                ]:
                    raise Problem(409, "SOURCE_CHANGED", "源文件自选择后已变化，请以新批次接入")

                def unchanged():
                    # Recheck the grant before registration, including long file reads.
                    self._root(batch["actor"], batch["project_id"], source["source_id"])
                    after = os.fstat(stream.fileno())
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise Problem(409, "SOURCE_CHANGED", "源文件读取期间变化，请重试新版本")

                self.process(batch, item, stream, unchanged)
        except Exception as exc:
            # Errors before process (e.g. withdrawn source permission) are durable too.
            problem = (
                exc
                if isinstance(exc, Problem)
                else Problem(422, "SOURCE_READ_FAILED", "本地来源读取失败")
            )
            if not isinstance(exc, Problem):
                logger.exception("Local import %s failed", item["id"])
            with self.store.engine.begin() as c:
                c.execute(
                    update(items)
                    .where(items.c.id == item["id"], items.c.lease == item["lease"])
                    .values(
                        status="failed",
                        lease_until=None,
                        error={"code": problem.code, "message": problem.message},
                    )
                )
        return True


def router(store):
    routes, service = APIRouter(), BatchIntake(store)

    @routes.get("/api/projects/{project}/local-sources")
    def sources(project: str, request: Request):
        return service.sources(request.state.actor["id"], project)

    @routes.get("/api/projects/{project}/local-sources/{source}/files")
    def browse(
        project: str,
        source: str,
        request: Request,
        path: str = "",
        offset: int = 0,
        search: str = "",
    ):
        if offset < 0:
            raise Problem(422, "OFFSET_INVALID", "页偏移不能为负数")
        return service.browse(request.state.actor["id"], project, source, path, offset, search)

    @routes.post("/api/projects/{project}/imports", status_code=201)
    def create(project: str, body: NewImport, request: Request):
        return service.create(request.state.actor["id"], project, body.model_dump())

    @routes.get("/api/tasks/{task_id}/imports")
    def task_batches(task_id: str, request: Request):
        actor = request.state.actor["id"]
        store.task(actor, task_id)
        with store.engine.connect() as c:
            return [
                service.read(actor, batch_id)
                for batch_id in c.scalars(
                    select(imports.c.id)
                    .where(imports.c.task_id == task_id)
                    .order_by(imports.c.created.desc())
                )
            ]

    @routes.get("/api/imports/{batch_id}")
    def read(batch_id: str, request: Request):
        return service.read(request.state.actor["id"], batch_id)

    @routes.post("/api/imports/{batch_id}/items/{item_id}/content")
    def upload(batch_id: str, item_id: str, request: Request, file: Annotated[UploadFile, File()]):
        batch = service.read(request.state.actor["id"], batch_id, write=True)
        current = next((i for i in batch["items"] if i["id"] == item_id), None)
        if current is None:
            raise Problem(404, "ITEM_UNAVAILABLE", "文件项不可用")
        if current["source"]["source_id"]:
            raise Problem(422, "SOURCE_KIND", "本地目录项由服务端读取")
        if file.size != current["source"]["size"]:
            raise Problem(409, "SOURCE_CHANGED", "重新选择的文件大小不同，请建立新批次")
        if current["asset_id"]:
            digest = hashlib.sha256()
            while chunk := file.file.read(1024**2):
                digest.update(chunk)
            asset = service.intake.read_asset(request.state.actor["id"], current["asset_id"])
            if digest.hexdigest() != asset["sha256"]:
                raise Problem(409, "SOURCE_CHANGED", "重试文件字节与已接入项不同，请建立新批次")
            file.file.seek(0)
        if current["status"] == "ready":
            return current
        item = service.claim(batch_id, item_id)
        if item is None:
            raise Problem(409, "IMPORT_BUSY", "此文件仍在接入，请稍候查看状态")
        return service.process(batch, item, file.file)

    @routes.post("/api/imports/{batch_id}/items/{item_id}/retry")
    def retry(batch_id: str, item_id: str, request: Request):
        batch = service.read(request.state.actor["id"], batch_id, write=True)
        current = next((i for i in batch["items"] if i["id"] == item_id), None)
        if current is None:
            raise Problem(404, "ITEM_UNAVAILABLE", "文件项不可用")
        if current["source"]["source_id"]:
            service._root(
                request.state.actor["id"], batch["project_id"], current["source"]["source_id"]
            )
        if current["status"] != "failed":
            raise Problem(409, "ITEM_STATE", "仅重试已失败项目")
        with store.engine.begin() as c:
            c.execute(
                update(items)
                .where(items.c.id == item_id, items.c.status == "failed")
                .values(
                    status="queued" if current["source"]["source_id"] else "awaiting_upload",
                    error=None,
                )
            )
        return service.read(request.state.actor["id"], batch_id)

    return routes
