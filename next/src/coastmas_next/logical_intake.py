"""Immutable TIFF packages assembled from verified resumable upload sessions."""

import hashlib
import json
import math
import os
import re
import shutil
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath

import rasterio
from affine import Affine
from fastapi import APIRouter, Request
from pydantic import Field, field_validator
from sqlalchemy import JSON, Column, ForeignKey, String, Table, insert, select, update

from .asset_integrity import hash_file
from .contracts import Contract
from .intake import Intake, assets
from .management_catalog import require_available
from .profiles import inspect_file
from .store import Problem, audit_event, identifier, metadata
from .upload_sessions import PartReader, Uploads, uploads

packages = Table(
    "logical_import_receipts",
    metadata,
    Column("project_id", ForeignKey("projects.id"), primary_key=True),
    Column("actor", ForeignKey("accounts.id"), primary_key=True),
    Column("intent", String, primary_key=True),
    Column("fingerprint", String, nullable=False),
    Column("response", JSON, nullable=False),
)


def sidecar(name):
    return name.lower().endswith(
        (
            ".tfw",
            ".tifw",
            ".tiffw",
            ".wld",
            ".aux.xml",
            ".ovr",
            ".msk",
            ".shx",
            ".dbf",
            ".prj",
            ".cpg",
        )
    )


class PackageMember(Contract):
    upload_id: str
    relative_path: str = Field(min_length=1, max_length=1000)

    @field_validator("relative_path")
    @classmethod
    def safe_path(cls, value):
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in value
            or ":" in value
            or str(path) != value
            or any(ord(c) < 32 for c in value)
        ):
            raise ValueError("只允许无路径穿越的规范相对路径")
        return value


class CompletePackage(Contract):
    idempotency_key: str = Field(min_length=1, max_length=100)
    members: list[PackageMember] = Field(min_length=1, max_length=16)
    previous_asset_id: str | None = None


def package_members(body):
    paths = [PurePosixPath(m.relative_path) for m in body.members]
    if len({str(p).casefold() for p in paths}) != len(paths):
        raise Problem(422, "PACKAGE_DUPLICATE", "包内路径重复或大小写冲突。")
    mains = [p for p in paths if p.suffix.lower() in {".tif", ".tiff", ".shp"}]
    if len(mains) != 1:
        raise Problem(
            422, "SIDECAR_REQUIRES_PRIMARY", "请选择一份TIFF主件及其附件；孤立附件保留待补主件。"
        )
    main = mains[0]
    if main.suffix.lower() == ".shp":
        suffixes = {".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".sbn", ".sbx"}
        if any(
            p.parent != main.parent
            or p.stem.casefold() != main.stem.casefold()
            or p.suffix.lower() not in suffixes
            for p in paths
        ):
            raise Problem(422, "PACKAGE_ASSOCIATION", "Shapefile成员必须属于同一目录、同一名称。")
        missing = {".shp", ".shx", ".dbf"} - {p.suffix.lower() for p in paths}
        if missing:
            raise Problem(
                422,
                "SHAPEFILE_MEMBERS",
                "地物资料缺少成员：" + "、".join(sorted(missing)),
                {"missing": sorted(missing)},
            )
        return main
    allowed = {
        str(main).casefold(),
        (str(main) + ".aux.xml").casefold(),
        (str(main) + ".ovr").casefold(),
        (str(main) + ".msk").casefold(),
        str(main.with_suffix(".tfw")).casefold(),
        (str(main) + "w").casefold(),
        str(main.with_suffix(".wld")).casefold(),
    }
    if any(str(p).casefold() not in allowed for p in paths):
        raise Problem(
            422, "PACKAGE_ASSOCIATION", "附件必须与主件位于同一相对目录且名称对应，不能跨目录配对。"
        )
    return main


def world_transform(path):
    if path.stat().st_size > 4096:
        raise Problem(422, "WORLDFILE_INVALID", "定位附件超出合理长度。")
    try:
        a, d, b, e, x, y = [float(v) for v in path.read_text(encoding="utf-8-sig").split()]
        if not all(math.isfinite(v) for v in [a, d, b, e, x, y]) or a * e - b * d == 0:
            raise ValueError("degenerate grid")
        return Affine(a, b, x - (a + b) / 2, d, e, y - (d + e) / 2)
    except (ValueError, UnicodeError) as exc:
        raise Problem(
            422, "WORLDFILE_INVALID", "定位附件必须包含六个有限数值和非退化网格。"
        ) from exc


def pam_facts(path):
    if path.stat().st_size > 8 * 1024**2:
        raise Problem(422, "PAM_LIMIT", "PAM元数据超过8MiB安全预算。")
    try:
        text = path.read_text(encoding="utf-8-sig")
        if re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.I):
            raise ValueError("entity declaration")
        root = ET.fromstring(text)
        if root.tag != "PAMDataset":
            raise ValueError("not PAM")
        if any(
            e.tag in {"SourceFilename", "SourceDataset", "VRTDataset", "VRTRasterBand", "Overview"}
            or e.attrib.get("domain", "").upper() in {"GEOLOCATION", "RPC", "SUBDATASETS"}
            for e in root.iter()
        ):
            raise ValueError("external reference or unimplemented geolocation")
        crs = rasterio.crs.CRS.from_string(root.findtext("SRS")) if root.findtext("SRS") else None
        value = root.findtext("GeoTransform")
        transform = Affine.from_gdal(*[float(v) for v in value.split(",")]) if value else None
        if transform and (
            not all(math.isfinite(v) for v in transform) or transform.determinant == 0
        ):
            raise ValueError("invalid grid")
        return crs, transform
    except (ValueError, UnicodeError, ET.ParseError, rasterio.errors.CRSError) as exc:
        raise Problem(
            422, "PAM_UNSAFE_OR_INVALID", "定位元数据无效或含外部引用；原件保留，需修复附件。"
        ) from exc


def prepare_reader(originals, reader, main, manifest):
    reader.mkdir()
    if main.suffix.lower() == ".shp":
        target = reader / (main.stem + ".zip")
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for entry in manifest:
                path = PurePosixPath(entry["path"])
                archive.write(originals / path, path.name)
                entry["role"] = "primary" if path == main else "vector_member"
        return target
    original = originals / main
    target = reader / main.name
    os.link(original, target)
    with rasterio.Env(GDAL_PAM_ENABLED="NO"):
        with rasterio.open(target, GEOREF_SOURCES="INTERNAL") as ds:
            native_crs, native_transform = ds.crs, ds.transform
            shape, count, types = (ds.height, ds.width), ds.count, ds.dtypes
    reference_crs = native_crs
    reference_transform = None if native_transform.is_identity else native_transform
    for entry in manifest:
        path = PurePosixPath(entry["path"])
        if path == main:
            entry["role"] = "primary"
            continue
        source = originals / path
        entry["role"] = "attachment"
        suffix = path.name.lower()
        if suffix.endswith((".tfw", ".tifw", ".tiffw", ".wld")):
            crs, transform = None, world_transform(source)
        elif suffix.endswith(".aux.xml"):
            crs, transform = pam_facts(source)
        elif suffix.endswith(".ovr"):
            try:
                with rasterio.open(source) as overview:
                    if (
                        overview.count != count
                        or overview.dtypes != types
                        or overview.width >= shape[1]
                        or overview.height >= shape[0]
                    ):
                        raise ValueError("overview shape/bands")
                os.link(source, reader / path.name)
                entry["role"] = "overview"
            except (ValueError, rasterio.errors.RasterioError):
                entry["role"] = "unused_overview"
                entry["warning"] = "金字塔无效，预览直接从主件读取；原附件保留。"
            continue
        elif suffix.endswith(".msk"):
            with rasterio.open(source) as mask:
                if (mask.height, mask.width) != shape or mask.count not in {1, count}:
                    raise Problem(422, "MASK_INVALID", "关键掩膜与主件网格或波段不一致，未放行。")
            os.link(source, reader / path.name)
            entry["role"] = "mask"
            continue
        else:
            raise Problem(422, "PACKAGE_MEMBER", "附件类型未声明。")
        if reference_crs and crs and reference_crs != crs:
            raise Problem(422, "LOCATION_CONFLICT", "主件与附件坐标参考系冲突，不能自动选用。")
        if (
            reference_transform
            and transform
            and not reference_transform.almost_equals(transform, precision=1e-10)
        ):
            raise Problem(422, "LOCATION_CONFLICT", "主件与附件网格冲突，不能自动覆盖定位。")
        reference_crs = reference_crs or crs
        reference_transform = reference_transform or transform
        os.link(source, reader / path.name)
        entry["role"] = "georeference_metadata"
    # This runtime intentionally prioritizes internal georeferencing. Where
    # only validated sidecars locate the source, create an explicit derived
    # reader file; never update a hardlink to an original received member.
    if (native_transform.is_identity and reference_transform is not None) or (
        native_crs is None and reference_crs is not None
    ):
        temporary = reader / "adapted-reader.tif"
        shutil.copyfile(target, temporary)
        with rasterio.Env(GDAL_PAM_ENABLED="NO"):
            with rasterio.open(temporary, "r+") as adapted:
                if reference_transform is not None:
                    adapted.transform = reference_transform
                if reference_crs is not None:
                    adapted.crs = reference_crs
        os.replace(temporary, target)
        next(member for member in manifest if member["path"] == str(main))["reader_adaptation"] = (
            "validated_sidecar_georeference_embedded; original_bytes_retained"
        )
    return target


def complete_package(store, actor, project, body, *, commit_guard=None):
    main = package_members(body)
    fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    service = Uploads(store)
    lease = identifier()
    with store.engine.begin() as c:
        store.permission(c, actor, project, write=True)
        require_available(c, "projects", project)
        if body.previous_asset_id:
            from .resource_catalog import require_active

            previous = Intake(store).read_asset(actor, body.previous_asset_id, c)
            if previous["project_id"] != project:
                raise Problem(404, "ASSET_UNAVAILABLE", "资料不属于本项目")
            require_active(c, body.previous_asset_id)
        old = (
            c.execute(
                select(packages).where(
                    packages.c.project_id == project,
                    packages.c.actor == actor,
                    packages.c.intent == body.idempotency_key,
                )
            )
            .mappings()
            .first()
        )
        if old:
            if old["fingerprint"] != fingerprint:
                raise Problem(409, "PACKAGE_INTENT_CONFLICT", "同一接入请求不能改用其他成员。")
            return old["response"]
        rows = []
        for member in body.members:
            row = service.owned(c, actor, member.upload_id, write=True)
            if (
                row["project_id"] != project
                or PurePosixPath(member.relative_path).name != row["name"]
            ):
                raise Problem(422, "PACKAGE_MEMBER", "上传与项目或成员名称不一致。")
            if row["status"] in {"ready", "cancelled"}:
                raise Problem(
                    409,
                    "PACKAGE_MEMBER_STATE",
                    "成员已完成其他接入或已取消，请选择原件建立新版本。",
                )
            if row["status"] == "committing" and (row["lease_until"] or 0) > time.time():
                raise Problem(409, "PACKAGE_BUSY", "成员正在提交，可稍后以相同请求恢复。")
            if sum(p["size"] for p in row["parts"].values()) != row["size"]:
                raise Problem(
                    409,
                    "UPLOAD_INCOMPLETE",
                    "成员分段尚未收齐，可继续上传。",
                    {"upload_id": row["id"]},
                )
            c.execute(
                update(uploads)
                .where(uploads.c.id == row["id"])
                .values(status="committing", lease=lease, lease_until=time.time() + 1800)
            )
            rows.append((member, row))
    root = store.settings.storage_root
    staging = root / ("package-staging-" + lease)
    staging.mkdir()
    originals = staging / "originals"
    originals.mkdir()
    try:
        manifest = []
        for member, row in rows:
            target = originals / member.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            digest, size = hashlib.sha256(), 0
            with (
                PartReader(service.root(row["id"]), row["parts"]) as stream,
                target.open("xb") as out,
            ):
                while chunk := stream.read(1024**2):
                    size += len(chunk)
                    digest.update(chunk)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            if size != row["size"]:
                raise Problem(409, "SOURCE_CHANGED", "包内成员实际长度变化，未发布混合快照。")
            manifest.append(
                {"path": member.relative_path, "sha256": digest.hexdigest(), "size": size}
            )
        target = prepare_reader(originals, staging / "reader", main, manifest)
        facts = inspect_file(target)
        reader_members = [
            {
                "path": str(file.relative_to(staging / "reader")),
                "sha256": hash_file(file),
                "size": file.stat().st_size,
            }
            for file in sorted((staging / "reader").rglob("*"))
            if file.is_file()
        ]
        package_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        relative = Path("packages") / project / identifier()
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.rename(staging, destination)
        primary = next(m for m in manifest if m["path"] == str(main))
        facts["logical_package"] = {
            "sha256": package_hash,
            "primary": str(main),
            "members": [
                {**m, "object_key": str(relative / "originals" / m["path"])} for m in manifest
            ],
            "reader_members": [
                {**member, "object_key": str(relative / "reader" / member["path"])}
                for member in reader_members
            ],
            "previous_asset_id": body.previous_asset_id,
        }
        with store.engine.begin() as c:
            store.permission(c, actor, project, write=True)
            require_available(c, "projects", project)
            if commit_guard is not None:
                commit_guard(c)
            revision = 1
            if body.previous_asset_id:
                previous = Intake(store).read_asset(actor, body.previous_asset_id, c)
                if previous["project_id"] != project:
                    raise Problem(422, "PROJECT_MISMATCH", "新版本与原资料必须属于同一项目。")
                revision = previous["revision"] + 1
            asset = {
                "id": identifier(),
                "project_id": project,
                "revision": revision,
                "name": main.name,
                "sha256": primary["sha256"],
                "size": primary["size"],
                "object_key": str(relative / "reader" / target.name),
                "facts": facts,
                "created": time.time(),
            }
            c.execute(insert(assets).values(**asset))
            for _, row in rows:
                if (
                    c.execute(
                        update(uploads)
                        .where(uploads.c.id == row["id"], uploads.c.lease == lease)
                        .values(
                            status="ready",
                            asset_id=asset["id"],
                            lease=None,
                            lease_until=None,
                            error=None,
                        )
                    ).rowcount
                    != 1
                ):
                    raise Problem(409, "UPLOAD_LEASE", "成员处理资格已变化，请重新查询。")
            response = {"asset": asset, "members": len(manifest)}
            c.execute(
                insert(packages).values(
                    project_id=project,
                    actor=actor,
                    intent=body.idempotency_key,
                    fingerprint=fingerprint,
                    response=response,
                )
            )
            audit_event(c, actor, project, "ingest_logical_asset", asset["id"])
        for _, row in rows:
            for index in row["parts"]:
                (service.root(row["id"]) / index).unlink(missing_ok=True)
        return response
    except Exception as exc:
        problem = (
            exc
            if isinstance(exc, Problem)
            else Problem(422, "PACKAGE_INVALID", "逻辑资料读取失败，分段和原件保留，可修复后重试。")
        )
        with store.engine.begin() as c:
            c.execute(
                update(uploads)
                .where(uploads.c.lease == lease)
                .values(
                    status="failed",
                    lease=None,
                    lease_until=None,
                    error={"code": problem.code, "message": problem.message},
                )
            )
        raise problem from exc
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def router(store):
    routes = APIRouter()

    @routes.post("/api/projects/{project}/logical-imports", status_code=201)
    def complete(project: str, body: CompletePackage, request: Request):
        return complete_package(store, request.state.actor["id"], project, body)

    return routes
