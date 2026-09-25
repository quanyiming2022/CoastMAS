"""Disk-bounded raster intake. Registration and scientific validation are separate."""

import hashlib
import math
from pathlib import Path
from typing import BinaryIO, cast

import numpy as np
import rasterio  # type: ignore[import-untyped]
from pydantic import Field, JsonValue
from pyproj import CRS
from rasterio.windows import Window  # type: ignore[import-untyped]

from coastmas.core.business_intake import inspect_raster
from coastmas.core.contracts import Contract, DataAssetSpec, Name
from coastmas.core.data_inspection import DataInspection
from coastmas.core.errors import CoastMASError, ConstraintError

MAX_FILE_BYTES = 2 * 1024**3


class IntakeDeclaration(Contract):
    name: Name
    source: Name
    license: Name
    year: int | None = Field(default=None, strict=True, ge=1, le=9999)


def snapshot_file(source: BinaryIO, target: Path) -> str:
    digest = hashlib.sha256()
    size = 0
    with target.open("xb") as output:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                raise CoastMASError("DATA_LIMIT", "file exceeds 2 GiB disk intake limit")
            digest.update(chunk)
            output.write(chunk)
    if not size:
        raise ConstraintError("empty file cannot be imported")
    return digest.hexdigest()


def inspect_raster_file(path: Path, asset: DataAssetSpec | None = None) -> DataInspection:
    with path.open("rb") as source:
        if source.read(4) not in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
            raise ConstraintError("automatic raster intake requires actual GeoTIFF bytes")
    try:
        # Shared fact reader never infers scientific definitions or rewrites source metadata.
        facts = inspect_raster(path, path.parent)
        facts.pop("path", None)
        issues = cast(list[JsonValue], facts["issues"])
        issues[:] = [item for item in issues if item != "EXCEEDS_WEB_UPLOAD_LIMIT"]
        if asset is not None and asset.checksum != facts["sha256"]:
            raise CoastMASError("CHECKSUM_ERROR", "stored file checksum mismatch")
        with rasterio.open(path, driver="GTiff") as dataset:
            values = dataset.read(
                1, window=Window(0, 0, min(10, dataset.width), min(10, dataset.height)), masked=True
            )
            preview: list[JsonValue] = [
                [
                    None
                    if np.ma.is_masked(value) or not math.isfinite(float(value))
                    else float(value)
                    for value in row
                ]
                for row in values
            ]
            metadata: dict[str, JsonValue] = {
                "validated": False,
                "ingestion_state": "INGESTED_PENDING_MAPPING",
                "size_bytes": facts["size_bytes"],
                "checksum": facts["sha256"],
                "file_facts": facts,
                "validation_scope": "file_structure_only",
                "crs": facts["crs"],
                "geometry": "grid",
                "shape": [dataset.height, dataset.width],
                "cell_count": dataset.width * dataset.height,
            }
            if asset is None or not asset.variables:
                return DataInspection(metadata=metadata, preview={"values": preview})
            if asset.type != "raster":
                raise ConstraintError("GeoTIFF requires a raster catalog type")
            if dataset.count != 1 or len(asset.variables) != 1:
                raise ConstraintError(
                    "select one explicit raster band before scientific validation"
                )
            if "GEOGRAPHIC_BOUNDS_INVALID" in issues or not dataset.crs:
                raise ConstraintError(
                    "raster coordinates require verified correction before computation"
                )
            if not asset.crs or CRS(asset.crs) != CRS(dataset.crs):
                raise ConstraintError("file and catalog CRS differ")
            variable = asset.variables[0]
            unit = dataset.units[0] or dataset.tags(1).get("unit") or dataset.tags().get("unit")
            if unit and unit != variable.unit:
                raise ConstraintError("file and catalog units differ; explicit conversion required")
            if (dataset.tags().get("vertical_datum") or None) != asset.vertical_datum:
                raise ConstraintError("file and catalog vertical datum differ")
            if dataset.scales[0] != 1 or dataset.offsets[0] != 0:
                raise ConstraintError(
                    "nonidentity scale/offset requires an explicit physical-value mapping"
                )
            if asset.spatial_extent:
                extent = asset.spatial_extent
                if not np.allclose(
                    dataset.bounds,
                    [extent.west, extent.south, extent.east, extent.north],
                    rtol=0,
                    atol=1e-7,
                ):
                    raise ConstraintError("file and declared spatial extent differ")
            if asset.format == "COG" and dataset.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") != "COG":
                raise ConstraintError("file is not a cloud-optimized GeoTIFF")
            valid_count = 0
            minimum, maximum = math.inf, -math.inf
            # Fixed windows rather than native blocks: an untrusted TIFF may be one huge strip.
            for y in range(0, dataset.height, 512):
                for x in range(0, dataset.width, 512):
                    block = dataset.read(
                        1,
                        window=Window(
                            x, y, min(512, dataset.width - x), min(512, dataset.height - y)
                        ),
                        masked=True,
                    )
                    known = block.compressed()
                    if np.any(np.isinf(known)):
                        raise ConstraintError("raster contains infinity")
                    known = known[np.isfinite(known)]
                    if variable.nodata_policy == "reject" and known.size != block.size:
                        raise ConstraintError("raster contains forbidden NoData")
                    if variable.semantic_type == "categorical" and np.any(known != np.floor(known)):
                        raise ConstraintError("categorical raster contains fractional values")
                    valid_count += int(known.size)
                    if known.size:
                        minimum = min(minimum, float(known.min()))
                        maximum = max(maximum, float(known.max()))
            reference = CRS(dataset.crs)
            resolution = None
            if reference.is_projected:
                transform = dataset.transform
                resolution = max(
                    math.hypot(transform.a, transform.d)
                    * reference.axis_info[0].unit_conversion_factor,
                    math.hypot(transform.b, transform.e)
                    * reference.axis_info[1].unit_conversion_factor,
                )
            metadata.update(
                {
                    "validated": True,
                    "ingestion_state": "MAPPED_STRUCTURE_VALIDATED",
                    "validation_scope": "structure_and_declared_metadata",
                    "unit_source": "file" if unit else "catalog_declaration",
                    "spatial_extent": list(dataset.bounds),
                    "spatial_resolution_m": resolution,
                    "nodata_cells": dataset.width * dataset.height - valid_count,
                    "valid_cells": valid_count,
                    "statistics_scope": "full",
                    "minimum": minimum if valid_count else None,
                    "maximum": maximum if valid_count else None,
                }
            )
            return DataInspection(metadata=metadata, preview={"values": preview})
    except CoastMASError:
        raise
    except (OSError, ValueError, RuntimeError) as exc:
        raise CoastMASError("DATA_FORMAT", "GeoTIFF cannot be read") from exc
