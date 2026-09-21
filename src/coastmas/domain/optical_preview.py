"""Georeferenced, fixed-scale display images; original numeric outputs remain authoritative."""

import base64

import numpy as np
from affine import Affine
from pydantic import JsonValue
from rasterio.enums import Resampling  # type: ignore[import-untyped]
from rasterio.io import MemoryFile  # type: ignore[import-untyped]
from rasterio.transform import array_bounds, from_bounds  # type: ignore[import-untyped]
from rasterio.warp import reproject, transform_bounds  # type: ignore[import-untyped]

from coastmas.core.contracts import TargetGridSpec
from coastmas.core.errors import ConstraintError
from coastmas.core.numeric import FloatArray


def optical_preview(values: FloatArray, grid: TargetGridSpec, name: str) -> dict[str, JsonValue]:
    if values.shape != (grid.height, grid.width) or values.size > 250000:
        raise ConstraintError("preview must match a bounded analysis grid")
    if name not in {"NDVI", "NDWI", "NDVI_CHANGE"}:
        raise ConstraintError("unsupported optical preview scale")
    transform = Affine(*grid.transform)
    bounds = transform_bounds(
        grid.crs, "EPSG:4326", *array_bounds(grid.height, grid.width, transform), densify_pts=21
    )
    height, width = min(grid.height, 512), min(grid.width, 512)
    display = np.full((height, width), np.nan, dtype=np.float64)
    reproject(
        values,
        display,
        src_transform=transform,
        src_crs=grid.crs,
        dst_transform=from_bounds(*bounds, width, height),
        dst_crs="EPSG:4326",
        src_nodata=np.nan,
        dst_nodata=np.nan,
        resampling=Resampling.nearest,
    )
    limit = 2 if name == "NDVI_CHANGE" else 1
    known = np.isfinite(display)
    position = (np.where(known, display, 0) / limit + 1) / 2
    rgba = np.zeros((4, height, width), dtype="uint8")
    # Fixed brown-to-green / brown-to-blue scales, never normalized per image.
    low = np.array([165, 75, 45])
    high = np.array([30, 95, 205] if name == "NDWI" else [25, 155, 65])
    for channel in range(3):
        rgba[channel] = np.rint(
            low[channel] + np.clip(position, 0, 1) * (high[channel] - low[channel])
        ).astype("uint8")
    rgba[3] = known.astype("uint8") * 255
    with MemoryFile() as memory:
        with memory.open(
            driver="PNG", width=width, height=height, count=4, dtype="uint8"
        ) as destination:
            destination.write(rgba)
        content = memory.read()
    return {
        "kind": "optical_preview",
        "url": "data:image/png;base64," + base64.b64encode(content).decode("ascii"),
        "bounds": list(bounds),
        "label": name,
        "minimum": -limit,
        "maximum": limit,
        "unit": "1",
        "nodata": "transparent",
        "resampling": "nearest; display only",
    }
