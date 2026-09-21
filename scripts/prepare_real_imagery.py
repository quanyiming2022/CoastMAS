"""Acquire bounded, georeferenced Sentinel-2 subsets; retain source and calibration evidence."""

import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window
from rasterio.windows import from_bounds as window_from_bounds

from coastmas.adapters.geofiles import Grid, encode_geotiff
from coastmas.domain.remote_sensing import calibrated_cog_reflectance

SEARCH_ROOT = Path(__file__).resolve().parents[1] / "artifacts/runtime/real-imagery"
ROOT = SEARCH_ROOT / "collection-1"
REGIONS = (
    ("yellow-river", "yellow-river-c1-search.json", (119.01, 37.74, 119.05, 37.77), 0),
    ("jiaozhou", "jiaozhou-c1-search.json", (120.16, 36.16, 120.20, 36.19), 0),
    ("yangtze-2024", "yangtze-2024-c1-search.json", (121.90, 31.46, 121.94, 31.49), 0),
    ("yangtze-2025", "yangtze-2025-c1-search.json", (121.90, 31.46, 121.94, 31.49), 0),
)


ITEMS = {
    "yellow-river": "S2B_T50SPG_20250925T030120_L2A",
    "jiaozhou": "S2C_T50SQF_20251027T024827_L2A",
    "yangtze-2024": "S2B_T51RUQ_20240901T023727_L2A",
    "yangtze-2025": "S2B_T51RUQ_20250906T023756_L2A",
}


def source_item(name, search):
    path = SEARCH_ROOT / search
    if not path.exists():
        response = httpx.post(
            "https://earth-search.aws.element84.com/v1/search",
            json={"collections": ["sentinel-2-c1-l2a"], "ids": [ITEMS[name]], "limit": 1},
            timeout=30,
        )
        response.raise_for_status()
        if len(response.content) > 2 * 1024 * 1024:
            raise ValueError("STAC response exceeds metadata budget")
        data = response.json()
        if not any(item.get("id") == ITEMS[name] for item in data.get("features", [])):
            raise ValueError("pinned public imagery product unavailable")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    matches = [
        item for item in json.loads(path.read_text())["features"] if item["id"] == ITEMS[name]
    ]
    if len(matches) != 1 or matches[0]["collection"] != "sentinel-2-c1-l2a":
        raise ValueError("STAC snapshot must contain exactly one pinned Collection 1 product")
    return matches[0]


def url(asset):
    address = urlsplit(asset["href"])
    if (
        address.scheme != "https"
        or address.netloc != "e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com"
    ):
        raise ValueError("source is outside the explicitly selected public Sentinel-2 archive")
    return asset["href"]


def acquire(name, search, bbox, selected):
    directory = ROOT / name
    directory.mkdir(exist_ok=True)
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        saved = json.loads(manifest_path.read_text())
        if all(
            hashlib.sha256((directory / key).read_bytes()).hexdigest() == digest
            for key, digest in saved["files"].items()
        ):
            print(name, "verified existing files", flush=True)
            return
        raise ValueError("existing imagery checksum mismatch; refusing overwrite")
    item = source_item(name, search)
    (directory / "source-item.json").write_text(json.dumps(item, ensure_ascii=False, indent=2))
    calibrations = {}
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_TIMEOUT=25,
        GDAL_HTTP_MAX_RETRY=0,
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    ):
        with rasterio.open(url(item["assets"]["red"])) as source:
            projected = transform_bounds("EPSG:4326", source.crs, *bbox, densify_pts=21)
            raw_window = window_from_bounds(*projected, transform=source.transform)
            left, top = math.floor(raw_window.col_off), math.floor(raw_window.row_off)
            right, bottom = (
                math.ceil(raw_window.col_off + raw_window.width),
                math.ceil(raw_window.row_off + raw_window.height),
            )
            window = Window(left, top, right - left, bottom - top)
            if left < 0 or top < 0 or right > source.width or bottom > source.height:
                raise ValueError("selected item does not fully cover the requested AOI")
            height, width = int(window.height), int(window.width)
            if height * width > 250000:
                raise ValueError("demonstration subset exceeds 250000 native pixels")
            transform, crs = source.window_transform(window), source.crs
            native_transform = source.transform
        with rasterio.open(url(item["assets"]["scl"])) as source:
            scl_window = window_from_bounds(
                *rasterio.windows.bounds(window, native_transform),
                transform=source.transform,
            )
            labels = source.read(
                1, window=scl_window, out_shape=(height, width), resampling=Resampling.nearest
            )
        clear = np.isin(labels, [4, 5, 6])
        for band in ("red", "green", "nir"):
            asset = item["assets"][band]
            with rasterio.open(url(asset)) as source:
                if source.crs != crs or source.window_transform(window) != transform:
                    raise ValueError("native optical bands are not aligned")
                raw = source.read(1, window=window)
                file_scale, file_offset, file_nodata = (
                    source.scales[0],
                    source.offsets[0],
                    source.nodata,
                )
            calibration = asset["raster:bands"][0]
            values = calibrated_cog_reflectance(
                raw,
                scale=calibration["scale"],
                offset=calibration["offset"],
                nodata=calibration["nodata"],
                file_scale=file_scale,
                file_offset=file_offset,
                file_nodata=file_nodata,
            )
            np.save(directory / (band + "-raw.npy"), raw, allow_pickle=False)
            calibrations[band] = {
                "stac": calibration,
                "file_scale": file_scale,
                "file_offset": file_offset,
                "file_nodata": file_nodata,
            }
            values[~clear] = np.nan
            (directory / (band + ".tif")).write_bytes(
                encode_geotiff(Grid(values, str(crs), transform, "1"))
            )
        with rasterio.open(url(item["assets"]["visual"])) as source:
            rgb = source.read((1, 2, 3), window=window)
        display_bounds = transform_bounds(
            crs,
            "EPSG:4326",
            *rasterio.transform.array_bounds(height, width, transform),
            densify_pts=21,
        )
        display_transform = from_bounds(*display_bounds, 512, 512)
        rgba = np.zeros((4, 512, 512), dtype=np.uint8)
        for index in range(3):
            reproject(
                rgb[index],
                rgba[index],
                src_transform=transform,
                src_crs=crs,
                dst_transform=display_transform,
                dst_crs="EPSG:4326",
                resampling=Resampling.bilinear,
            )
        source_alpha = np.where(np.any(rgb != 0, axis=0), 255, 0).astype(np.uint8)
        reproject(
            source_alpha,
            rgba[3],
            src_transform=transform,
            src_crs=crs,
            dst_transform=display_transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.nearest,
        )
        with rasterio.open(
            directory / "true-color.png",
            "w",
            driver="PNG",
            width=512,
            height=512,
            count=4,
            dtype="uint8",
        ) as target:
            target.write(rgba)
        np.save(directory / "scene-classification.npy", labels, allow_pickle=False)
    files = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.iterdir()
        if path.is_file()
    }
    manifest = {
        "source": "Copernicus Sentinel-2 Collection 1 L2A / Earth Search",
        "calibration_policy": "stac_matches_cog_v1",
        "band_calibration": calibrations,
        "item_id": item["id"],
        "acquired_at": item["properties"]["datetime"],
        "tile_cloud_cover_percent": item["properties"]["eo:cloud_cover"],
        "aoi_wgs84": bbox,
        "native_crs": str(crs),
        "transform": list(transform)[:6],
        "width": width,
        "height": height,
        "native_pixel_size_m": 10,
        "display_bounds_wgs84": list(display_bounds),
        "display_size": [512, 512],
        "display_resampling": "bilinear RGB, nearest alpha; visualization only",
        "accepted_scene_classes": [4, 5, 6],
        "clear_pixels": int(clear.sum()),
        "total_pixels": int(clear.size),
        "scientific_processing": (
            "physical reflectance = raw * asset scale + asset offset; "
            "raw nodata and non-clear classes masked; no cloud filling"
        ),
        "files": files,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(name, item["id"], width, height, "clear", int(clear.sum()), flush=True)


if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    for definition in REGIONS:
        acquire(*definition)
