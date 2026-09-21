"""Bounded, in-memory GeoTIFF I/O with explicit scientific metadata.

Uploaded bytes can only select the GTiff driver: no VRT or external-file
references. NoData becomes NaN, never zero. Area is the projected affine cell
area with coordinate units converted to metres; projection distortion remains
an explicit scene-level scientific decision.
"""

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from affine import Affine
from pyproj import CRS
from pyproj.exceptions import CRSError

# Rasterio exposes extension APIs without complete type annotations.
from rasterio.enums import Resampling  # type: ignore[import-untyped]
from rasterio.errors import RasterioError  # type: ignore[import-untyped]
from rasterio.io import MemoryFile  # type: ignore[import-untyped]
from rasterio.warp import reproject  # type: ignore[import-untyped]

from coastmas.core.errors import CoastMASError, ConstraintError
from coastmas.core.numeric import FloatArray


@dataclass(frozen=True)
class Grid:
    values: FloatArray
    crs: str
    transform: Affine
    unit: str
    vertical_datum: str | None = None

    def __post_init__(self) -> None:
        if self.values.ndim != 2 or self.values.size == 0 or np.any(np.isinf(self.values)):
            raise ConstraintError("grid must be nonempty 2D without infinity")
        if (
            not all(math.isfinite(value) for value in self.transform)
            or self.transform.determinant == 0
        ):
            raise ConstraintError("grid transform must be finite and invertible")
        if not self.unit.strip():
            raise ConstraintError("grid unit is required")
        try:
            CRS.from_user_input(self.crs)
        except CRSError as exc:
            raise ConstraintError("grid CRS is invalid") from exc
        snapshot = np.array(self.values, dtype=np.float64, copy=True)
        snapshot.setflags(write=False)
        object.__setattr__(self, "values", snapshot)

    @property
    def cell_area_m2(self) -> float:
        reference = CRS.from_user_input(self.crs)
        if not reference.is_projected or len(reference.axis_info) < 2:
            raise ConstraintError("cell area requires a suitable projected CRS")
        factors = [axis.unit_conversion_factor for axis in reference.axis_info[:2]]
        if not all(math.isfinite(value) and value > 0 for value in factors):
            raise ConstraintError("projected axis units are not convertible to metres")
        return float(abs(self.transform.determinant) * factors[0] * factors[1])


def encode_geotiff(grid: Grid) -> bytes:
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            height=grid.values.shape[0],
            width=grid.values.shape[1],
            count=1,
            dtype="float64",
            crs=grid.crs,
            transform=grid.transform,
            nodata=np.nan,
            compress="deflate",
        ) as dataset:
            dataset.write(grid.values, 1)
            dataset.update_tags(unit=grid.unit, vertical_datum=grid.vertical_datum or "")
        return bytes(memory.read())


def decode_geotiff(
    content: bytes, *, max_cells: int = 4_000_000, max_bytes: int = 64 * 1024 * 1024
) -> Grid:
    if max_cells <= 0 or max_bytes <= 0 or len(content) > max_bytes:
        raise CoastMASError("RASTER_LIMIT", "raster byte budget exceeded")
    if content[:4] not in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
        raise CoastMASError("RASTER_FORMAT", "only actual GeoTIFF bytes are accepted")
    try:
        with MemoryFile(content) as memory, memory.open(driver="GTiff") as dataset:
            if dataset.driver != "GTiff" or dataset.count != 1:
                raise ConstraintError("a single-band GeoTIFF is required")
            if dataset.width * dataset.height > max_cells:
                raise CoastMASError("RASTER_LIMIT", "raster cell budget exceeded")
            if dataset.crs is None:
                raise ConstraintError("GeoTIFF CRS is missing")
            tags = dataset.tags()
            unit = tags.get("unit")
            if not isinstance(unit, str) or not unit:
                raise ConstraintError("GeoTIFF variable unit metadata is missing")
            values = np.asarray(
                dataset.read(1, masked=True).astype("float64").filled(np.nan), dtype=np.float64
            )
            return Grid(
                values,
                str(dataset.crs),
                dataset.transform,
                unit,
                tags.get("vertical_datum") or None,
            )
    except RasterioError as exc:
        raise CoastMASError("RASTER_FORMAT", "GeoTIFF could not be decoded") from exc


def resample_grid(
    grid: Grid,
    *,
    crs: str,
    transform: Affine,
    shape: tuple[int, int],
    kind: Literal["continuous", "categorical", "extensive"],
    method: Literal["nearest", "bilinear", "cubic", "average", "sum", "area_weighted"],
    max_cells: int = 4_000_000,
) -> Grid:
    if kind == "extensive":
        if method not in ("sum", "area_weighted"):
            raise ConstraintError(
                "extensive values require explicit conservative area redistribution"
            )
        source_crs, target_crs = CRS(grid.crs), CRS(crs)
        if source_crs != target_crs or not source_crs.is_projected:
            raise ConstraintError("conservative grids require a common reviewed projected CRS")
        from coastmas.domain.grid_conservation import allocate_grid

        allocated = allocate_grid(
            grid.values, grid.transform, transform, shape, max_cells=min(max_cells, 100000)
        )
        return Grid(allocated, crs, transform, grid.unit, grid.vertical_datum)
    if kind == "categorical" and method != "nearest":
        raise ConstraintError("categorical values require nearest-neighbour resampling")
    if kind not in ("continuous", "categorical") or method not in (
        "nearest",
        "bilinear",
        "cubic",
        "average",
    ):
        raise ConstraintError("unsupported variable kind or resampling method")
    if min(shape) <= 0 or shape[0] * shape[1] > max_cells:
        raise CoastMASError("RASTER_LIMIT", "destination raster cell budget exceeded")
    destination = Grid(np.full(shape, np.nan), crs, transform, grid.unit, grid.vertical_datum)
    values = destination.values.copy()
    try:
        reproject(
            source=grid.values,
            destination=values,
            src_transform=grid.transform,
            src_crs=grid.crs,
            src_nodata=np.nan,
            dst_transform=transform,
            dst_crs=crs,
            dst_nodata=np.nan,
            resampling=Resampling[method],
            num_threads=1,
            warp_mem_limit=64,
        )
    except RasterioError as exc:
        raise CoastMASError("CRS_ERROR", "raster reprojection failed") from exc
    return Grid(values, crs, transform, grid.unit, grid.vertical_datum)
