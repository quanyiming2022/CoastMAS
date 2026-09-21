"""Checksum-verified storage-to-workflow bindings, never arbitrary URL fetches.

Authorization is performed by the job service against immutable resource
versions before constructing this resolver. Only its configured bucket is
accessible. CRS/grid changes require an explicit target grid in the scene.
"""

import json
from functools import partial
from urllib.parse import urlsplit

import numpy as np
from affine import Affine
from pydantic import JsonValue, TypeAdapter
from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError
from shapely.geometry import mapping, shape  # type: ignore[import-untyped]
from shapely.ops import transform as transform_geometry  # type: ignore[import-untyped]

from coastmas.adapters.geofiles import Grid, decode_geotiff, resample_grid
from coastmas.adapters.storage import ArtifactRecord, S3ArtifactStore
from coastmas.core.binding import convert_units, validate_semantics
from coastmas.core.contracts import BindingPlan, DataAssetSpec, SceneSpec, VariableSpec
from coastmas.core.contracts import TargetGridSpec as TargetGrid
from coastmas.core.data_inspection import inspect_data, read_data_value
from coastmas.core.errors import CoastMASError, ConstraintError
from coastmas.core.execution import transform_numeric

JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class StoredDataResolver:
    def __init__(self, store: S3ArtifactStore):
        self.store = store

    def resolve(
        self, asset: DataAssetSpec, target: VariableSpec, binding: BindingPlan, scene: SceneSpec
    ) -> JsonValue:
        address = urlsplit(asset.uri)
        if (
            address.scheme != "s3"
            or address.netloc != self.store.bucket
            or address.query
            or address.fragment
        ):
            raise CoastMASError("STORAGE_ERROR", "asset must use configured object storage")
        if binding.source.id != asset.id or binding.source.version != asset.version:
            raise ConstraintError("binding data version differs from resolved asset")
        size = asset.quality.get("size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ConstraintError("asset byte size metadata is required")
        content = self.store.read(
            ArtifactRecord(self.store.bucket, address.path.removeprefix("/"), asset.checksum, size)
        )
        candidates = [
            item for item in asset.variables if item.standard_name == target.standard_name
        ]
        if len(candidates) != 1:
            raise ConstraintError("binding requires one unambiguous source variable")
        source = candidates[0]
        validate_semantics(source, target, {})
        if binding.temporal_transform is not None:
            raise ConstraintError(
                "temporal binding requires an explicit time-series transformation node"
            )
        if asset.format in {"GeoTIFF", "COG"}:
            inspection = inspect_data(content, asset)
            measured = inspection.metadata.get("spatial_resolution_m")
            declared = asset.quality.get("spatial_resolution_m")
            if measured is not None and not isinstance(measured, (int, float)):
                raise ConstraintError("invalid measured raster resolution")
            if measured is not None and (
                isinstance(declared, bool)
                or not isinstance(declared, (float, int))
                or not np.isclose(declared, measured, rtol=1e-9, atol=0)
            ):
                raise ConstraintError("catalog resolution differs from the actual raster")
            grid = decode_geotiff(content)
            if (
                asset.type != "raster"
                or target.data_type != "raster"
                or not asset.crs
                or CRS(grid.crs) != CRS(asset.crs)
                or grid.unit != source.unit
                or grid.vertical_datum != asset.vertical_datum
            ):
                raise ConstraintError("GeoTIFF metadata differs from immutable data catalog")
            if source.semantic_type == "categorical":
                known = grid.values[np.isfinite(grid.values)]
                if np.any(known != np.floor(known)):
                    raise ConstraintError(
                        "categorical raster contains fractional class identifiers"
                    )
            converted = grid.values.copy()
            known_mask = np.isfinite(converted)
            if np.any(known_mask):
                converted[known_mask] = convert_units(
                    converted[known_mask], source.unit, target.unit
                )
            if target.nodata_policy == "reject" and not np.all(known_mask):
                raise ConstraintError("target does not accept NoData")
            grid = Grid(converted, grid.crs, grid.transform, target.unit, grid.vertical_datum)
            target_spec = scene.data_policy.get("target_grid")
            if binding.crs_transform and target_spec is None:
                raise ConstraintError("CRS transformation requires an explicit destination grid")
            if target_spec is not None:
                destination = TargetGrid.model_validate(target_spec)
                if binding.crs_transform is not None:
                    target_crs = binding.crs_transform.split(" -> ")[-1]
                    if CRS(destination.crs) != CRS(target_crs):
                        raise ConstraintError("destination grid differs from verified CRS binding")
                method = binding.resampling
                if method not in ("nearest", "bilinear", "cubic", "sum", "area_weighted"):
                    raise ConstraintError(
                        "grid binding requires an explicit supported resampling method"
                    )
                grid = resample_grid(
                    grid,
                    crs=destination.crs,
                    transform=Affine(*destination.transform),
                    shape=(destination.height, destination.width),
                    kind=source.semantic_type,
                    method=method,
                )
            values: list[JsonValue] = [
                [float(value) if np.isfinite(value) else None for value in row]
                for row in grid.values
            ]
            return values
        if asset.format in {"JSON", "CSV", "NetCDF", "GeoJSON", "Shapefile", "GeoPackage"}:
            value = read_data_value(content, asset, source.name)
            if asset.type == "vector" and binding.crs_transform is not None:
                value = reproject_features(value, asset.crs, binding.crs_transform)
            if source.unit != target.unit:
                value = transform_numeric(
                    value, source.unit, target.unit, allow_nodata=target.nodata_policy != "reject"
                )
            json.dumps(value, allow_nan=False)
            return value
        raise CoastMASError(
            "DATA_FORMAT_ERROR", "data format requires a registered ingestion adapter"
        )


def reproject_features(value: JsonValue, crs: str | None, declaration: str) -> JsonValue:
    if not isinstance(value, dict) or not isinstance(value.get("features"), list) or crs is None:
        raise ConstraintError("vector CRS binding requires a feature collection")
    parts = declaration.split(" -> ")
    if len(parts) != 2 or CRS(parts[0]) != CRS(crs):
        raise ConstraintError("vector source CRS differs from verified binding")
    try:
        transformer = Transformer.from_crs(
            crs, parts[1], always_xy=True, allow_ballpark=False, only_best=True
        )
        features = value["features"]
        if not isinstance(features, list):
            raise ConstraintError("invalid feature collection")
        transformed: list[JsonValue] = []
        for feature in features:
            if not isinstance(feature, dict) or not isinstance(feature.get("geometry"), dict):
                raise ConstraintError("feature geometry missing")
            geometry = transform_geometry(
                partial(transformer.transform, errcheck=True), shape(feature["geometry"])
            )
            transformed.append(
                JSON_VALUE.validate_json(
                    json.dumps({**feature, "geometry": mapping(geometry)}, allow_nan=False)
                )
            )
        return {**value, "features": transformed, "crs": parts[1]}
    except ProjError as exc:
        raise ConstraintError("vector coordinate transformation is unavailable") from exc
