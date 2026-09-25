"""Bounded visual projections of immutable assets; never a scientific transformation.

A fixed native nearest sample determines the style once. Tiles use that same style,
while inspect always reads one original pixel. Cache keys include bytes and renderer.
"""

import hashlib
import json
import math
import os
from uuid import uuid4

import numpy as np
import rasterio
from fastapi import APIRouter, Query, Request, Response
from pydantic import Field
from pyproj import Transformer
from rasterio.enums import ColorInterp, Resampling
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window

from .contracts import Contract
from .intake import Intake
from .profiles import clean
from .store import Problem

RENDERER = "native-affine-nearest-v1"
MERCATOR = 20037508.342789244


def georeference(ds):
    if ds.gcps[0] or ds.rpcs or ds.tags(ns="GEOLOCATION"):
        return "unsupported", None, "GCP/RPC/定位数组需专用校正链；当前显示器未核验此定位链"
    if not ds.crs:
        return "missing", None, "文件未声明坐标系，可查看原始图像"
    t = ds.transform
    if t.is_identity or not math.isfinite(t.determinant) or abs(t.determinant) < 1e-24:
        return "conflict", None, "缺少可信仿射定位或变换退化，可查看原始图像"
    # Densify all four true affine edges, including rotations and shears.
    edge = np.linspace(0, 1, 65)
    pixels = (
        [(ds.width * x, 0) for x in edge]
        + [(ds.width, ds.height * y) for y in edge]
        + [(ds.width * x, ds.height) for x in edge]
        + [(0, ds.height * y) for y in edge]
    )
    xy = [t @ p for p in pixels]
    transformer = Transformer.from_crs(ds.crs, "EPSG:4326", always_xy=True)
    try:
        lon, lat = transformer.transform(*zip(*xy, strict=True), errcheck=True)
    except Exception:
        return "conflict", None, "坐标变换失败，不能推测地理位置"
    bounds = [min(lon), min(lat), max(lon), max(lat)]
    if not all(math.isfinite(v) for v in bounds) or not (
        -180 <= bounds[0] < bounds[2] <= 180 and -90 <= bounds[1] < bounds[3] <= 90
    ):
        return "conflict", None, "文件坐标与经纬范围冲突；原件保留，禁止猜测定位"
    if bounds[2] - bounds[0] > 180 or bounds[1] < -85.05112878 or bounds[3] > 85.05112878:
        return "unsupported", None, "当前地图未支持跨日期变更线或极区；可查看非地理图像"
    return "located", bounds, None


def band_check(ds, band):
    if not 1 <= band <= ds.count:
        raise Problem(422, "BAND_UNAVAILABLE", "所选波段不存在")


def data_mask(ds, band, **kwargs):
    raw = ds.read(band, masked=True, **kwargs)
    values = raw.data.astype("float64") * ds.scales[band - 1] + ds.offsets[band - 1]
    mask = ~np.ma.getmaskarray(raw) & np.isfinite(values)
    if ColorInterp.alpha in ds.colorinterp:
        alpha = ds.colorinterp.index(ColorInterp.alpha) + 1
        mask &= ds.read(alpha, **kwargs) > 0
    return values, mask


def paint(values, mask, style):
    rgba = np.zeros((4, *values.shape), dtype="uint8")
    palette = style.get("palette")
    if palette:
        # Palettes apply to stored categories, not scale/offset-transformed codes.
        stored = (values - style["offset"]) / style["scale"] if style["scale"] else values
        for code, color in palette.items():
            selected = mask & (stored == int(code))
            rgba[:, selected] = np.array(color, dtype="uint8")[:, None]
        return rgba
    low, high = style["minimum"], style["maximum"]
    if low is not None and high is not None:
        fraction = np.zeros_like(values) if low == high else (values - low) / (high - low)
        fraction = np.clip(np.where(mask, fraction, 0), 0, 1)
        for index, (a, b) in enumerate([(224, 8), (244, 110), (239, 115)]):
            rgba[index] = (a + (b - a) * fraction).astype("uint8")
        rgba[3] = np.where(mask, 255, 0).astype("uint8")
    return rgba


def png_bytes(rgba):
    with rasterio.io.MemoryFile() as memory:
        with memory.open(
            driver="PNG", width=rgba.shape[2], height=rgba.shape[1], count=4, dtype="uint8"
        ) as image:
            image.write(rgba)
            image.colorinterp = (
                ColorInterp.red,
                ColorInterp.green,
                ColorInterp.blue,
                ColorInterp.alpha,
            )
        return memory.read()


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid4().hex)
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class Views:
    def __init__(self, store):
        self.store = store
        self.intake = Intake(store)

    def asset(self, actor, asset_id):
        asset = self.intake.read_asset(actor, asset_id)
        if asset["facts"]["profile"] not in {"geotiff", "cog"}:
            raise Problem(
                422, "RASTER_VIEW_REQUIRED", "此接口只显示真实栅格；其他资料使用原始字段预览"
            )
        return asset

    def cache(self, asset, band):
        path = self.store.settings.storage_root / "display" / RENDERER / asset["sha256"] / str(band)
        if asset.get("render_palette"):
            style_key = hashlib.sha256(
                json.dumps(asset["render_palette"], sort_keys=True).encode()
            ).hexdigest()[:16]
            path = path / style_key
        return path

    def descriptor(self, asset, band):
        cache = self.cache(asset, band)
        metadata = cache / "style.json"
        if metadata.is_file():
            info = json.loads(metadata.read_text())
        else:
            with (
                rasterio.Env(GDAL_CACHEMAX=64 * 1024**2, GDAL_NUM_THREADS="1"),
                rasterio.open(self.store.settings.storage_root / asset["object_key"]) as ds,
            ):
                band_check(ds, band)
                ratio = min(1, self.store.settings.preview_size / max(ds.width, ds.height))
                values, mask = data_mask(
                    ds,
                    band,
                    out_shape=(max(1, int(ds.height * ratio)), max(1, int(ds.width * ratio))),
                    resampling=Resampling.nearest,
                )
                valid = values[mask]
                status, bounds, issue = georeference(ds)
                palette = None
                if ds.colorinterp[band - 1] == ColorInterp.palette:
                    palette = ds.colormap(band)
                palette = asset.get("render_palette") or palette
                info = {
                    "renderer": RENDERER,
                    "band": band,
                    "band_count": ds.count,
                    "width": ds.width,
                    "height": ds.height,
                    "crs": ds.crs.to_string() if ds.crs else None,
                    "transform": list(ds.transform)[:6],
                    "scale": ds.scales[band - 1],
                    "offset": ds.offsets[band - 1],
                    "unit": ds.units[band - 1],
                    "unit_source": "file" if ds.units[band - 1] else "undeclared",
                    "minimum": float(valid.min()) if valid.size else None,
                    "maximum": float(valid.max()) if valid.size else None,
                    "sample_valid_pixels": int(mask.sum()),
                    "sample_pixels": int(mask.size),
                    "statistics_scope": "bounded_nearest_sample",
                    "georeference_status": status,
                    "bounds": bounds,
                    "extent_source": "densified_native_affine_edges" if bounds else None,
                    "geolocation_chain": "source_affine_then_PROJ" if bounds else None,
                    "display_status": "ready" if valid.size else "empty_sample",
                    "issues": [issue] if issue else [],
                    "palette": palette,
                    "value_domain": "physical_values",
                    "resampling": "nearest",
                    "scientific_readiness": "not_required_for_view",
                }
                atomic(cache / "native.png", png_bytes(paint(values, mask, info)))
                atomic(metadata, json.dumps(info, allow_nan=False).encode())
        return {
            **info,
            "asset_id": asset["id"],
            "asset_revision": asset["revision"],
            "sha256": asset["sha256"],
        }

    def tile(self, asset, band, z, x, y):
        if not 0 <= z <= 22 or not 0 <= x < 2**z or not 0 <= y < 2**z:
            raise Problem(422, "TILE_BOUNDS", "瓦片坐标超出显示范围")
        style = self.descriptor(asset, band)
        if style["georeference_status"] != "located":
            raise Problem(422, "VIEW_LOCATION", style["issues"][0])
        span = 2 * MERCATOR / 2**z
        bounds = (
            -MERCATOR + x * span,
            MERCATOR - (y + 1) * span,
            -MERCATOR + (x + 1) * span,
            MERCATOR - y * span,
        )
        with (
            rasterio.Env(GDAL_CACHEMAX=64 * 1024**2, GDAL_NUM_THREADS="1"),
            rasterio.open(self.store.settings.storage_root / asset["object_key"]) as ds,
        ):
            # Explicit target grid and alpha prevent warp padding becoming valid zero.
            with WarpedVRT(
                ds,
                crs="EPSG:3857",
                transform=from_bounds(*bounds, 256, 256),
                width=256,
                height=256,
                add_alpha=ColorInterp.alpha not in ds.colorinterp,
                resampling=Resampling.nearest,
                warp_mem_limit=self.store.settings.display_warp_mib,
            ) as display:
                raw = display.read(band, masked=True)
                values = raw.data.astype("float64") * ds.scales[band - 1] + ds.offsets[band - 1]
                mask = ~np.ma.getmaskarray(raw) & np.isfinite(values)
                if ColorInterp.alpha in display.colorinterp:
                    mask &= display.read(display.colorinterp.index(ColorInterp.alpha) + 1) > 0
                return png_bytes(paint(values, mask, style))

    def inspect(self, asset, body):
        with (
            rasterio.Env(GDAL_CACHEMAX=64 * 1024**2),
            rasterio.open(self.store.settings.storage_root / asset["object_key"]) as ds,
        ):
            band_check(ds, body.band)
            status, _, issue = georeference(ds)
            if status != "located":
                raise Problem(422, "VIEW_LOCATION", issue)
            x, y = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True).transform(
                body.longitude, body.latitude
            )
            row, col = ds.index(x, y)
            result = {
                "asset_id": asset["id"],
                "asset_revision": asset["revision"],
                "sha256": asset["sha256"],
                "band": body.band,
                "row": row,
                "column": col,
                "crs": ds.crs.to_string(),
                "transform": list(ds.transform)[:6],
                "value_domain": "native_source_pixel",
                "geolocation_chain": "inverse_PROJ_then_source_affine",
                "scale": ds.scales[body.band - 1],
                "offset": ds.offsets[body.band - 1],
                "unit": ds.units[body.band - 1],
                "unit_source": "file" if ds.units[body.band - 1] else "undeclared",
                "valid": False,
                "stored_value": None,
                "value": None,
                "status": "outside",
            }
            if 0 <= row < ds.height and 0 <= col < ds.width:
                window = Window(col, row, 1, 1)
                raw = ds.read(body.band, window=window)
                values, mask = data_mask(ds, body.band, window=window)
                result.update(
                    stored_value=clean(raw[0, 0]),
                    valid=bool(mask[0, 0]),
                    value=float(values[0, 0]) if mask[0, 0] else None,
                    status="valid" if mask[0, 0] else "nodata",
                )
            return result


class InspectPoint(Contract):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    band: int = Field(default=1, ge=1)


def router(store):
    routes = APIRouter()
    views = Views(store)

    @routes.get("/api/assets/{asset_id}/view")
    def descriptor(asset_id: str, request: Request, band: int = Query(1, ge=1)):
        return views.descriptor(views.asset(request.state.actor["id"], asset_id), band)

    @routes.get("/api/assets/{asset_id}/view.png")
    def native_image(asset_id: str, request: Request, band: int = Query(1, ge=1)):
        asset = views.asset(request.state.actor["id"], asset_id)
        views.descriptor(asset, band)
        return Response(
            (views.cache(asset, band) / "native.png").read_bytes(), media_type="image/png"
        )

    @routes.get("/api/assets/{asset_id}/tiles/{z}/{x}/{y}.png")
    def tile(asset_id: str, z: int, x: int, y: int, request: Request, band: int = Query(1, ge=1)):
        return Response(
            views.tile(views.asset(request.state.actor["id"], asset_id), band, z, x, y),
            media_type="image/png",
        )

    @routes.post("/api/assets/{asset_id}/inspect")
    def inspect(asset_id: str, body: InspectPoint, request: Request):
        return views.inspect(views.asset(request.state.actor["id"], asset_id), body)

    return routes
