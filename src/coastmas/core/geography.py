"""Versioned spatial entities with explicit CRS, validity and geometry semantics."""

from math import isclose, pi
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, FiniteFloat, JsonValue, model_validator
from pyproj import CRS
from pyproj.exceptions import CRSError
from shapely.geometry import shape  # type: ignore[import-untyped]
from shapely.validation import explain_validity  # type: ignore[import-untyped]

from coastmas.core.contracts import Contract, Name, Version

Position = tuple[FiniteFloat, FiniteFloat]
Line = Annotated[tuple[Position, ...], Field(min_length=2)]
Ring = Annotated[tuple[Position, ...], Field(min_length=4)]
PolygonCoordinates = Annotated[tuple[Ring, ...], Field(min_length=1)]


class PointGeometry(Contract):
    type: Literal["Point"]
    coordinates: Position


class MultiPointGeometry(Contract):
    type: Literal["MultiPoint"]
    coordinates: Annotated[tuple[Position, ...], Field(min_length=1)]


class LineGeometry(Contract):
    type: Literal["LineString"]
    coordinates: Line


class MultiLineGeometry(Contract):
    type: Literal["MultiLineString"]
    coordinates: Annotated[tuple[Line, ...], Field(min_length=1)]


class PolygonGeometry(Contract):
    type: Literal["Polygon"]
    coordinates: PolygonCoordinates


class MultiPolygonGeometry(Contract):
    type: Literal["MultiPolygon"]
    coordinates: Annotated[tuple[PolygonCoordinates, ...], Field(min_length=1)]


Geometry = (
    PointGeometry
    | MultiPointGeometry
    | LineGeometry
    | MultiLineGeometry
    | PolygonGeometry
    | MultiPolygonGeometry
)


def geometry_positions(geometry: Geometry) -> tuple[Position, ...]:
    if isinstance(geometry, PointGeometry):
        return (geometry.coordinates,)
    if isinstance(geometry, (MultiPointGeometry, LineGeometry)):
        return geometry.coordinates
    if isinstance(geometry, (MultiLineGeometry, PolygonGeometry)):
        return tuple(position for line in geometry.coordinates for position in line)
    return tuple(
        position for polygon in geometry.coordinates for ring in polygon for position in ring
    )


class GeographicEntity(Contract):
    id: Name
    name: Name
    version: Version
    type: Literal[
        "coast_segment",
        "wetland",
        "land_parcel",
        "administrative_unit",
        "management_unit",
        "water_body",
        "protection_zone",
        "custom",
    ]
    crs: Name
    geometry: Geometry
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None
    management_unit_id: Name | None = None
    properties: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def spatial_and_temporal_consistency(self) -> Self:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must follow valid_from")
        if self.management_unit_id == self.id:
            raise ValueError("management unit and geographic entity identifiers must be distinct")
        if self.type == "management_unit" and self.management_unit_id is None:
            raise ValueError("management units require their separate management_unit_id")
        if self.type == "coast_segment" and self.geometry.type not in {
            "LineString",
            "MultiLineString",
        }:
            raise ValueError("coast segments require line geometry")
        if self.type not in {"coast_segment", "custom"} and self.geometry.type not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise ValueError("area entities require polygon geometry")
        validate_geometry(self.geometry, self.crs)
        return self


def validate_geometry(geometry: Geometry, crs_name: str) -> None:
    try:
        crs = CRS.from_user_input(crs_name)
    except CRSError as exc:
        raise ValueError("invalid entity CRS") from exc
    if not (crs.is_geographic or crs.is_projected) or len(crs.axis_info) != 2:
        raise ValueError("entity CRS must be two-dimensional geographic or projected")
    if crs.is_geographic and any(
        not isclose(axis.unit_conversion_factor, pi / 180) for axis in crs.axis_info
    ):
        raise ValueError("geographic CRS axes must use degrees")
    positions = geometry_positions(geometry)
    if len(positions) > 100_000:
        raise ValueError("entity geometry exceeds 100000 vertices")
    if crs.is_geographic and any(abs(x) > 180 or abs(y) > 90 for x, y in positions):
        raise ValueError("geographic coordinates must be longitude/latitude degrees")
    polygons: tuple[PolygonCoordinates, ...] = ()
    if isinstance(geometry, PolygonGeometry):
        polygons = (geometry.coordinates,)
    elif isinstance(geometry, MultiPolygonGeometry):
        polygons = geometry.coordinates
    if any(ring[0] != ring[-1] for polygon in polygons for ring in polygon):
        raise ValueError("polygon rings must be explicitly closed")
    spatial = shape(geometry.model_dump())
    if spatial.is_empty or not spatial.is_valid:
        raise ValueError(f"invalid entity geometry: {explain_validity(spatial)}")
