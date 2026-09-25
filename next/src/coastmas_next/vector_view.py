"""Authenticated, bounded vector pages with separate native and display geometry."""

import hashlib
import math
from contextlib import contextmanager

import fiona
from fastapi import APIRouter, Query, Request
from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform

from .intake import Intake
from .profiles import clean, vector_target
from .store import Problem


def located_bounds(bounds):
    return (
        len(bounds) == 4
        and all(math.isfinite(v) for v in bounds)
        and (-180 <= bounds[0] <= bounds[2] <= 180 and -90 <= bounds[1] <= bounds[3] <= 90)
    )


def positioning(ds):
    if not ds.crs:
        return "missing", None, "文件未声明坐标系；仅展示原始属性和原生坐标"
    try:
        projection = Transformer.from_crs(ds.crs, "EPSG:4326", always_xy=True)
        if CRS.from_user_input(ds.crs).is_geographic and not located_bounds(ds.bounds):
            return "conflict", None, "文件坐标超出经纬范围，不能推测坐标系"
        bounds = list(projection.transform_bounds(*ds.bounds, densify_pts=64, errcheck=True))
        if located_bounds(bounds):
            return "located", bounds, None
    except (ValueError, RuntimeError):
        pass
    return "conflict", None, "文件坐标与声明冲突；原件保留，不猜测定位"


def display_geometry(geometry, crs):
    if not geometry:
        return None, "此记录没有几何"
    if not crs:
        return None, "未声明坐标系，不能定位"
    try:
        native = shape(geometry)
        if native.is_empty or not native.is_valid:
            return None, "几何为空或无效，原生记录保留"
        if CRS.from_user_input(crs).is_geographic and not located_bounds(native.bounds):
            return None, "坐标超出经纬范围，禁止猜测定位"
        projection = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        projected = transform(projection.transform, native)
        if not located_bounds(projected.bounds):
            return None, "显示坐标变换失败或经纬范围冲突"
        return clean(mapping(projected)), None
    except (ValueError, RuntimeError):
        return None, "显示坐标变换失败；原生记录保留"


class VectorViews:
    def __init__(self, store):
        self.store = store

    def asset(self, actor, asset_id):
        asset = Intake(self.store).read_asset(actor, asset_id)
        profile = asset["facts"]["profile"]
        if profile not in {"geojson", "geopackage", "shapefile"}:
            raise Problem(422, "VECTOR_REQUIRED", "此资料不是已接入的矢量文件")
        path = str(self.store.settings.storage_root / asset["object_key"])
        return asset, vector_target(path, profile)

    @contextmanager
    def open(self, actor, asset_id, layer):
        asset, target = self.asset(actor, asset_id)
        names = fiona.listlayers(target)
        logical = ["features"] if asset["facts"]["profile"] == "geojson" else names
        if layer not in logical:
            raise Problem(422, "VECTOR_LAYER", "所选图层不存在")
        with fiona.open(target, layer=names[logical.index(layer)]) as ds:
            yield asset, ds

    def layers(self, actor, asset_id):
        asset, target = self.asset(actor, asset_id)
        layers = []
        for native_name in fiona.listlayers(target):
            with fiona.open(target, layer=native_name) as ds:
                status, bounds, issue = positioning(ds)
                layers.append(
                    {
                        "name": "features"
                        if asset["facts"]["profile"] == "geojson"
                        else native_name,
                        "total": len(ds),
                        "geometry_type": ds.schema["geometry"],
                        "fields": list(ds.schema["properties"]),
                        "crs": CRS.from_user_input(ds.crs).to_string() if ds.crs else None,
                        "georeference_status": status,
                        "bounds": bounds,
                        "display_issue": issue,
                    }
                )
        return {"asset_id": asset_id, "sha256": asset["sha256"], "layers": layers}

    def record(self, asset, layer, ordinal, feature):
        identity = hashlib.sha256(f"{asset['id']}:{layer}:{ordinal}".encode()).hexdigest()
        return {
            "id": identity,
            "asset_id": asset["id"],
            "sha256": asset["sha256"],
            "layer": layer,
            "source_ordinal": ordinal,
            "source_id": feature.id,
            "properties": clean(dict(feature.properties)),
            "native_geometry": clean(fiona.model.to_dict(feature.geometry))
            if feature.geometry
            else None,
        }

    def page(self, actor, asset_id, layer, offset, limit):
        with self.open(actor, asset_id, layer) as (asset, ds):
            features = []
            # OGR slices avoid materializing the full layer; ordinals remain distinct even
            # when the source itself contains duplicated feature IDs.
            for ordinal, feature in enumerate(ds.filter(offset, offset + limit), start=offset):
                record = self.record(asset, layer, ordinal, feature)
                geometry, issue = display_geometry(record["native_geometry"], ds.crs)
                features.append(
                    {
                        "type": "Feature",
                        "id": record["id"],
                        "properties": record["properties"],
                        "geometry": geometry,
                        "display_issue": issue,
                        "source_ordinal": ordinal,
                    }
                )
            return {
                "type": "FeatureCollection",
                "features": features,
                "total": len(ds),
                "offset": offset,
                "limit": limit,
                "scope": "source_record_page",
            }

    def native(self, actor, asset_id, layer, ordinal):
        with self.open(actor, asset_id, layer) as (asset, ds):
            if ordinal >= len(ds):
                raise Problem(404, "VECTOR_RECORD", "原生记录不存在")
            feature = next(iter(ds.filter(ordinal, ordinal + 1)), None)
            if feature is None:
                raise Problem(404, "VECTOR_RECORD", "原生记录不存在")
            return self.record(asset, layer, ordinal, feature)


def router(store):
    routes = APIRouter()
    views = VectorViews(store)

    @routes.get("/api/assets/{asset_id}/vector/layers")
    def layers(asset_id: str, request: Request):
        return views.layers(request.state.actor["id"], asset_id)

    @routes.get("/api/assets/{asset_id}/vector/features")
    def page(
        asset_id: str,
        request: Request,
        layer: str = Query(max_length=256),
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
    ):
        return views.page(request.state.actor["id"], asset_id, layer, offset, limit)

    @routes.get("/api/assets/{asset_id}/vector/records/{ordinal}")
    def record(asset_id: str, ordinal: int, request: Request, layer: str = Query(max_length=256)):
        if ordinal < 0:
            raise Problem(404, "VECTOR_RECORD", "原生记录不存在")
        return views.native(request.state.actor["id"], asset_id, layer, ordinal)

    return routes
