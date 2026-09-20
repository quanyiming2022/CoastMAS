"""Bounded parsing of real catalog files with explicit metadata provenance.

Structural validation does not establish the scientific accuracy of observations.
CSV and vector attribute units remain user declarations because these formats do
not carry a standard unit for each column. Native file units must match the catalog.
"""

import csv
import hashlib
import io
import json
import math
import stat
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePosixPath
from typing import cast

import netCDF4
import numpy as np
from fiona.io import MemoryFile as VectorMemoryFile  # type: ignore[import-untyped]
from fiona.io import ZipMemoryFile
from fiona.model import to_dict  # type: ignore[import-untyped]
from pydantic import JsonValue, TypeAdapter
from pyproj import CRS
from rasterio.io import MemoryFile as RasterMemoryFile  # type: ignore[import-untyped]
from shapely import orient_polygons  # type: ignore[import-untyped]
from shapely.geometry import shape  # type: ignore[import-untyped]

from coastmas.adapters.geofiles import decode_geotiff
from coastmas.core.contracts import Contract, DataAssetSpec, VariableSpec
from coastmas.core.errors import CoastMASError, ConstraintError

# All native NetCDF operations in this process use one thread (Unidata requirement).
# API inspection itself additionally runs in an isolated, deadline-bound process.
NETCDF_IO = ThreadPoolExecutor(max_workers=1, thread_name_prefix="coastmas-netcdf")

MAX_BYTES = 64 * 1024 * 1024
MAX_ITEMS = 100_000
MAX_CELLS = 4_000_000
JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class DataInspection(Contract):
    metadata: dict[str, JsonValue]
    preview: dict[str, JsonValue]


def _unique_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ConstraintError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ConstraintError("non-finite JSON number is forbidden")


def _numeric(values: JsonValue, variable: VariableSpec) -> None:
    if variable.data_type == "json":
        pending: list[tuple[JsonValue, int]] = [(values, 0)]
        nodes = 0
        while pending:
            item, level = pending.pop()
            nodes += 1
            if nodes > MAX_ITEMS or level > 64:
                raise ConstraintError("JSON container exceeds structure budget")
            if isinstance(item, float) and not math.isfinite(item):
                raise ConstraintError("JSON container contains a non-finite number")
            if isinstance(item, dict):
                pending.extend((value, level + 1) for value in item.values())
            elif isinstance(item, list):
                pending.extend((value, level + 1) for value in item)
        return
    stack: list[tuple[JsonValue, int]] = [(values, 0)]
    count = 0
    while stack:
        value, depth = stack.pop()
        count += 1
        if count > MAX_CELLS or depth > 64:
            raise ConstraintError("variable structure exceeds configured budget")
        if isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
        elif value is None:
            if variable.nodata_policy == "reject":
                raise ConstraintError("variable contains forbidden NoData")
        elif (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ConstraintError("numeric variable contains invalid values")
        elif variable.semantic_type == "categorical" and value != math.floor(value):
            raise ConstraintError("categorical variable contains fractional identifiers")


def _read_json(content: bytes) -> JsonValue:
    return JSON_VALUE.validate_python(
        json.loads(content, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    )


def _raster(content: bytes, asset: DataAssetSpec) -> DataInspection:
    if asset.type != "raster" or len(asset.variables) != 1:
        raise ConstraintError("raster inspection requires one declared band variable")
    grid = decode_geotiff(content)
    variable = asset.variables[0]
    if not asset.crs or CRS(asset.crs) != CRS(grid.crs):
        raise ConstraintError("file and catalog CRS differ")
    if variable.unit != grid.unit or asset.vertical_datum != grid.vertical_datum:
        raise ConstraintError("file unit or vertical datum differs from catalog")
    known = np.isfinite(grid.values)
    if variable.nodata_policy == "reject" and not np.all(known):
        raise ConstraintError("raster contains forbidden NoData")
    if variable.semantic_type == "categorical" and np.any(
        grid.values[known] != np.floor(grid.values[known])
    ):
        raise ConstraintError("categorical raster contains fractional identifiers")
    with RasterMemoryFile(content) as memory, memory.open(driver="GTiff") as dataset:
        layout = dataset.tags(ns="IMAGE_STRUCTURE").get("LAYOUT")
        if asset.format == "COG" and layout != "COG":
            raise ConstraintError("file is not a cloud-optimized GeoTIFF")
        bounds = [float(value) for value in dataset.bounds]
    if asset.spatial_extent is not None:
        expected = [
            asset.spatial_extent.west,
            asset.spatial_extent.south,
            asset.spatial_extent.east,
            asset.spatial_extent.north,
        ]
        if not np.allclose(bounds, expected, rtol=0, atol=1e-7):
            raise ConstraintError("file and declared spatial extent differ")
    preview: list[JsonValue] = [
        [float(value) if np.isfinite(value) else None for value in row[:10]]
        for row in grid.values[:10]
    ]
    reference = CRS(grid.crs)
    resolution: float | None = None
    if reference.is_projected:
        # Larger cell axis is conservative for applicability checks; rectangular grids preserved.
        x = (
            math.hypot(grid.transform.a, grid.transform.d)
            * reference.axis_info[0].unit_conversion_factor
        )
        y = (
            math.hypot(grid.transform.b, grid.transform.e)
            * reference.axis_info[1].unit_conversion_factor
        )
        resolution = max(x, y)
    return DataInspection(
        metadata={
            "validated": True,
            "crs": grid.crs,
            "geometry": "grid",
            "shape": list(grid.values.shape),
            "cell_count": int(grid.values.size),
            "nodata_cells": int(np.count_nonzero(~known)),
            "spatial_extent": bounds,
            "spatial_resolution_m": resolution,
            "unit_source": "file",
            "layout": layout,
        },
        preview={"values": preview},
    )


def _csv(content: bytes, asset: DataAssetSpec) -> DataInspection:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    fields = reader.fieldnames
    if not fields or len(set(fields)) != len(fields) or any(not name for name in fields):
        raise ConstraintError("CSV requires unique nonempty column names")
    if not {item.name for item in asset.variables if item.data_type != "json"}.issubset(fields):
        raise ConstraintError("CSV is missing a declared variable column")
    preview: list[JsonValue] = []
    count = 0
    for row in reader:
        count += 1
        if count > MAX_ITEMS:
            raise ConstraintError("CSV row budget exceeded")
        if None in row or any(value is None for value in row.values()):
            raise ConstraintError("CSV row has a different number of fields")
        for variable in asset.variables:
            if variable.data_type == "json":
                continue  # Table containers preserve entity keys and heterogeneous columns.
            raw = row[variable.name]
            _numeric(None if raw.strip() == "" else float(raw), variable)
        if count <= 10:
            preview.append(cast(dict[str, JsonValue], dict(row)))
    if count == 0:
        raise ConstraintError("CSV contains no observations")
    return DataInspection(
        metadata={
            "validated": True,
            "row_count": count,
            "columns": fields,
            "unit_source": "catalog_declaration",
        },
        preview={"rows": preview},
    )


def _archive(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        files = archive.infolist()
        if not files or len(files) > 32 or sum(item.file_size for item in files) > MAX_BYTES:
            raise ConstraintError("shapefile archive exceeds extraction budget")
        names = [item.filename for item in files]
        if len(set(names)) != len(names):
            raise ConstraintError("archive contains duplicate names")
        for item in files:
            path = PurePosixPath(item.filename)
            if (
                path.is_absolute()
                or len(path.parts) != 1
                or "\\" in item.filename
                or stat.S_ISLNK(item.external_attr >> 16)
                or item.flag_bits & 1
            ):
                raise ConstraintError("unsafe shapefile archive entry")
            if path.suffix.lower() not in {".shp", ".shx", ".dbf", ".prj", ".cpg"}:
                raise ConstraintError("unexpected shapefile archive component")
        shapes = [name for name in names if name.lower().endswith(".shp")]
        if len(shapes) != 1:
            raise ConstraintError("archive must contain exactly one shapefile")
        stem = PurePosixPath(shapes[0]).stem
        if not {stem + extension for extension in (".shp", ".shx", ".dbf", ".prj")}.issubset(names):
            raise ConstraintError("shapefile requires matching shp/shx/dbf/prj components")
        # Reading each bounded member verifies CRC before handing it to GDAL's archive reader.
        for item in files:
            archive.read(item)
        return shapes[0]


def _vector(content: bytes, asset: DataAssetSpec, *, full: bool = False) -> DataInspection:
    driver = {"GeoJSON": "GeoJSON", "Shapefile": "ESRI Shapefile", "GeoPackage": "GPKG"}[
        asset.format
    ]
    if asset.type != "vector":
        raise ConstraintError("vector format requires a vector catalog type")
    path = _archive(content) if asset.format == "Shapefile" else None
    if asset.format == "GeoJSON":
        document = _read_json(content)
        if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
            raise ConstraintError("GeoJSON must be a FeatureCollection")
        if "crs" in document:
            raise ConstraintError("GeoJSON must use RFC 7946 coordinates without legacy CRS")
    memory = ZipMemoryFile(content) if path else VectorMemoryFile(content)
    with memory:
        # Multi-layer packages require explicit selection; never choose the first silently.
        layers = memory.listlayers()
        if len(layers) != 1:
            raise ConstraintError("vector file must contain exactly one selected layer")
        collection = (
            memory.open(path=path, enabled_drivers=[driver])
            if path
            else memory.open(enabled_drivers=[driver])
        )
        with collection:
            crs = collection.crs_wkt
            if not crs or not asset.crs or CRS(crs) != CRS(asset.crs):
                raise ConstraintError("vector file and catalog CRS differ")
            count = 0
            preview: list[JsonValue] = []
            support_sizes: list[float] = []
            reference = CRS(crs)
            geometry_type = str(collection.schema["geometry"]).lower()
            for feature in collection:
                count += 1
                if count > MAX_ITEMS:
                    raise ConstraintError("vector feature budget exceeded")
                raw = to_dict(feature)
                geometry = raw.get("geometry")
                if geometry is None:
                    raise ConstraintError("vector feature geometry is missing")
                parsed = shape(geometry)
                if parsed.is_empty or not parsed.is_valid or parsed.has_z:
                    raise ConstraintError("vector geometry must be valid nonempty 2D")
                if not all(math.isfinite(value) for value in parsed.bounds):
                    raise ConstraintError("vector coordinates must be finite")
                if parsed.geom_type in {"Polygon", "MultiPolygon"}:
                    if reference.is_projected:
                        area = (
                            parsed.area
                            * reference.axis_info[0].unit_conversion_factor
                            * reference.axis_info[1].unit_conversion_factor
                        )
                    else:
                        geodesic = reference.get_geod()
                        if geodesic is None:
                            raise ConstraintError("CRS has no geodesic definition for polygon area")
                        area, _ = geodesic.geometry_area_perimeter(orient_polygons(parsed))
                        area = abs(area)
                    if not math.isfinite(area) or area <= 0:
                        raise ConstraintError("polygon cannot define a positive spatial support")
                    support_sizes.append(math.sqrt(area))
                properties = raw.get("properties", {})
                for variable in asset.variables:
                    if variable.data_type == "json":
                        continue  # Explicit feature-collection container, not an attribute column.
                    if variable.name not in properties:
                        raise ConstraintError("vector attribute variable is absent")
                    _numeric(JSON_VALUE.validate_python(properties[variable.name]), variable)
                if full or count <= 10:
                    preview.append(JSON_VALUE.validate_json(json.dumps(raw, allow_nan=False)))
            if count == 0:
                raise ConstraintError("vector file contains no features")
            bounds = [float(value) for value in collection.bounds]
    return DataInspection(
        metadata={
            "validated": True,
            "feature_count": count,
            "geometry": geometry_type,
            "spatial_support_m": max(support_sizes)
            if support_sizes
            else asset.quality.get("spatial_support_m"),
            "minimum_spatial_support_m": min(support_sizes) if support_sizes else None,
            "spatial_support_definition": "sqrt_feature_area"
            if support_sizes
            else "catalog_declaration",
            "crs": asset.crs,
            "spatial_extent": bounds,
            "unit_source": "catalog_declaration",
        },
        preview={"features": preview},
    )


def _netcdf(content: bytes, asset: DataAssetSpec) -> DataInspection:
    preview: dict[str, JsonValue] = {}
    shapes: dict[str, JsonValue] = {}
    with netCDF4.Dataset("catalog-memory.nc", memory=content) as dataset:
        cells = 0
        for declared in asset.variables:
            if declared.name not in dataset.variables:
                raise ConstraintError("NetCDF variable missing")
            variable = dataset.variables[declared.name]
            cells += math.prod(variable.shape)
            if cells > MAX_CELLS or len(variable.shape) > 8:
                raise ConstraintError("NetCDF array budget exceeded")
            if getattr(variable, "units", None) != declared.unit:
                raise ConstraintError("NetCDF unit differs from catalog")
        for declared in asset.variables:
            variable = dataset.variables[declared.name]
            values = np.ma.asarray(variable[:], dtype=np.float64)
            plain = np.ma.filled(values, np.nan)
            if np.any(np.isinf(plain)):
                raise ConstraintError("NetCDF contains infinity, not a declared missing value")
            flat = plain.reshape(-1)
            converted: list[JsonValue] = [
                float(value) if np.isfinite(value) else None for value in flat
            ]
            _numeric(converted, declared)
            preview[declared.name] = converted[:10]
            shapes[declared.name] = list(variable.shape)
    return DataInspection(
        metadata={
            "validated": True,
            "shapes": shapes,
            "unit_source": "file",
            "preview_layout": "flattened_first_10",
        },
        preview=preview,
    )


def inspect_data(content: bytes, asset: DataAssetSpec) -> DataInspection:
    if len(content) > MAX_BYTES:
        raise CoastMASError("DATA_LIMIT", "file exceeds inspection byte budget")
    if hashlib.sha256(content).hexdigest() != asset.checksum:
        raise CoastMASError("CHECKSUM_ERROR", "data checksum mismatch")
    if not asset.variables:
        raise ConstraintError("data requires at least one declared variable")
    try:
        if asset.format in {"GeoTIFF", "COG"}:
            report = _raster(content, asset)
        elif asset.format == "CSV":
            report = _csv(content, asset)
        elif asset.format in {"GeoJSON", "Shapefile", "GeoPackage"}:
            report = _vector(content, asset)
        elif asset.format == "NetCDF":
            report = NETCDF_IO.submit(_netcdf, content, asset).result()
        elif asset.format == "JSON":
            value = _read_json(content)
            if not isinstance(value, dict):
                raise ConstraintError("JSON data must map variable names to values")
            for variable in asset.variables:
                if variable.name not in value:
                    raise ConstraintError("JSON variable missing")
                _numeric(value[variable.name], variable)
            # Preview has its own byte budget and never silently returns an enormous object.
            preview = value if len(content) <= 8192 else {"message": "preview exceeds 8192 bytes"}
            report = DataInspection(
                metadata={"validated": True, "unit_source": "catalog_declaration"}, preview=preview
            )
        else:
            raise ConstraintError("service/database inspection requires a configured connector")
    except CoastMASError:
        raise
    except (
        ValueError,
        TypeError,
        OSError,
        RuntimeError,
        csv.Error,
        zipfile.BadZipFile,
        RecursionError,
    ) as exc:
        raise CoastMASError(
            "DATA_FORMAT", "file cannot be parsed under the declared format"
        ) from exc
    return report.model_copy(
        update={
            "metadata": {
                **report.metadata,
                "size_bytes": len(content),
                "checksum": asset.checksum,
                "validation_scope": "structure_and_declared_metadata",
            }
        }
    )


def read_data_value(content: bytes, asset: DataAssetSpec, variable_name: str) -> JsonValue:
    """Return full validated values, never the truncated preview, for execution bindings."""
    inspect_data(content, asset)
    declared = next((item for item in asset.variables if item.name == variable_name), None)
    if declared is None:
        raise ConstraintError("requested variable is absent from the catalog")
    if asset.format == "JSON":
        payload = _read_json(content)
        if not isinstance(payload, dict):
            raise ConstraintError("JSON data must be an object")
        return payload[variable_name]
    if asset.format == "CSV":
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        if declared.data_type == "json":
            rows: list[JsonValue] = [cast(dict[str, JsonValue], dict(row)) for row in reader]
            return {
                "rows": rows,
                "column_units": asset.quality.get("column_units", {}),
                "unit_source": "catalog_declaration",
            }
        return [float(row[variable_name]) if row[variable_name].strip() else None for row in reader]
    if asset.format == "NetCDF":
        return NETCDF_IO.submit(_netcdf_value, content, variable_name).result()
    if asset.format in {"GeoJSON", "Shapefile", "GeoPackage"}:
        if declared.data_type != "json":
            raise ConstraintError("vector execution binding requires an explicit feature container")
        collection = _vector(content, asset, full=True)
        return {
            "type": "FeatureCollection",
            "crs": asset.crs,
            "features": collection.preview["features"],
        }
    raise ConstraintError("this file type requires a raster binding")


def _netcdf_value(content: bytes, variable_name: str) -> JsonValue:
    with netCDF4.Dataset("binding-memory.nc", memory=content) as dataset:
        values = np.ma.asarray(dataset.variables[variable_name][:], dtype=np.float64)
        plain = np.ma.filled(values, np.nan)
        serializable = plain.astype(object)
        serializable[~np.isfinite(plain)] = None
        return JSON_VALUE.validate_python(serializable.tolist())
