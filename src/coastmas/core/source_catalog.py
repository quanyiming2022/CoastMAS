"""Source registrations contain scientific metadata and a connector identity, not secrets."""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from coastmas.core.contracts import Contract, Extent, Name, VariableSpec, Version


class DataAssetMetadata(Contract):
    name: Name
    type: Literal["raster", "vector", "table", "json"]
    format: Literal["GeoTIFF", "COG", "GeoJSON", "Shapefile", "GeoPackage", "CSV", "NetCDF", "JSON"]
    crs: str | None = None
    vertical_datum: str | None = None
    spatial_extent: Extent | None = None
    time_start: AwareDatetime | None = None
    time_end: AwareDatetime | None = None
    time_resolution: str | None = None
    variables: tuple[VariableSpec, ...]
    source: Name
    license: Name

    @model_validator(mode="after")
    def time_coverage(self) -> Self:
        if (self.time_start is None) != (self.time_end is None):
            raise ValueError("time coverage must supply both endpoints")
        if (
            self.time_start is not None
            and self.time_end is not None
            and self.time_end < self.time_start
        ):
            raise ValueError("time end precedes start")
        return self


class DataSourceSpec(Contract):
    id: Name
    name: Name
    version: Version
    connector_id: Name
    kind: Literal["http", "postgresql"]
    output: DataAssetMetadata

    @model_validator(mode="after")
    def database_output(self) -> Self:
        if self.kind == "postgresql" and (
            self.output.format != "CSV" or self.output.type != "table"
        ):
            raise ValueError("PostgreSQL snapshots require table/CSV metadata")
        return self


class SourceSnapshotRequest(Contract):
    expected_version: int = Field(ge=1)
    idempotency_key: Name
