"""Explicit association of received attachments with authorized managed originals."""

import hashlib
import io
import re
import threading
from pathlib import PurePosixPath

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import select, update

from .asset_integrity import verify_asset
from .contracts import Contract
from .intake import Intake, assets
from .management_catalog import require_available
from .resource_catalog import asset_metadata, require_active
from .store import Problem, audit_event
from .upload_sessions import NewUpload, Uploads


class PrimaryChoice(Contract):
    asset_id: str
    revision: int = Field(ge=1)


def base_name(name):
    return re.sub(
        r"(?i)(\.tiff?(?:\.aux\.xml|\.ovr|\.msk|w)?|\.tfw|\.wld)$", "", PurePosixPath(name).name
    ).casefold()


def router(store, read):
    from .group_sessions import group_sessions

    routes = APIRouter()
    uploads = Uploads(store)

    @routes.get("/api/upload-groups/{group_id}/primary-candidates")
    def candidates(group_id: str, request: Request):
        actor = request.state.actor["id"]
        group = read(actor, group_id)
        names = {base_name(m["relative_path"]) for m in group["members"]}
        with store.engine.connect() as c:
            candidates = c.execute(
                select(assets).where(assets.c.project_id == group["project_id"])
            ).mappings()
            return [
                {k: a[k] for k in ("id", "name", "revision", "size", "facts")}
                for a in candidates
                if a["facts"]["profile"] in {"geotiff", "cog"}
                and base_name(a["name"]) in names
                and c.scalar(
                    select(asset_metadata.c.state).where(asset_metadata.c.asset_id == a["id"])
                )
                != "recycled"
            ]

    @routes.post("/api/upload-groups/{group_id}/primary")
    def associate(group_id: str, body: PrimaryChoice, request: Request):
        actor = request.state.actor["id"]
        group = read(actor, group_id)
        if group["asset_id"]:
            raise Problem(409, "PACKAGE_IMMUTABLE", "资料已完成，请建立新的解释版本。")
        with store.engine.begin() as c:
            source = Intake(store).read_asset(actor, body.asset_id, c)
            if source["project_id"] != group["project_id"]:
                raise Problem(404, "ASSET_UNAVAILABLE", "本项目中没有可关联资料。")
            require_available(c, "projects", group["project_id"])
            require_active(c, source["id"])
            if source["revision"] != body.revision:
                raise Problem(409, "SOURCE_CHANGED", "主资料版本已变化，请重新核对。")
        previous = [m for m in group["members"] if m.get("reused_asset_id")]
        if previous:
            if any(m["reused_asset_id"] != source["id"] for m in previous):
                raise Problem(
                    409, "PRIMARY_CHOICE_CHANGED", "本次关联已固定其他主件，请建立新的接入。"
                )
            return group
        if any(
            PurePosixPath(m["relative_path"]).suffix.lower() in {".tif", ".tiff"}
            for m in group["members"]
        ):
            raise Problem(409, "PRIMARY_ALREADY_SELECTED", "已选择主影像，不再关联另一个主件。")
        if source["facts"]["profile"] not in {"geotiff", "cog"}:
            raise Problem(422, "PRIMARY_TYPE", "定位附件需关联真实栅格主件。")
        if base_name(source["name"]) not in {
            base_name(m["relative_path"]) for m in group["members"]
        }:
            raise Problem(422, "PRIMARY_NAME", "附件与所选影像名称不匹配，请核对实际数据包关系。")
        verify_asset(store.settings.storage_root, source, threading.Event())
        package = source["facts"].get("logical_package")
        originals = (
            package["members"]
            if package
            else [
                {
                    "path": source["name"],
                    "object_key": source["object_key"],
                    "sha256": source["sha256"],
                    "size": source["size"],
                }
            ]
        )
        directory = PurePosixPath(group["members"][0]["relative_path"]).parent
        existing = {m["relative_path"] for m in group["members"]}
        added = []
        for original in originals:
            relative = str(directory / PurePosixPath(original["path"]).name)
            if relative in existing:
                continue
            session = uploads.create(
                actor,
                group["project_id"],
                NewUpload(
                    name=PurePosixPath(relative).name,
                    size=original["size"],
                    idempotency_key=hashlib.sha256(
                        f"{group_id}:{source['id']}:{relative}".encode()
                    ).hexdigest(),
                ),
            )
            path = (store.settings.storage_root / original["object_key"]).resolve()
            if not path.is_relative_to(store.settings.storage_root):
                raise Problem(422, "SOURCE_PATH", "受管资料位置不合法。")
            checksum = hashlib.sha256()
            with path.open("rb") as stream:
                index = 0
                while chunk := stream.read(session["chunk_size"]):
                    digest = hashlib.sha256(chunk).hexdigest()
                    checksum.update(chunk)
                    if session["parts"].get(str(index), {}).get("sha256") != digest:
                        uploads.part(actor, session["id"], index, io.BytesIO(chunk), digest)
                    index += 1
            if checksum.hexdigest() != original["sha256"]:
                raise Problem(409, "SOURCE_CHANGED", "受管原件校验不一致，关联未发布。")
            added.append(
                {
                    "upload_id": session["id"],
                    "relative_path": relative,
                    "reused_asset_id": source["id"],
                    "reused_revision": source["revision"],
                }
            )
        with store.engine.begin() as c:
            store.permission(c, actor, group["project_id"], write=True)
            require_available(c, "projects", group["project_id"])
            require_active(c, source["id"])
            current = (
                c.execute(
                    select(group_sessions).where(group_sessions.c.id == group_id).with_for_update()
                )
                .mappings()
                .one()
            )
            clean = [{k: v for k, v in m.items() if k != "upload"} for m in group["members"]]
            if current["members"] != clean or current["asset_id"]:
                raise Problem(409, "UPLOAD_GROUP_CONFLICT", "接入关系已变化，请重新读取。")
            c.execute(
                update(group_sessions)
                .where(group_sessions.c.id == group_id)
                .values(members=clean + added)
            )
            audit_event(c, actor, group["project_id"], "associate_managed_primary", source["id"])
        return read(actor, group_id)

    return routes
