"""Byte-detected format profiles with retained semantics and bounded previews."""

import csv
import json
import math
import zipfile
from pathlib import Path

import fiona
import numpy as np
import rasterio
from netCDF4 import Dataset
from pyproj import CRS
from rasterio.windows import Window
from shapely.geometry import shape

from . import csvw
from .store import Problem

PREVIEW_ROWS = 20


def clean(value):
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def field(name, kind, **metadata):
    return {"name": name, "data_type": kind, "unit": None, "concept": None, **metadata}


def base(profile, version=None):
    return {
        "profile": profile,
        "standard_version": version,
        "observed_period": None,
        "layers": [],
        "issues": [],
        "fact_scope": "file_metadata_not_scientific_approval",
    }


def json_object(p):
    if p.stat().st_size > 64 * 1024**2:
        raise Problem(422, "JSON_LIMIT", "JSON对象超过解析预算；原资料请按表格/栅格形式接入")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Problem(422, "DUPLICATE_KEY", f"JSON重复键：{key}")
            result[key] = value
        return result

    def constant(value):
        raise Problem(422, "NON_FINITE", "JSON不能包含非有限数")

    return json.loads(
        p.read_text(encoding="utf-8-sig"), object_pairs_hook=unique, parse_constant=constant
    )


def raster_facts(p):
    with rasterio.open(p) as ds:
        out = base("cog" if ds.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") == "COG" else "geotiff")
        out.update(
            crs=ds.crs.to_string() if ds.crs else None,
            bounds=list(ds.bounds),
            transform=list(ds.transform)[:6],
            width=ds.width,
            height=ds.height,
            cell_count=ds.width * ds.height,
        )
        if not ds.crs:
            out["issues"].append(
                {"code": "CRS_MISSING", "blocks": ["spatial"], "message": "坐标参考系缺失"}
            )
        elif ds.crs.is_geographic and (
            ds.bounds.left < -180
            or ds.bounds.right > 180
            or ds.bounds.bottom < -90
            or ds.bounds.top > 90
        ):
            out["issues"].append(
                {
                    "code": "CRS_BOUNDS_CONFLICT",
                    "blocks": ["spatial"],
                    "message": "文件经纬度坐标系与实际数值范围冲突，不能猜测更正",
                }
            )
        fields = []
        for band in range(1, ds.count + 1):
            fields.append(
                field(
                    f"band_{band}",
                    ds.dtypes[band - 1],
                    band=band,
                    unit=ds.units[band - 1],
                    description=ds.descriptions[band - 1],
                    metadata=ds.tags(band),
                    scale=ds.scales[band - 1],
                    offset=ds.offsets[band - 1],
                    nodata=clean(ds.nodatavals[band - 1]),
                )
            )
        raw = ds.read(1, window=Window(0, 0, min(10, ds.width), min(10, ds.height)), masked=True)
        physical = raw.astype(float) * ds.scales[0] + ds.offsets[0]
        out["layers"] = [
            {
                "name": "raster",
                "fields": fields,
                "preview": clean(physical.filled(np.nan)),
                "preview_scope": "top_left_window_physical_values",
                "row_count": ds.width * ds.height,
            }
        ]
        out["file_tags"] = ds.tags()
        return out


def vector_target(path, profile):
    # GDAL needs braces when a managed ZIP has a content hash rather than .zip suffix.
    return "/vsizip/{" + str(path) + "}" if profile == "shapefile" else str(path)


def vector_facts(p, profile, original=None):
    out = base(profile, "RFC7946" if profile == "geojson" else None)
    target = vector_target(p, profile)
    if profile == "shapefile":
        with zipfile.ZipFile(p) as archive:
            names = archive.namelist()
            if any(Path(n).is_absolute() or ".." in Path(n).parts for n in names):
                raise Problem(422, "ARCHIVE_PATH", "压缩包包含越界路径")
            if sum(i.file_size for i in archive.infolist()) > 2 * 1024**3:
                raise Problem(422, "ARCHIVE_LIMIT", "压缩包解压规模超过预算")
            stems = {str(Path(n).with_suffix("")) for n in names if n.lower().endswith(".shp")}
            if not stems:
                raise Problem(422, "SHAPEFILE_PARTS", "压缩包中没有Shapefile")
            for stem in stems:
                if not all(stem + ext in names for ext in [".shp", ".dbf", ".shx"]):
                    raise Problem(422, "SHAPEFILE_PARTS", "Shapefile配套文件不完整")
    for name in fiona.listlayers(target):
        with fiona.open(target, layer=name) as ds:
            crs = CRS.from_user_input(ds.crs).to_string() if ds.crs else None
            fields = [field(k, v) for k, v in ds.schema["properties"].items()]
            preview, invalid = [], 0
            count = 0
            for feature in ds:
                count += 1
                geometry = fiona.model.to_dict(feature.geometry) if feature.geometry else None
                if geometry is None or not shape(geometry).is_valid:
                    invalid += 1
                if len(preview) < PREVIEW_ROWS:
                    preview.append(
                        {
                            "type": "Feature",
                            "id": feature.id,
                            "properties": dict(feature.properties),
                            "geometry": geometry,
                        }
                    )
            if original is not None:
                preview = original[:PREVIEW_ROWS]
            out["layers"].append(
                {
                    "name": "features" if profile == "geojson" else name,
                    "fields": fields,
                    "crs": crs,
                    "geometry_type": ds.schema["geometry"],
                    "row_count": count,
                    "preview": clean(preview),
                    "invalid_geometries": invalid,
                }
            )
            if invalid:
                out["issues"].append(
                    {
                        "code": "INVALID_GEOMETRY",
                        "layer": name,
                        "count": invalid,
                        "blocks": ["spatial"],
                    }
                )
    if profile == "geopackage":
        import sqlite3

        connection = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        try:
            out["container_version"] = connection.execute("PRAGMA user_version").fetchone()[0]
        finally:
            connection.close()
    return out


def netcdf_facts(p):
    out = base("netcdf")
    with Dataset(p) as ds:
        attrs = {k: clean(ds.getncattr(k)) for k in ds.ncattrs()}
        out["standard_version"] = attrs.get("Conventions")
        out["attributes"] = attrs
        out["dimensions"] = {k: len(v) for k, v in ds.dimensions.items()}
        out["coordinates"] = {}
        fields, preview = [], {}
        for name, var in ds.variables.items():
            a = {k: clean(var.getncattr(k)) for k in var.ncattrs()}
            item = field(
                name,
                str(var.dtype),
                dimensions=list(var.dimensions),
                shape=list(var.shape),
                attributes=a,
                unit=a.get("units"),
                concept=a.get("standard_name"),
                cell_methods=a.get("cell_methods"),
                coordinates=a.get("coordinates"),
                grid_mapping=a.get("grid_mapping"),
            )
            fields.append(item)
            subset = tuple(slice(0, 10 if var.ndim == 1 else 2) for _ in var.shape)
            data = var[subset] if subset else var[...]
            if np.ma.isMaskedArray(data):
                data = (
                    data.astype(float).filled(np.nan)
                    if np.issubdtype(data.dtype, np.number)
                    else data.filled("")
                )
            preview[name] = clean(data)
            if name in ds.dimensions or a.get("axis") or a.get("standard_name") == "time":
                coordinate = {**a, "preview": preview[name]}
                bounds = a.get("bounds")
                if bounds and bounds in ds.variables:
                    b = ds.variables[bounds]
                    coordinate["bounds_values"] = clean(b[: min(len(b), PREVIEW_ROWS)])
                    coordinate["bounds_scope"] = "preview" if len(b) > PREVIEW_ROWS else "full"
                out["coordinates"][name] = coordinate
        out["layers"] = [
            {
                "name": "dataset",
                "fields": fields,
                "preview": preview,
                "preview_scope": "bounded_per_axis",
                "row_count": None,
            }
        ]
    from .temporal import candidates

    out["temporal_candidates"] = candidates(out)
    return out


def csv_facts(p, prefix):
    encoding = "utf-8-sig" if prefix.startswith(b"\xef\xbb\xbf") else "utf-8"
    try:
        sample = prefix.decode(encoding)
    except UnicodeDecodeError as exc:
        raise Problem(
            422, "ENCODING_UNRESOLVED", "编码无法确定；需要提供正确编码，而不是猜读"
        ) from exc
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error as exc:
        # A valid one-column CSV has no delimiter to sniff. Do not invent
        # separators for ambiguous multi-column text or accept binary content.
        if len(sample.splitlines()) >= 2 and not any(c in sample for c in ",;\t|\0"):
            dialect = csv.excel
        else:
            raise Problem(422, "DIALECT_UNRESOLVED", "未识别到可靠表格方言") from exc
    out = base("csv")
    out.update(
        encoding=encoding,
        dialect={
            "delimiter": dialect.delimiter,
            "quotechar": dialect.quotechar,
            "doublequote": dialect.doublequote,
        },
    )
    csv.field_size_limit(1024**2)
    with p.open(encoding=encoding, newline="") as source:
        reader = csv.reader(source, dialect)
        columns = next(reader, [])
        if (
            not columns
            or len(columns) > 512
            or len(set(columns)) != len(columns)
            or any(not k for k in columns)
        ):
            raise Problem(422, "CSV_HEADER", "字段名称必须非空、唯一，且不超过512列")
        rows, count = [], 0
        for row in reader:
            if not row:
                continue
            if len(row) != len(columns):
                raise Problem(422, "CSV_ROW", f"第{reader.line_num}行字段数量不一致")
            count += 1
            if len(rows) < PREVIEW_ROWS:
                rows.append(dict(zip(columns, row, strict=True)))
    out["layers"] = [
        {
            "name": "table",
            "fields": [field(k, "text") for k in columns],
            "row_count": count,
            "preview": rows,
        }
    ]
    return out


def inspect_file(p: Path):
    with p.open("rb") as source:
        prefix = source.read(16384)
    if not prefix:
        raise Problem(422, "EMPTY_FILE", "空文件不能作为数据资料")
    try:
        if prefix[:4] in {b"II*\0", b"MM\0*", b"II+\0", b"MM\0+"}:
            return raster_facts(p)
        if prefix.startswith(b"SQLite format 3"):
            return vector_facts(p, "geopackage")
        if prefix.startswith(b"PK\x03\x04"):
            description = csvw.metadata(p)
            if description is not None:
                return csvw.facts(p, description)
            return vector_facts(p, "shapefile")
        if prefix.startswith((b"CDF", b"\x89HDF\r\n\x1a\n")):
            return netcdf_facts(p)
        if prefix.lstrip(b"\xef\xbb\xbf \t\r\n").startswith((b"{", b"[")):
            obj = json_object(p)
            if (
                isinstance(obj, dict)
                and obj.get("type")
                in {
                    "FeatureCollection",
                    "Feature",
                    "Point",
                    "LineString",
                    "Polygon",
                    "MultiPoint",
                    "MultiLineString",
                    "MultiPolygon",
                }
                and not obj.get("stac_version")
            ):
                if "crs" in obj:
                    raise Problem(
                        422, "GEOJSON_CRS", "RFC7946对象不能使用旧crs成员隐式改变坐标解释"
                    )
                features = obj.get(
                    "features",
                    [obj]
                    if obj["type"] == "Feature"
                    else [{"type": "Feature", "properties": {}, "geometry": obj}],
                )
                return vector_facts(p, "geojson", features)
            out = base(
                "stac"
                if isinstance(obj, dict) and obj.get("stac_version")
                else "csvw"
                if isinstance(obj, dict) and "@context" in obj and "csvw" in str(obj["@context"])
                else "json"
            )
            out["document"] = obj
            out["standard_version"] = (
                obj.get("stac_version", obj.get("schema_version"))
                if isinstance(obj, dict)
                else None
            )
            out["layers"] = [
                {
                    "name": "document",
                    "fields": [field(str(k), type(v).__name__) for k, v in obj.items()]
                    if isinstance(obj, dict)
                    else [],
                    "preview": obj,
                    "row_count": len(obj),
                }
            ]
            return out
        return csv_facts(p, prefix)
    except Problem:
        raise
    except (
        ValueError,
        OSError,
        RuntimeError,
        csv.Error,
        fiona.errors.FionaError,
        rasterio.errors.RasterioError,
    ) as exc:
        raise Problem(422, "FILE_INVALID", "文件结构无法读取", {"reason": str(exc)[:300]}) from exc
