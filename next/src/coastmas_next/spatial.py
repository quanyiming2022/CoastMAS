"""Deterministic, full-grid spatial operators with explicit output contracts."""

import hashlib
from typing import Literal

import rasterio
from pydantic import Field, ValidationError
from rasterio.windows import Window

from .contracts import Contract
from .geospatial_view import band_check, data_mask, georeference
from .store import Problem


class SpatialOptions(Contract):
    operator: Literal["valid_mask"]
    band: int = Field(default=1, ge=1)


def preflight(settings, draft, sources):
    if draft["options"].get("operator") == "planning_units":
        from .planning_units import preflight as unit_preflight

        return unit_preflight(settings, draft, sources)
    if draft["options"].get("operator") == "builtin_indicator":
        from .indicator_kernels_v1 import preflight as indicator_preflight

        return indicator_preflight(settings, draft, sources)
    if draft["options"].get("operator") in {"align_grid", "ndvi", "score"}:
        from .preparation import preflight as preparation_preflight

        return preparation_preflight(settings, draft, sources)
    try:
        options = SpatialOptions.model_validate(draft["options"])
    except ValidationError as exc:
        raise Problem(422, "SPATIAL_OPTIONS", "请选择空间处理工具和有效波段") from exc
    if len(sources) != 1 or sources[0]["facts"]["profile"] not in {"geotiff", "cog"}:
        raise Problem(422, "SPATIAL_SOURCE", "有效覆盖工具需要一份真实栅格资料")
    with rasterio.open(settings.storage_root / sources[0]["object_key"]) as ds:
        band_check(ds, options.band)
        status, _, issue = georeference(ds)
        if status != "located":
            raise Problem(422, "SPATIAL_LOCATION", issue)
    return {
        "id": "builtin:valid-mask:1",
        "version": 1,
        "operator": options.operator,
        "basis": "源波段有效掩膜、NoData、有限值及alpha联合有效性；保持原生网格",
        "expected_outputs": [
            {"name": "valid-coverage.tif", "view_kind": "raster", "role": "result"}
        ],
    }


def compute(settings, manifest, cancelled, artifact_dir):
    if manifest["draft"]["options"].get("operator") == "planning_units":
        from .planning_units import compute as unit_compute

        return unit_compute(settings, manifest, cancelled, artifact_dir)
    if manifest["draft"]["options"].get("operator") == "builtin_indicator":
        from .builtin_operators import BuiltinOperatorRegistry

        return BuiltinOperatorRegistry.compute_indicator(
            settings, manifest, cancelled, artifact_dir
        )
    if manifest["draft"]["options"].get("operator") in {"align_grid", "ndvi", "score"}:
        from .preparation import compute as preparation_compute

        return preparation_compute(settings, manifest, cancelled, artifact_dir)
    method = preflight(settings, manifest["draft"], manifest["assets"])
    options = SpatialOptions.model_validate(manifest["draft"]["options"])
    source = manifest["assets"][0]
    if cancelled.is_set():
        raise Problem(409, "CANCELLED", "运行已取消")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    output = artifact_dir / method["expected_outputs"][0]["name"]
    valid_count = 0
    with (
        rasterio.Env(GDAL_CACHEMAX=64 * 1024**2),
        rasterio.open(settings.storage_root / source["object_key"]) as ds,
    ):
        with rasterio.open(
            output,
            "w",
            driver="GTiff",
            width=ds.width,
            height=ds.height,
            count=1,
            dtype="uint8",
            crs=ds.crs,
            transform=ds.transform,
            nodata=None,
            tiled=True,
            blockxsize=512,
            blockysize=512,
            compress="deflate",
        ) as target:
            for row in range(0, ds.height, 1024):
                for column in range(0, ds.width, 1024):
                    if cancelled.is_set():
                        raise Problem(409, "CANCELLED", "运行已取消")
                    window = Window(
                        column, row, min(1024, ds.width - column), min(1024, ds.height - row)
                    )
                    _, valid = data_mask(ds, options.band, window=window)
                    valid_count += int(valid.sum())
                    target.write(valid.astype("uint8"), 1, window=window)
            target.set_band_description(1, "source_validity")
            target.set_band_unit(1, "1")
            target.write_colormap(1, {0: (225, 232, 236, 255), 1: (5, 143, 145, 255)})
            target.update_tags(
                operator="valid_mask",
                operator_version="1",
                source_sha256=source["sha256"],
                source_band=options.band,
                categories="0=invalid_source;1=valid_source",
                scope="full_grid",
            )
        total = ds.width * ds.height
    with output.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "scope": "full_grid",
        "operator": "valid_mask",
        "method": method,
        "statistics": {
            "total_pixels": total,
            "valid_pixels": valid_count,
            "invalid_pixels": total - valid_count,
            "scope": "full_grid",
        },
        "files": [
            {
                "name": output.name,
                "key": str(output.relative_to(settings.storage_root)),
                "sha256": digest,
                "size": output.stat().st_size,
                "role": "result",
                "view_kind": "raster",
            }
        ],
    }


def validate_outputs(manifest, data, root):
    if manifest["draft"]["options"].get("operator") == "planning_units":
        from .planning_units import validate_outputs as validate_units

        return validate_units(manifest, data, root)
    if manifest["draft"]["options"].get("operator") == "builtin_indicator":
        from .indicator_kernels_v1 import validate_outputs as validate_indicator

        return validate_indicator(manifest, data, root)
    if manifest["draft"]["options"].get("operator") in {"align_grid", "ndvi", "score"}:
        from .preparation import validate_outputs as validate_preparation

        return validate_preparation(manifest, data, root)
    expected = manifest.get("method", {}).get("expected_outputs") or [
        {"name": "valid-coverage.tif"}
    ]
    files = data.get("files", [])
    if [f.get("name") for f in files] != [f["name"] for f in expected]:
        raise Problem(422, "OUTPUT_CONTRACT", "实际产物与本次声明的必要输出不一致")
    facts = manifest["assets"][0]["facts"]
    for item in files:
        path = (root / item["key"]).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise Problem(422, "OUTPUT_CONTRACT", "必要成果缺失或越界")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != item["sha256"] or path.stat().st_size != item["size"]:
            raise Problem(422, "OUTPUT_CONTRACT", "成果字节与声明不一致")
        with rasterio.open(path) as ds:
            if (
                ds.width != facts["width"]
                or ds.height != facts["height"]
                or list(ds.transform)[:6] != facts["transform"]
                or ds.crs.to_string() != facts["crs"]
                or ds.count != 1
                or ds.dtypes[0] != "uint8"
            ):
                raise Problem(422, "OUTPUT_CONTRACT", "覆盖成果的网格、坐标或数据类型错误")
        stats = data.get("statistics", {})
        if stats.get("total_pixels") != facts["width"] * facts["height"] or stats.get(
            "valid_pixels", -1
        ) + stats.get("invalid_pixels", -1) != stats.get("total_pixels"):
            raise Problem(422, "OUTPUT_CONTRACT", "成果全域分母不一致")


class StartSpatial(Contract):
    asset_id: str
    band: int = Field(default=1, ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


def router(store):
    import time

    from fastapi import APIRouter, Request
    from sqlalchemy import insert, select

    from .contracts import TaskDraft
    from .intake import Intake
    from .resource_catalog import require_active
    from .store import audit_event, projects, revisions, tasks

    routes = APIRouter()

    @routes.post("/api/projects/{project}/spatial-tasks", status_code=201)
    def start(project: str, body: StartSpatial, request: Request):
        actor = request.state.actor["id"]
        task_id = hashlib.sha256(f"{actor}:{project}:{body.idempotency_key}".encode()).hexdigest()[
            :32
        ]
        with store.engine.begin() as c:
            c.execute(
                select(projects.c.id).where(projects.c.id == project).with_for_update()
            ).first()
            store.permission(c, actor, project, write=True)
            asset = Intake(store).read_asset(actor, body.asset_id, c)
            if asset["project_id"] != project:
                raise Problem(404, "ASSET_UNAVAILABLE", "资料不可用")
            draft = TaskDraft(
                title=("有效覆盖 · " + asset["name"])[:200],
                purpose="spatial",
                selection=[{"asset_id": asset["id"], "revision": asset["revision"]}],
                options={"operator": "valid_mask", "band": body.band},
            ).model_dump(mode="json")
            existing = c.execute(
                select(revisions.c.draft).where(
                    revisions.c.task_id == task_id, revisions.c.revision == 1
                )
            ).scalar()
            if existing is not None:
                if existing != draft:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT", "此操作意图对应不同的资料或波段")
                return store.task(actor, task_id, connection=c)
            require_active(c, asset["id"])
            preflight(store.settings, draft, [asset])
            now = time.time()
            c.execute(
                insert(tasks).values(
                    id=task_id, project_id=project, revision=1, draft=draft, updated=now
                )
            )
            c.execute(
                insert(revisions).values(
                    task_id=task_id, revision=1, draft=draft, actor=actor, created=now
                )
            )
            audit_event(c, actor, project, "create_spatial_task", task_id)
            return store.task(actor, task_id, connection=c)

    return routes
