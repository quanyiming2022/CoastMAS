"""Installed indicator kernels v1: native masks, physical values, explicit spatial support.

This implementation is hash-pinned by the recipe registry. New algorithms must
publish a new implementation version rather than changing historical snapshots.
"""

import hashlib
from contextlib import ExitStack

import fiona
import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window
from shapely.geometry import Point, shape
from shapely.ops import transform as transform_geometry
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .geospatial_view import data_mask, georeference
from .preparation import grid
from .profiles import vector_target
from .store import Problem


def ratio(numerator, denominator, mask):
    valid = mask & np.isfinite(numerator) & np.isfinite(denominator) & (denominator != 0)
    values = np.full(numerator.shape, np.nan, dtype="float64")
    np.divide(numerator, denominator, out=values, where=valid)
    valid &= np.isfinite(values)
    return values, valid


def spectral(code, bands, masks, parameters):
    valid = np.logical_and.reduce(list(masks.values()))
    if code in {"indicator.ndvi", "indicator.evi", "indicator.savi"}:
        red, nir = bands["red"], bands["nir"]
        if code == "indicator.evi":
            return ratio(
                parameters["gain"] * (nir - red),
                nir
                + parameters["red_coefficient"] * red
                - parameters["blue_coefficient"] * bands["blue"]
                + parameters["background"],
                valid,
            )
        if code == "indicator.savi":
            return ratio(
                (1 + parameters["soil_factor"]) * (nir - red),
                nir + red + parameters["soil_factor"],
                valid,
            )
        return ratio(nir - red, nir + red, valid)
    left, right = {
        "indicator.ndwi": ("green", "nir"),
        "indicator.mndwi": ("green", "swir1"),
        "indicator.ndbi": ("swir1", "nir"),
    }[code]
    return ratio(bands[left] - bands[right], bands[left] + bands[right], valid)


def preflight(settings, draft, sources):
    from .indicator_registry import require_definition, validate_parameters

    selection = draft["options"]["indicator_selection"]
    definition = require_definition(selection["indicator_id"], selection["definition_version"])
    if definition != selection["definition"]:
        raise Problem(409, "INDICATOR_VERSION", "指标定义与固定版本不一致")
    parameters = validate_parameters(definition, selection["parameters"])
    chosen = selection["candidate"]
    if chosen["mode"] != "compute":
        raise Problem(422, "INDICATOR_REUSE", "已有指标直接引用，无需重新计算")
    if [
        {"asset_id": a["id"], "revision": a["revision"], "sha256": a["sha256"]} for a in sources
    ] != chosen["sources"]:
        raise Problem(409, "INDICATOR_SOURCE", "指标输入版本已经改变")
    family = definition["default_algorithm"]
    reference = sources[1] if family == "road_density" else sources[0]
    with rasterio.open(settings.storage_root / reference["object_key"]) as ds:
        status, _, issue = georeference(ds)
        if status != "located":
            raise Problem(422, "SOURCE_LOCATION", issue)
        target_grid = grid(ds)
        if family == "road_density":
            crs = CRS(ds.crs)
            if not crs.is_projected or not all(a.unit_name == "metre" for a in crs.axis_info):
                raise Problem(422, "ROAD_METRIC_GRID", "道路密度需要已确认的米制参考网格")
        if family == "spectral":
            for band in chosen["bindings"].values():
                if band not in ds.indexes:
                    raise Problem(422, "BAND_MISSING", "影像缺少匹配的波段")
    if family == "urban_speed":
        with rasterio.open(settings.storage_root / sources[1]["object_key"]) as second:
            if grid(second) != target_grid:
                raise Problem(422, "GRID_ALIGNMENT", "两期分类网格尚未对齐")
    return {
        "id": definition["indicator_id"],
        "version": definition["version"],
        "operator": "builtin_indicator",
        "definition": definition,
        "parameters": parameters,
        "candidate": chosen,
        "output_grid": target_grid,
        "expected_outputs": [
            {"name": "indicator.tif", "role": "raw_indicator", "view_kind": "raster"}
        ],
    }


def _area(ds, window):
    """Actual geodesic cell area, or analytic area for an explicitly equal-area CRS."""
    crs = CRS(ds.crs)
    method = crs.coordinate_operation.method_name.lower() if crs.coordinate_operation else ""
    if crs.is_projected and "equal area" in method:
        factor = crs.axis_info[0].unit_conversion_factor
        return np.full(
            (int(window.height), int(window.width)), abs(ds.transform.determinant) * factor**2
        )
    transform = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
    geod = crs.get_geod()
    areas = np.empty((int(window.height), int(window.width)))
    for r in range(int(window.height)):
        for c in range(int(window.width)):
            col, row = c + window.col_off, r + window.row_off
            xy = [
                ds.transform * (col + dx, row + dy) for dx, dy in [(0, 0), (1, 0), (1, 1), (0, 1)]
            ]
            lon, lat = transform.transform(*zip(*xy, strict=True))
            areas[r, c] = abs(geod.polygon_area_perimeter(lon, lat)[0])
    return areas


def _roads(settings, source, target_crs, layer):
    lines = []
    with fiona.open(
        vector_target(settings.storage_root / source["object_key"], source["facts"]["profile"]),
        layer=None if source["facts"]["profile"] == "geojson" else layer,
    ) as ds:
        project = Transformer.from_crs(ds.crs, target_crs, always_xy=True).transform
        for item in ds:
            if item.geometry:
                geom = shape(item.geometry)
                if not geom.is_valid or geom.geom_type not in {"LineString", "MultiLineString"}:
                    raise Problem(422, "ROAD_GEOMETRY", "道路存在无效或非线几何")
                lines.append(transform_geometry(project, geom))
                if len(lines) > 1000000:
                    raise Problem(
                        422,
                        "ROAD_RESOURCE_BUDGET",
                        "道路线段超过此内置窗口算法的内存预算，请按研究范围建立空间索引",
                    )
    return lines, STRtree(lines)


def compute(settings, manifest, cancelled, artifact_dir):
    method = preflight(settings, manifest["draft"], manifest["assets"])
    if method != manifest["method"]:
        raise Problem(409, "INDICATOR_CHANGED", "固定指标计划已变化")
    definition = method["definition"]
    family = definition["default_algorithm"]
    sources = manifest["assets"]
    chosen = method["candidate"]
    params = method["parameters"]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / "indicator.tif"
    count = 0
    totals = [0.0, 0.0]
    area_valid = 0.0
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(GDAL_CACHEMAX=64 * 1024**2))
        reference = sources[1] if family == "road_density" else sources[0]
        ds = stack.enter_context(rasterio.open(settings.storage_root / reference["object_key"]))
        second = (
            stack.enter_context(rasterio.open(settings.storage_root / sources[1]["object_key"]))
            if family == "urban_speed"
            else None
        )
        target = stack.enter_context(
            rasterio.open(
                path,
                "w",
                driver="GTiff",
                width=ds.width,
                height=ds.height,
                count=1,
                dtype="float64",
                nodata=np.nan,
                crs=ds.crs,
                transform=ds.transform,
                tiled=True,
                blockxsize=256,
                blockysize=256,
                compress="deflate",
            )
        )
        if family == "road_density":
            lines, index = _roads(settings, sources[0], ds.crs, chosen["bindings"]["road_layer"])
        for row in range(0, ds.height, 256):
            for col in range(0, ds.width, 256):
                if cancelled.is_set():
                    raise Problem(409, "CANCELLED", "指标计算已取消")
                window = Window(col, row, min(256, ds.width - col), min(256, ds.height - row))
                if family == "spectral":
                    values, masks = {}, {}
                    for role, band in chosen["bindings"].items():
                        values[role], masks[role] = data_mask(ds, band, window=window)
                    output, valid = spectral(definition["indicator_id"], values, masks, params)
                elif family == "urban_speed":
                    a, av = data_mask(ds, 1, window=window)
                    b, bv = data_mask(second, 1, window=window)
                    valid = av & bv
                    areas = _area(ds, window)
                    first = np.isin(a, chosen["bindings"]["codes"][0])
                    last = np.isin(b, chosen["bindings"]["codes"][1])
                    totals[0] += float(areas[valid & first].sum())
                    totals[1] += float(areas[valid & last].sum())
                    area_valid += float(areas[valid].sum())
                    # A transition map is not mislabeled as a per-pixel urban expansion rate.
                    output = first.astype(float) + 2 * last.astype(float)
                else:
                    _, valid = data_mask(ds, 1, window=window)
                    output = np.full(valid.shape, np.nan)
                    for rr, cc in zip(*np.where(valid), strict=True):
                        if cancelled.is_set():
                            raise Problem(409, "CANCELLED", "指标计算已取消")
                        x, y = ds.transform * (col + int(cc) + 0.5, row + int(rr) + 0.5)
                        circle = Point(x, y).buffer(params["radius_m"], quad_segs=64)
                        hits = index.query(circle, predicate="intersects")
                        clipped = [lines[int(i)].intersection(circle) for i in hits]
                        length = unary_union(clipped).length if clipped else 0.0
                        output[rr, cc] = length / circle.area * 1000.0  # km/km²
                count += int(valid.sum())
                target.write(np.where(valid, output, np.nan), 1, window=window)
        concept = (
            definition["semantic_type"] if family != "urban_speed" else "built_land_transition"
        )
        target.set_band_description(1, concept)
        target.set_band_unit(1, definition["unit"] if family != "urban_speed" else "1")
        target.update_tags(
            indicator_id=definition["indicator_id"]
            if family != "urban_speed"
            else "built_land_transition",
            indicator_version=str(definition["version"]),
            scope="full_grid",
            algorithm_version=definition["algorithm_version"],
        )
    stats = {"scope": "full_grid", "total_pixels": ds.width * ds.height, "valid_pixels": count}
    files = [
        _file(
            path,
            settings,
            "raw_indicator" if family != "urban_speed" else "transition",
            "raster",
            definition["name"] if family != "urban_speed" else "建设用地变化",
        )
    ]
    if family == "urban_speed":
        years = chosen["bindings"]["years"]
        speed = (totals[1] - totals[0]) / (years[1] - years[0])
        stats.update(
            area0_m2=totals[0],
            area1_m2=totals[1],
            valid_area_m2=area_valid,
            years=years,
            speed_m2_per_year=speed,
        )
        table = artifact_dir / "urban-expansion.csv"
        table.write_text(
            "year0,year1,area0_m2,area1_m2,common_valid_area_m2,speed_m2_per_year\n"
            + f"{years[0]},{years[1]},{totals[0]},{totals[1]},{area_valid},{speed}\n"
        )
        files.append(_file(table, settings, "indicator", "table", "城市扩张速度"))
    return {
        "scope": "full_grid",
        "operator": "builtin_indicator",
        "method": method,
        "statistics": stats,
        "business_validated": False,
        "files": files,
    }


def _file(path, settings, role, view, title):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "name": path.name,
        "key": str(path.relative_to(settings.storage_root)),
        "sha256": digest,
        "size": path.stat().st_size,
        "role": role,
        "view_kind": view,
        "title": title,
    }


def validate_outputs(manifest, data, root):
    for item in data["files"]:
        path = (root / item["key"]).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise Problem(422, "OUTPUT_CONTRACT", "指标产物缺失或路径越界")
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                raise Problem(422, "OUTPUT_CONTRACT", "指标产物校验失败")
        if item["view_kind"] == "raster":
            with rasterio.open(path) as ds:
                if (
                    grid(ds) != manifest["method"]["output_grid"]
                    or ds.count != 1
                    or ds.dtypes[0] != "float64"
                ):
                    raise Problem(422, "OUTPUT_CONTRACT", "指标产物网格不符合固定配置")
