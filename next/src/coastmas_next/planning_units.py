"""Full-layer planning units. Preparation is not diagnosis or a planning solution."""

import hashlib
import json
import math
import time

from fastapi import APIRouter, Request
from pydantic import ValidationError
from pyproj import CRS, Geod
from shapely.geometry import shape
from shapely.geometry.polygon import orient
from shapely.strtree import STRtree
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
    select,
    update,
)

from .contracts import Contract
from .observations import read_rows
from .planning_versions import immutable
from .selection import selected_layer
from .store import Problem, audit_event, metadata
from .vector_view import display_geometry

VERSION = "1.0.0"
MAX_UNITS = 100000
MAX_INTERSECTION_PAIRS = 5000000
GEOD = Geod(ellps="WGS84")

sets = Table(
    "planning_unit_sets",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", ForeignKey("projects.id"), nullable=False),
    Column("source_asset_id", ForeignKey("assets.id"), nullable=False),
    Column("layer", String, nullable=False),
    Column("revision", Integer, nullable=False),
    UniqueConstraint("project_id", "source_asset_id", "layer"),
)
versions = Table(
    "planning_unit_set_revisions",
    metadata,
    Column("id", String, primary_key=True),
    Column("object_id", ForeignKey("planning_unit_sets.id"), nullable=False),
    Column("project_id", ForeignKey("projects.id"), nullable=False),
    Column("task_id", ForeignKey("tasks.id"), nullable=False),
    Column("job_id", ForeignKey("jobs.id"), nullable=False, unique=True),
    Column("version", Integer, nullable=False),
    Column("source", JSON, nullable=False),
    Column("unit_count", Integer, nullable=False),
    Column("geometry_type", String, nullable=False),
    Column("algorithm_version", String, nullable=False),
    Column("sha256", String, nullable=False),
    Column("object_key", String, nullable=False),
    Column("created", Float, nullable=False),
    UniqueConstraint("object_id", "version"),
)
immutable(versions)


class UnitOptions(Contract):
    # An empty contract intentionally rejects hidden geometry-fixing, sampling,
    # zero-filling, or policy parameters. Inputs define the full domain.
    pass


def validate_options(value):
    try:
        return UnitOptions.model_validate(value)
    except ValidationError as exc:
        raise Problem(422, "UNIT_PARAMETERS", "规划单元准备不接受隐藏的采样或跳过校验参数") from exc


def preflight(settings, draft, sources):
    validate_options(draft["options"].get("parameters", {}))
    if len(sources) != 1:
        raise Problem(422, "UNIT_SOURCE_REQUIRED", "请选择一份已有规划分区或设施候选点资料")
    asset = sources[0]
    if asset["facts"]["profile"] not in {"geojson", "geopackage", "shapefile", "csv", "csvw"}:
        raise Problem(
            422,
            "UNIT_SOURCE_PROFILE",
            "当前单元准备支持真实矢量或已关联坐标的表；栅格划分服务尚未接通",
        )
    if asset["facts"]["profile"] in {"csv", "csvw"} and not draft["options"].get(
        "spatial_reference"
    ):
        raise Problem(422, "UNIT_LOCATION_REQUIRED", "此表尚无可靠坐标关联；不能猜测规划单元位置")
    layer = selected_layer(asset, draft)
    return {
        "id": "builtin:planning-units:1",
        "version": VERSION,
        "operator": "planning_units",
        "layer": layer["name"],
        "scope": "full_layer",
        "maximum_units": MAX_UNITS,
        "basis": "逐要素保留原生几何与字段；多边形计算面积并检查重叠；不推测成本、类别或时期",
        "expected_outputs": [
            {"name": "planning-units.json", "role": "planning_units", "view_kind": "table"},
            {"name": "planning-units.geojson", "role": "planning_units", "view_kind": "vector"},
        ],
    }


def check_cancel(cancel):
    if cancel.is_set():
        raise Problem(409, "CANCELLED", "规划单元准备已取消")


def area_m2(native, crs, displayed):
    if native.geom_type == "Point":
        return None, "not_applicable_point"
    reference = CRS.from_user_input(crs)
    if reference.is_projected and len(reference.axis_info) >= 2:
        x, y = [axis.unit_conversion_factor for axis in reference.axis_info[:2]]
        if not all(math.isfinite(v) and v > 0 for v in (x, y)):
            raise Problem(422, "UNIT_AREA_UNIT", "无法确认原生投影坐标的长度单位")
        area, basis = native.area * x * y, "native_projected_plane"
    else:
        if displayed.bounds[2] - displayed.bounds[0] >= 180:
            raise Problem(422, "UNIT_ANTIMERIDIAN", "跨半球几何需明确分割规则，未自动修复")
        polygons = list(displayed.geoms) if displayed.geom_type == "MultiPolygon" else [displayed]
        area = math.fsum(abs(GEOD.geometry_area_perimeter(orient(p, sign=1))[0]) for p in polygons)
        basis = "WGS84_ellipsoid_geodesic_edges"
    if not math.isfinite(area) or area <= 0:
        raise Problem(422, "UNIT_AREA_INVALID", "规划单元面积无效")
    return area, basis


def compute(settings, manifest, cancelled, artifact_dir):
    method = preflight(settings, manifest["draft"], manifest["assets"])
    rows, _ = read_rows(settings, manifest, limit=MAX_UNITS)
    units, native_shapes, features, kinds = [], [], [], set()
    for index, row in enumerate(rows):
        check_cancel(cancelled)
        display, issue = display_geometry(row["geometry"], row["geometry_crs"])
        if issue:
            raise Problem(
                422,
                "UNIT_GEOMETRY_INVALID",
                "规划单元几何或定位无效，未静默丢弃",
                {"unit": row["id"], "reason": issue},
            )
        native, shown = shape(row["geometry"]), shape(display)
        kind = (
            "polygon"
            if native.geom_type in {"Polygon", "MultiPolygon"}
            else "point"
            if native.geom_type == "Point"
            else None
        )
        if not kind:
            raise Problem(
                422,
                "UNIT_GEOMETRY_TYPE",
                "规划单元必须为面或单个候选点；线与集合需使用相应决策服务",
                {"unit": row["id"]},
            )
        kinds.add(kind)
        if len(kinds) > 1:
            raise Problem(
                422, "UNIT_GEOMETRY_MIXED", "同一单元集不能混用面与点，请按真实用途选择图层"
            )
        area, basis = area_m2(native, row["geometry_crs"], shown)
        unit = {
            "id": row["id"],
            "source_id": row["source_id"],
            "source_ordinal": index,
            "properties": row["properties"],
            "native_geometry": row["geometry"],
            "native_crs": CRS.from_user_input(row["geometry_crs"]).to_string(),
            "area_m2": area,
            "area_basis": basis,
        }
        units.append(unit)
        native_shapes.append(native)
        features.append(
            {
                "type": "Feature",
                "id": row["id"],
                "geometry": display,
                "properties": {
                    "unit_id": row["id"],
                    "unit_index": index + 1,
                    "area_m2": area,
                    "source_properties": row["properties"],
                    "area_basis": basis,
                },
            }
        )
    kind = next(iter(kinds))
    # Shared boundaries are legal. Positive-area overlap would double-count land.
    if kind == "polygon":
        tree, pairs = STRtree(native_shapes), 0
        for i, geometry in enumerate(native_shapes):
            check_cancel(cancelled)
            for candidate in tree.query(geometry, predicate="intersects"):
                j = int(candidate)
                if j <= i:
                    continue
                pairs += 1
                if pairs > MAX_INTERSECTION_PAIRS:
                    raise Problem(
                        422, "UNIT_TOPOLOGY_BUDGET", "空间重叠检查超过执行预算，未跳过检查或抽样"
                    )
                if geometry.intersection(native_shapes[j]).area > 0:
                    raise Problem(
                        422,
                        "UNIT_OVERLAP",
                        "规划单元存在面积重叠，需先修复分区；未重复计地",
                        {"units": [units[i]["id"], units[j]["id"]]},
                    )
    source = manifest["assets"][0]
    lineage = {
        "asset_id": source["id"],
        "revision": source["revision"],
        "sha256": source["sha256"],
        "layer": method["layer"],
        "data_profile": source["facts"],
        "mapping": manifest["draft"]["mapping"],
        "spatial_reference": manifest["draft"]["options"].get("spatial_reference"),
    }
    spatial = {
        "type": "FeatureCollection",
        "features": features,
        "target_crs": "EPSG:4326",
        "theme_property": "area_m2" if kind == "polygon" else "unit_index",
        "located_count": len(units),
        "observation_count": len(units),
        "unlocated": [],
        "source_asset_id": source["id"],
        "source_sha256": source["sha256"],
    }
    payload = {
        "schema_version": 1,
        "algorithm_version": VERSION,
        "scope": "full_layer",
        "source": lineage,
        "units": units,
        "geometry_type": kind,
        "statistics": {
            "unit_count": len(units),
            "area_m2": math.fsum(u["area_m2"] for u in units) if kind == "polygon" else None,
            "overlap_check": "passed" if kind == "polygon" else "not_applicable_points",
        },
    }
    artifact_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for name, content, view in [
        ("planning-units.json", payload, "table"),
        ("planning-units.geojson", spatial, "vector"),
    ]:
        check_cancel(cancelled)
        path = artifact_dir / name
        path.write_text(json.dumps(content, ensure_ascii=False, allow_nan=False, sort_keys=True))
        files.append(
            {
                "name": name,
                "title": "规划单元",
                "key": str(path.relative_to(settings.storage_root)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
                "role": "planning_units",
                "view_kind": view,
            }
        )
    return {
        **payload,
        "operator": "planning_units",
        "method": method,
        "files": files,
        "spatial_result": spatial,
    }


def validate_outputs(manifest, data, root):
    for item in data["files"]:
        path = (root / item["key"]).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise Problem(422, "UNIT_OUTPUT_INVALID", "规划单元产物不可读取")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise Problem(422, "UNIT_OUTPUT_INVALID", "规划单元产物校验失败")
    actual = json.loads((root / data["files"][0]["key"]).read_text())
    if (
        actual["source"]["sha256"] != manifest["assets"][0]["sha256"]
        or actual["units"] != data["units"]
    ):
        raise Problem(422, "UNIT_OUTPUT_INVALID", "规划单元与固定资料不一致")


def publish(c, store, job, data):
    if data.get("operator") != "planning_units":
        return
    store.permission(c, job["actor"], job["project_id"], write=True)
    source = data["source"]
    set_id = hashlib.sha256(
        f"{job['project_id']}:{source['asset_id']}:{source['layer']}".encode()
    ).hexdigest()
    # Upsert establishes a shared parent before taking the revision lock.
    values = dict(
        id=set_id,
        project_id=job["project_id"],
        source_asset_id=source["asset_id"],
        layer=source["layer"],
        revision=0,
    )
    if c.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as upsert
    else:
        from sqlalchemy.dialects.sqlite import insert as upsert
    c.execute(upsert(sets).values(**values).on_conflict_do_nothing(index_elements=["id"]))
    version = c.execute(
        update(sets)
        .where(sets.c.id == set_id)
        .values(revision=sets.c.revision + 1)
        .returning(sets.c.revision)
    ).scalar_one()
    artifact = data["files"][0]
    c.execute(
        insert(versions).values(
            id=job["id"],
            object_id=set_id,
            project_id=job["project_id"],
            task_id=job["task_id"],
            job_id=job["id"],
            version=version,
            source=source,
            unit_count=data["statistics"]["unit_count"],
            geometry_type=data["geometry_type"],
            algorithm_version=VERSION,
            sha256=artifact["sha256"],
            object_key=artifact["key"],
            created=time.time(),
        )
    )
    audit_event(c, job["actor"], job["project_id"], "publish_planning_units", job["id"])


def router(store):
    routes = APIRouter()

    @routes.get("/api/v1/tasks/{task_id}/planning/units")
    def read(task_id: str, request: Request):
        with store.engine.connect() as c:
            task = store.task(request.state.actor["id"], task_id, connection=c)
            result = []
            for row in c.execute(
                select(versions)
                .where(versions.c.task_id == task_id)
                .order_by(versions.c.created.desc())
            ).mappings():
                ref = next(
                    (
                        x
                        for x in task["draft"]["selection"]
                        if x["asset_id"] == row["source"]["asset_id"]
                    ),
                    None,
                )
                applicable = bool(
                    ref
                    and ref["revision"] == row["source"]["revision"]
                    and (ref.get("layer") is None or ref["layer"] == row["source"]["layer"])
                    and [b for b in task["draft"]["mapping"] if b["asset_id"] == ref["asset_id"]]
                    == row["source"]["mapping"]
                    and task["draft"]["options"].get("spatial_reference")
                    == row["source"].get("spatial_reference")
                )
                result.append({**dict(row), "applicable": applicable})
            return result

    return routes
