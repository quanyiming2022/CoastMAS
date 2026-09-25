"""Task-oriented scientific execution using explicit source semantics."""

import fiona
from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform

from .profiles import json_object, vector_target
from .selection import identity_field, selected_layer
from .store import Problem
from .temporal import compute as temporal


def entities(settings, manifest, cancelled):
    features, ids, source_metadata = [], set(), []
    options = manifest["draft"]["options"]
    for asset in manifest["assets"]:
        path, facts = settings.storage_root / asset["object_key"], asset["facts"]
        layer = selected_layer(asset, manifest["draft"])
        layer_name = layer["name"]
        identity = identity_field(asset, manifest["draft"], layer)
        if facts["profile"] not in {"geojson", "geopackage", "shapefile"}:
            raise Problem(422, "GEOMETRY_REQUIRED", "实体生成需要真实矢量几何")
        if facts["profile"] == "geojson":
            obj = json_object(path)
            sequence = obj.get(
                "features",
                [obj]
                if obj["type"] == "Feature"
                else [{"type": "Feature", "properties": {}, "geometry": obj}],
            )
            native = "EPSG:4326"
        else:
            target = vector_target(path, facts["profile"])
            with fiona.open(target, layer=layer_name) as dataset:
                native = dataset.crs
                sequence = [fiona.model.to_dict(feature) for feature in dataset]
        if not native:
            raise Problem(422, "CRS_REQUIRED", "源几何缺少可信坐标参考系")
        crs = CRS.from_user_input(native)
        projector = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
        for index, feature in enumerate(sequence):
            if cancelled.is_set():
                raise Problem(409, "CANCELLED", "运行已取消")
            if len(features) >= 100000:
                raise Problem(
                    422, "ENTITY_BUDGET", "实体集合超过当前事务预算；必须显式划分批次，不截断结果"
                )
            properties = feature.get("properties") or {}
            key = (
                properties.get(identity)
                if identity
                else feature.get("id", asset["sha256"] + ":" + str(index))
            )
            if key is None or key == "" or str(key) in ids:
                raise Problem(422, "ENTITY_IDENTITY", "实体标识缺失或重复，请明确唯一字段")
            ids.add(str(key))
            geometry = shape(feature["geometry"]) if feature.get("geometry") else None
            if geometry is None or geometry.is_empty or not geometry.is_valid:
                raise Problem(422, "ENTITY_GEOMETRY", "实体几何为空或无效")
            projected = transform(projector, geometry)
            west, south, east, north = projected.bounds
            if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
                raise Problem(422, "CRS_BOUNDS_CONFLICT", "几何投影后的经纬度越界")
            features.append(
                {
                    "type": "Feature",
                    "id": str(key),
                    "properties": properties,
                    "geometry": mapping(projected),
                }
            )
        source_metadata.append(
            {
                "asset_id": asset["id"],
                "revision": asset["revision"],
                "crs": crs.to_string(),
                "target_crs": "EPSG:4326",
                "layer": layer_name,
                "identity_field": identity,
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "sources": source_metadata,
        "valid_time": options.get("valid_time"),
        "scope": "complete_selected_layers",
    }


def compute(settings, manifest, cancelled):
    purpose = manifest["draft"]["purpose"]
    if purpose == "temporal":
        return temporal(settings, manifest, cancelled)
    if purpose == "entities":
        return entities(settings, manifest, cancelled)
    raise Problem(422, "METHOD_UNAVAILABLE", "没有满足当前任务的已实现运行方法")
