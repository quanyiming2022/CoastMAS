"""Explicit scene geometry, catalog extent coverage, and entity validity checks.

Catalog extent overlap is not a claim about valid pixels or observational quality.
Area ratios use an equal-area CRS; unsupported polar/dateline cases fail explicitly.
"""

from functools import partial
from typing import Literal, cast

from pydantic import Field, JsonValue, TypeAdapter, ValidationError
from pyproj import Transformer
from pyproj.exceptions import ProjError
from shapely.geometry import box, mapping, shape  # type: ignore[import-untyped]
from shapely.ops import transform  # type: ignore[import-untyped]

from coastmas.core.contracts import Contract, DataAssetSpec, Extent, SceneSpec, VersionReference
from coastmas.core.errors import ConstraintError
from coastmas.core.geography import (
    GeographicEntity,
    Geometry,
    geometry_positions,
    validate_geometry,
)

GEOMETRY: TypeAdapter[Geometry] = TypeAdapter(Geometry)
CoverageStatus = Literal["COVERED", "PARTIAL", "OUTSIDE", "UNKNOWN"]


class SceneCoverage(Contract):
    reference: VersionReference
    name: str
    spatial_fraction: float | None = Field(ge=0, le=1)
    temporal_coverage: bool | None
    status: CoverageStatus
    method: str
    footprint_wgs84: dict[str, JsonValue] | None = None


class SceneInspection(Contract):
    valid: bool
    study_area_wgs84: dict[str, JsonValue]
    data_coverage: tuple[SceneCoverage, ...]
    entity_coverage: tuple[SceneCoverage, ...]
    issues: tuple[str, ...]


def geographic_geometry(raw: dict[str, JsonValue], crs: str) -> dict[str, JsonValue]:
    try:
        geometry = GEOMETRY.validate_python(raw)
        validate_geometry(geometry, crs)
        transformer = Transformer.from_crs(
            crs, "EPSG:4326", always_xy=True, allow_ballpark=False, only_best=True
        )
        spatial = shape(geometry.model_dump())
        # Densify source edges before transforming; never substitute an identity CRS.
        width = max(spatial.bounds[2] - spatial.bounds[0], spatial.bounds[3] - spatial.bounds[1])
        vertices = len(geometry_positions(geometry))
        if width > 0 and vertices < 90_000:
            # Bound densification even for narrow polygons with many long edges.
            segment_length = max(width / 64, spatial.length / (90_000 - vertices))
            spatial = spatial.segmentize(segment_length)
        converted = transform(partial(transformer.transform, errcheck=True), spatial)
        result = cast(dict[str, JsonValue], dict(mapping(converted)))
        validated = GEOMETRY.validate_python(result)
        validate_geometry(validated, "EPSG:4326")
        return validated.model_dump(mode="json")
    except (ValidationError, ValueError, ProjError) as exc:
        raise ConstraintError("scene geometry or explicit CRS transformation is invalid") from exc


def inspect_scene(
    scene: SceneSpec, assets: list[DataAssetSpec], entities: list[GeographicEntity]
) -> SceneInspection:
    crs = scene.data_policy.get("study_area_crs")
    if not isinstance(crs, str) or not crs.strip():
        raise ConstraintError("scene study_area_crs must explicitly declare the AOI CRS")
    geographic = geographic_geometry(scene.study_area, crs)
    area = shape(geographic)
    if area.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ConstraintError("scene AOI must be Polygon or MultiPolygon")
    west, south, east, north = area.bounds
    if east - west > 180 or south < -86 or north > 86:
        raise ConstraintError("polar or dateline-crossing AOI requires an explicit regional method")
    equal_area = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)
    project = partial(equal_area.transform, errcheck=True)
    projected_area = transform(project, area)
    if projected_area.area <= 0:
        raise ConstraintError("scene AOI has no positive area")
    issues: list[str] = []
    data: list[SceneCoverage] = []
    for asset in assets:
        temporal = (
            asset.time_start <= scene.time_range.start and asset.time_end >= scene.time_range.end
            if asset.time_start is not None and asset.time_end is not None
            else None
        )
        fraction: float | None = None
        footprint: dict[str, JsonValue] | None = None
        extent = asset.spatial_extent
        method = "catalog_extent_equal_area_EPSG6933"
        measured = asset.quality.get("spatial_extent")
        if (
            extent is None
            and asset.type in {"raster", "vector"}
            and asset.quality.get("validated") is True
            and isinstance(measured, list)
        ):
            if len(measured) != 4 or any(
                isinstance(value, bool) or not isinstance(value, (int, float)) for value in measured
            ):
                raise ConstraintError("verified file extent metadata is malformed")
            try:
                extent = Extent.model_validate(
                    dict(zip(("west", "south", "east", "north"), measured, strict=True))
                )
            except ValidationError as exc:
                raise ConstraintError("verified file extent metadata is invalid") from exc
            method = "inspected_extent_equal_area_EPSG6933"
        if extent is not None and asset.crs is not None:
            footprint = geographic_geometry(
                cast(
                    dict[str, JsonValue],
                    dict(mapping(box(extent.west, extent.south, extent.east, extent.north))),
                ),
                asset.crs,
            )
            intersection = projected_area.intersection(transform(project, shape(footprint)))
            fraction = min(1.0, max(0.0, intersection.area / projected_area.area))
        status: CoverageStatus = (
            "UNKNOWN"
            if fraction is None or temporal is None
            else "OUTSIDE"
            if fraction == 0
            else "COVERED"
            if fraction >= 1 - 1e-9 and temporal
            else "PARTIAL"
        )
        if status != "COVERED":
            issues.append(f"data {asset.id}@{asset.version}: {status}; catalog extent/time only")
        data.append(
            SceneCoverage(
                reference=VersionReference(id=asset.id, version=asset.version),
                name=asset.name,
                spatial_fraction=fraction,
                temporal_coverage=temporal,
                status=status,
                method=method,
                footprint_wgs84=footprint,
            )
        )
    entity_rows: list[SceneCoverage] = []
    for entity in entities:
        if entity.type not in scene.entity_types:
            issues.append(f"entity {entity.id}@{entity.version}: type not declared by scene")
        footprint = geographic_geometry(entity.geometry.model_dump(mode="json"), entity.crs)
        spatial = shape(footprint)
        intersects = area.intersects(spatial)
        temporal = entity.valid_from <= scene.time_range.start and (
            entity.valid_to is None or entity.valid_to >= scene.time_range.end
        )
        status = "OUTSIDE" if not intersects else "COVERED" if temporal else "PARTIAL"
        if status != "COVERED":
            issues.append(f"entity {entity.id}@{entity.version}: {status}")
        entity_rows.append(
            SceneCoverage(
                reference=VersionReference(id=entity.id, version=entity.version),
                name=entity.name,
                spatial_fraction=None,
                temporal_coverage=temporal,
                status=status,
                method="entity_intersection_and_validity",
                footprint_wgs84=footprint,
            )
        )
    return SceneInspection(
        valid=not issues,
        study_area_wgs84=geographic,
        data_coverage=tuple(data),
        entity_coverage=tuple(entity_rows),
        issues=tuple(issues),
    )
