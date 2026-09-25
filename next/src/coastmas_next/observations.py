"""Read real managed observation rows once for all tabular decision tasks."""

import csv
import math

import fiona

from coastmas.core.contracts import UNITS

from .csvw import iter_rows
from .profiles import json_object, vector_target
from .selection import selected_layer
from .store import Problem


def read_rows(settings, manifest, limit=100000):
    if len(manifest["assets"]) != 1:
        raise Problem(
            422,
            "RELATION_REQUIRED",
            "本次表格任务需要一个观测集合；多资料必须先明确关联键，不能按行号猜测连接",
        )
    asset = manifest["assets"][0]
    facts = asset["facts"]
    path = settings.storage_root / asset["object_key"]
    layer = selected_layer(asset, manifest["draft"])["name"]
    rows = []
    geometry_crs = "EPSG:4326" if facts["profile"] == "geojson" else None

    def append(properties, identity, geometry=None):
        if len(rows) >= limit:
            raise Problem(
                422, "OBSERVATION_BUDGET", "观测集合超过当前方法预算；必须明确分组，不能自动截断"
            )
        rows.append(
            {
                "properties": properties,
                "source_id": identity,
                "geometry": geometry,
                "geometry_crs": geometry_crs,
            }
        )

    if facts["profile"] == "csv":
        with path.open(encoding=facts["encoding"], newline="") as stream:
            for index, row in enumerate(csv.DictReader(stream, **facts["dialect"])):
                append(row, str(index + 1))
    elif facts["profile"] == "csvw":
        if "csvw" not in facts:
            raise Problem(422, "CSVW_COMPANION_REQUIRED", "请同时提供CSVW引用的实际表资料")
        table = next(item for item in facts["csvw"]["tables"] if item["name"] == layer)
        for index, row in enumerate(iter_rows(path, table)):
            append(row, str(index + 1))
    elif facts["profile"] == "geojson":
        obj = json_object(path)
        features = obj["features"] if obj["type"] == "FeatureCollection" else [obj]
        for index, item in enumerate(features):
            append(
                item.get("properties") or {}, item.get("id", str(index + 1)), item.get("geometry")
            )
    elif facts["profile"] in {"geopackage", "shapefile"}:
        target = vector_target(path, facts["profile"])
        with fiona.open(target, layer=layer) as collection:
            geometry_crs = collection.crs_wkt or collection.crs or None
            for feature in collection:
                value = fiona.model.to_dict(feature)
                append(value["properties"], value.get("id"), value.get("geometry"))
    else:
        raise Problem(
            422, "OBSERVATION_PROFILE", "此方法需要表格或矢量观测；栅格需明确像元/管理单元转换规则"
        )
    identities = [
        b
        for b in manifest["draft"]["mapping"]
        if b["role"] == "identity"
        and b["asset_id"] == asset["id"]
        and b["field"].startswith(layer + "/")
    ]
    if len(identities) > 1:
        raise Problem(422, "IDENTITY_AMBIGUOUS", "请选择唯一观测标识字段")
    bindings = {}
    paths = {
        item["name"] + "/" + field["name"]: field
        for item in facts["layers"]
        for field in item["fields"]
    }
    for binding in manifest["draft"]["mapping"]:
        if binding["asset_id"] != asset["id"] or binding["field"] not in paths:
            raise Problem(422, "BINDING_INVALID", "字段不在实际资料中")
        if not binding["field"].startswith(layer + "/"):
            continue
        if binding["role"] != "ignored" and binding.get("concept"):
            if binding["concept"] in bindings:
                raise Problem(422, "CONCEPT_AMBIGUOUS", "同一科学含义对应多个字段，请明确映射")
            bindings[binding["concept"]] = {**binding, "native": paths[binding["field"]]}
    seen = set()
    for row in rows:
        identity = (
            row["properties"].get(paths[identities[0]["field"]]["name"])
            if identities
            else row["source_id"]
        )
        if identity is None or identity == "" or str(identity) in seen:
            raise Problem(422, "OBSERVATION_IDENTITY", "观测标识缺失或重复")
        row["id"] = str(identity)
        seen.add(str(identity))
    if not rows:
        raise Problem(422, "OBSERVATIONS_REQUIRED", "所选图层没有观测")
    from .observation_space import attach_coordinates

    attach_coordinates(rows, asset, manifest["draft"])
    return rows, bindings


def quantity(row, binding, target_unit):
    name = binding["native"]["name"]
    raw = row["properties"].get(name)
    if raw is None or raw == "":
        raise Problem(
            422,
            "OBSERVATION_MISSING",
            "源数据缺少必要数值，不自动补零",
            {"row": row["id"], "field": name},
        )
    if isinstance(raw, bool):
        raise Problem(422, "OBSERVATION_TYPE", "布尔值不能作为数值指标")
    try:
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("nonfinite")
    except (TypeError, ValueError) as exc:
        raise Problem(
            422, "OBSERVATION_INVALID", "源字段不是有限数值", {"row": row["id"], "field": name}
        ) from exc
    native = binding["native"]
    source_unit = native.get("unit") or binding.get("unit")
    if not source_unit:
        raise Problem(422, "UNIT_REQUIRED", "源变量单位没有依据", {"field": name})
    value = value * native.get("scale", 1) + native.get("offset", 0)
    try:
        return float(UNITS.Quantity(value, source_unit).to(target_unit).magnitude)
    except Exception as exc:
        raise Problem(
            422,
            "UNIT_INCOMPATIBLE",
            "源变量不能按量纲适配到方法单位",
            {"field": name, "source": source_unit, "target": target_unit},
        ) from exc
