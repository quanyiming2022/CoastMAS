"""Read-only intake of local business sources; never infer units, periods or class meanings."""

import copy
import hashlib
import json
import math
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import numpy as np
import rasterio  # type: ignore[import-untyped]
from pydantic import Field, JsonValue
from pyproj import CRS, Transformer
from rasterio.enums import Resampling  # type: ignore[import-untyped]

from coastmas.core.contracts import Contract

FULL_SCAN_CELLS = 400_000
MAX_FILES = 10_000


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def inspect_raster(path: Path, root: Path) -> dict[str, JsonValue]:
    before = path.stat()
    checksum = digest(path)
    issues = ["PERIOD_UNDECLARED", "SOURCE_LICENSE_UNCONFIRMED", "VARIABLE_MEANING_UNCONFIRMED"]
    with rasterio.open(path, "r") as dataset:
        crs = CRS(dataset.crs) if dataset.crs else None
        bounds = [float(value) for value in dataset.bounds]
        geographic_invalid = bool(
            crs
            and crs.is_geographic
            and (bounds[0] < -180 or bounds[2] > 180 or bounds[1] < -90 or bounds[3] > 90)
        )
        if geographic_invalid:
            issues.append("GEOGRAPHIC_BOUNDS_INVALID")
        if crs is None:
            issues.append("CRS_MISSING")
        if dataset.count != 1:
            issues.append("MULTIBAND_MAPPING_REQUIRED")
        if before.st_size > 64 * 1024 * 1024:
            issues.append("EXCEEDS_WEB_UPLOAD_LIMIT")
        if dataset.width * dataset.height > 4_000_000:
            issues.append("EXCEEDS_CURRENT_EXECUTION_GRID_LIMIT")
        unit = dataset.units[0] or dataset.tags(1).get("unit") or dataset.tags().get("unit")
        if not unit:
            issues.append("UNIT_UNDECLARED")
        full = dataset.width * dataset.height <= FULL_SCAN_CELLS
        shape = (min(dataset.height, 256), min(dataset.width, 256))
        values = (
            dataset.read(1, masked=True)
            if full
            else dataset.read(1, out_shape=shape, masked=True, resampling=Resampling.nearest)
        )
        valid = values.compressed()
        valid = valid[np.isfinite(valid)]
        counts: list[JsonValue] = []
        if full and np.issubdtype(values.dtype, np.integer):
            identifiers, frequencies = np.unique(valid, return_counts=True)
            if len(identifiers) <= 256:
                counts = [
                    {"value": int(value), "count": int(count)}
                    for value, count in zip(identifiers, frequencies, strict=True)
                ]
                issues.append("CLASS_LABELS_UNCONFIRMED")
        wgs84: list[JsonValue] | None = None
        if crs and not geographic_invalid:
            try:
                transformed = Transformer.from_crs(
                    crs, "EPSG:4326", always_xy=True, allow_ballpark=False
                ).transform_bounds(
                    bounds[0], bounds[1], bounds[2], bounds[3], densify_pts=21, errcheck=True
                )
                if not all(math.isfinite(value) for value in transformed):
                    raise ValueError("non-finite transformed bounds")
                wgs84 = list(transformed)
            except Exception:
                issues.append("WGS84_TRANSFORM_UNAVAILABLE")
        transform = list(dataset.transform)[:6]
        grid = {
            "crs": crs.to_wkt() if crs else None,
            "transform": transform,
            "width": dataset.width,
            "height": dataset.height,
        }
        nodata = dataset.nodata
        result: dict[str, JsonValue] = {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": before.st_size,
            "sha256": checksum,
            "width": dataset.width,
            "height": dataset.height,
            "bands": dataset.count,
            "dtype": dataset.dtypes[0],
            "crs": dataset.crs.to_string() if dataset.crs else None,
            "bounds": cast(list[JsonValue], bounds),
            "wgs84_bounds": wgs84,
            "transform": cast(list[JsonValue], transform),
            "grid_id": hashlib.sha256(json.dumps(grid, sort_keys=True).encode()).hexdigest(),
            "nodata": nodata if nodata is None or math.isfinite(nodata) else str(nodata),
            "unit": unit,
            "observed_period": None,
            "scale": dataset.scales[0],
            "offset": dataset.offsets[0],
            "statistics_scope": "full" if full else "sample",
            "statistics_domain": "stored_values_before_scale_offset",
            "sample_cells": int(values.size),
            "sample_valid_cells": int(valid.size),
            "valid_cells": int(valid.size) if full else None,
            "nodata_cells": int(values.size - valid.size) if full else None,
            "minimum": float(valid.min()) if valid.size else None,
            "maximum": float(valid.max()) if valid.size else None,
            "value_counts": counts,
            "issues": cast(list[JsonValue], issues),
        }
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("source changed during inspection")
    return result


def inspect_package(description: Path, root: Path) -> dict[str, JsonValue]:
    fields: dict[str, str] = {}
    key = ""
    for line in description.read_text(encoding="utf-8-sig").splitlines():
        if line[:1].isspace() and key:
            fields[key] += " " + line.strip()
        elif ":" in line:
            key, value = line.split(":", 1)
            fields[key] = value.strip()
    name = fields.get("Package", description.parent.name)
    methods = {"PPCI": "projection_pursuit_clustering", "pprRFA": "projection_pursuit_regression"}
    return {
        "path": description.parent.relative_to(root).as_posix(),
        "name": name,
        "version": fields.get("Version"),
        "title": fields.get("Title"),
        "license": fields.get("License"),
        "dependencies": fields.get("Imports", fields.get("Depends")),
        "description_sha256": digest(description),
        "method": methods.get(name, "unclassified"),
        "execution_status": "NOT_EXECUTABLE",
        "issues": [
            "RUNTIME_NOT_APPROVED",
            "INPUT_BINDING_UNCONFIRMED",
            "BUSINESS_VALIDATION_REQUIRED",
        ],
    }


def inspect_directory(root: Path) -> dict[str, JsonValue]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("business source directory does not exist")
    rasters: list[JsonValue] = []
    models: list[JsonValue] = []
    errors: list[JsonValue] = []
    skipped: list[JsonValue] = []
    files: list[Path] = []
    for directory, names, filenames in os.walk(root, followlinks=False):
        for name in names[:]:
            path = Path(directory) / name
            if path.is_symlink() or name.startswith("."):
                names.remove(name)
                if path.is_symlink():
                    skipped.append(path.relative_to(root).as_posix())
        for name in filenames:
            path = Path(directory) / name
            if path.is_symlink():
                skipped.append(path.relative_to(root).as_posix())
            elif not name.startswith("."):
                files.append(path)
            if len(files) > MAX_FILES:
                raise ValueError("business source file budget exceeded")
    # Sidecar fingerprints preserve the provenance of GDAL metadata without interpreting
    # their class labels, timestamps or filenames as approved business semantics.
    sidecars: list[JsonValue] = []
    for path in sorted(files):
        try:
            if path.suffix.lower() in {".tif", ".tiff"}:
                rasters.append(inspect_raster(path, root))
            elif path.name == "DESCRIPTION":
                models.append(inspect_package(path, root))
            elif path.suffix.lower() in {".tfw", ".xml", ".dbf", ".cpg"}:
                sidecars.append({"path": path.relative_to(root).as_posix(), "sha256": digest(path)})
        except Exception as exc:
            errors.append(
                {"path": path.relative_to(root).as_posix(), "error_type": type(exc).__name__}
            )
    return {
        "kind": "coastmas_business_intake",
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_name": root.name,
        "scientific_execution_ready": False,
        "r_runtime_available": shutil.which("Rscript") is not None,
        "file_count": len(files),
        "rasters": rasters,
        "models": models,
        "errors": errors,
        "skipped_symlinks": skipped,
        "sidecars": sidecars,
    }


class BusinessDeclarations(Contract):
    year: int = Field(strict=True, ge=1, le=9999)
    source: str = Field(min_length=1, max_length=2000)
    use_restriction: str = Field(min_length=1, max_length=2000)
    units: dict[str, str] = Field(default_factory=dict)


def apply_declarations(
    report: dict[str, JsonValue], declarations: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    declared = BusinessDeclarations.model_validate(declarations)
    for prefix in declared.units:
        if not prefix.endswith("/") or prefix.startswith("/") or ".." in Path(prefix).parts:
            raise ValueError("unit group must be a relative directory prefix")
    result = copy.deepcopy(report)
    result["user_declarations"] = declared.model_dump(mode="json")
    for value in cast(list[JsonValue], result["rasters"]):
        row = cast(dict[str, JsonValue], value)
        row_issues = cast(list[JsonValue], row["issues"])
        row_issues.remove("PERIOD_UNDECLARED")
        row_issues.append("YEAR_ONLY_DECLARED")
        matches = [
            unit for prefix, unit in declared.units.items() if str(row["path"]).startswith(prefix)
        ]
        if len(matches) > 1:
            raise ValueError("overlapping unit declarations are ambiguous")
        if matches:
            row["declared_unit"] = matches[0]
            if "UNIT_UNDECLARED" in row_issues:
                row_issues.remove("UNIT_UNDECLARED")
            row_issues.append("UNIT_USER_DECLARED")
            if row["unit"] and row["unit"] != matches[0]:
                row_issues.append("UNIT_DECLARATION_DIFFERS_FROM_FILE")
    return result
