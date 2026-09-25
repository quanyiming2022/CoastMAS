"""Durable grouping intent, independent of files, task drafts and display state."""

import hashlib
import json

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import JSON, Column, ForeignKey, String, Table, insert, select, update

from .contracts import Contract
from .logical_intake import CompletePackage, PackageMember, complete_package
from .store import Problem, accounts, metadata
from .upload_sessions import NewUpload, Uploads

group_sessions = Table(
    "upload_group_sessions",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", ForeignKey("projects.id"), nullable=False),
    Column("actor", ForeignKey("accounts.id"), nullable=False),
    Column("intent", String, nullable=False),
    Column("members", JSON, nullable=False),
    Column("asset_id", ForeignKey("assets.id")),
)


class GroupFile(PackageMember):
    upload_id: str = ""
    size: int = Field(ge=1)


class NewGroup(Contract):
    idempotency_key: str = Field(min_length=1, max_length=100)
    files: list[GroupFile] = Field(min_length=1, max_length=10)


def router(store):
    routes, service = APIRouter(), Uploads(store)

    def read(actor, group_id):
        with store.engine.connect() as c:
            row = (
                c.execute(
                    select(group_sessions).where(
                        group_sessions.c.id == group_id, group_sessions.c.actor == actor
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise Problem(404, "UPLOAD_GROUP_UNAVAILABLE", "接入组不可用。")
            store.permission(c, actor, row["project_id"], write=True)
            return {
                **dict(row),
                "members": [
                    {
                        **member,
                        "upload": service.public(service.owned(c, actor, member["upload_id"])),
                    }
                    for member in row["members"]
                ],
            }

    @routes.post("/api/projects/{project}/upload-groups", status_code=201)
    def create(project: str, body: NewGroup, request: Request):
        actor = request.state.actor["id"]
        group_id = hashlib.sha256(
            json.dumps([project, actor, body.idempotency_key]).encode()
        ).hexdigest()[:32]
        # Each member has its own durable resumable intent, so a lost group-create
        # response or interrupted allocation reuses already reserved uploads.
        members = []
        for source in body.files:
            upload = service.create(
                actor,
                project,
                NewUpload(
                    name=source.relative_path.split("/")[-1],
                    size=source.size,
                    idempotency_key=hashlib.sha256(
                        (group_id + source.relative_path).encode()
                    ).hexdigest(),
                ),
            )
            members.append({"upload_id": upload["id"], "relative_path": source.relative_path})
        with store.engine.begin() as c:
            store.permission(c, actor, project, write=True)
            c.execute(update(accounts).where(accounts.c.id == actor).values(id=actor))
            old = (
                c.execute(select(group_sessions).where(group_sessions.c.id == group_id))
                .mappings()
                .first()
            )
            if old:
                if old["members"] != members:
                    raise Problem(409, "UPLOAD_GROUP_CONFLICT", "同一接入组标识不能改用其他成员。")
            else:
                c.execute(
                    insert(group_sessions).values(
                        id=group_id,
                        project_id=project,
                        actor=actor,
                        intent=body.idempotency_key,
                        members=members,
                        asset_id=None,
                    )
                )
        return read(actor, group_id)

    @routes.get("/api/projects/{project}/upload-groups")
    def listing(project: str, request: Request):
        actor = request.state.actor["id"]
        with store.engine.connect() as c:
            store.permission(c, actor, project)
            ids = list(
                c.scalars(
                    select(group_sessions.c.id).where(
                        group_sessions.c.project_id == project,
                        group_sessions.c.actor == actor,
                        group_sessions.c.asset_id.is_(None),
                    )
                )
            )
        return [read(actor, group_id) for group_id in ids]

    @routes.get("/api/upload-groups/{group_id}")
    def detail(group_id: str, request: Request):
        return read(request.state.actor["id"], group_id)

    @routes.post("/api/upload-groups/{group_id}/complete")
    def complete(group_id: str, request: Request):
        actor = request.state.actor["id"]
        group = read(actor, group_id)
        response = complete_package(
            store,
            actor,
            group["project_id"],
            CompletePackage(
                idempotency_key="group:" + group_id,
                previous_asset_id=next(
                    (
                        m.get("reused_asset_id")
                        for m in group["members"]
                        if m.get("reused_asset_id")
                    ),
                    None,
                ),
                members=[
                    PackageMember(upload_id=m["upload_id"], relative_path=m["relative_path"])
                    for m in group["members"]
                ],
            ),
        )
        with store.engine.begin() as c:
            store.permission(c, actor, group["project_id"], write=True)
            c.execute(
                update(group_sessions)
                .where(group_sessions.c.id == group_id)
                .values(asset_id=response["asset"]["id"])
            )
        return response

    @routes.post("/api/upload-groups/{group_id}/members")
    def supplement(group_id: str, body: NewGroup, request: Request):
        actor = request.state.actor["id"]
        group = read(actor, group_id)
        if group["asset_id"]:
            raise Problem(409, "PACKAGE_IMMUTABLE", "已完成资料不可改写，请建立新的资料版本。")
        added = []
        for source in body.files:
            if any(m["relative_path"] == source.relative_path for m in group["members"]):
                raise Problem(409, "PACKAGE_DUPLICATE", "此成员已存在，请继续原上传。")
            upload = service.create(
                actor,
                group["project_id"],
                NewUpload(
                    name=source.relative_path.split("/")[-1],
                    size=source.size,
                    idempotency_key=hashlib.sha256(
                        (group_id + source.relative_path).encode()
                    ).hexdigest(),
                ),
            )
            added.append({"upload_id": upload["id"], "relative_path": source.relative_path})
        with store.engine.begin() as c:
            store.permission(c, actor, group["project_id"], write=True)
            c.execute(update(accounts).where(accounts.c.id == actor).values(id=actor))
            current = (
                c.execute(select(group_sessions).where(group_sessions.c.id == group_id))
                .mappings()
                .one()
            )
            if current["asset_id"] or current["members"] != [
                {k: v for k, v in m.items() if k != "upload"} for m in group["members"]
            ]:
                raise Problem(409, "UPLOAD_GROUP_CONFLICT", "接入组已变化，请重新读取。")
            c.execute(
                update(group_sessions)
                .where(group_sessions.c.id == group_id)
                .values(members=current["members"] + added)
            )
        return read(actor, group_id)

    from .group_primary import router as primary_router

    routes.include_router(primary_router(store, read))
    return routes
