"""Prepare bounded statistical observations from immutable project raster assets."""

import hashlib
import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import cast
from uuid import uuid4

import pint
from fastapi import APIRouter, Request
from pydantic import Field, JsonValue, model_validator

from coastmas.adapters.runtime import PythonFunctionAdapter, RunRequest
from coastmas.app.data_routes import data_resource, stored_record
from coastmas.app.dependencies import CurrentUser, DatabaseSession, artifact_store
from coastmas.core.contracts import UNITS, Contract, DataAssetSpec, Name, TimeRange, VariableSpec
from coastmas.core.data_inspection import inspect_data
from coastmas.core.errors import CoastMASError, ConstraintError
from coastmas.core.file_ingestion import MAX_FILE_BYTES
from coastmas.core.raster_frame import RasterFeature, RasterFrameOptions, prepare_raster_frame
from coastmas.persistence.resources import add_dependencies, create_resource, require_permission
from coastmas.persistence.schema import Resource

router = APIRouter(prefix="/api/v1/data-assets", tags=["data"])


class FeatureBinding(RasterFeature):
    asset_id: Name
    version: int = Field(strict=True, ge=1)


class PrepareFrameRequest(Contract):
    project_id: Name
    name: Name
    features: tuple[FeatureBinding, ...] = Field(min_length=1, max_length=8)
    options: RasterFrameOptions
    period: TimeRange | None = None
    time_resolution: Name | None = None

    @model_validator(mode="after")
    def declared_time(self) -> "PrepareFrameRequest":
        if (self.period is None) != (self.time_resolution is None):
            raise ValueError("provide both period and temporal support, or neither")
        if self.time_resolution is not None:
            try:
                seconds = float(UNITS.Quantity(self.time_resolution).to("s").magnitude)
            except (pint.PintError, ValueError, TypeError) as exc:
                raise ValueError("temporal support must be a recognized time interval") from exc
            if not 0 < seconds < float("inf"):
                raise ValueError("temporal support must be a finite positive interval")
        return self


def _prepare(
    inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    paths = inputs.get("paths")
    features = inputs.get("features")
    if not isinstance(paths, list) or not isinstance(features, list):
        raise ConstraintError("private snapshot inputs missing")
    if not all(isinstance(path, str) for path in paths):
        raise ConstraintError("invalid private paths")
    return prepare_raster_frame(
        [Path(cast(str, path)) for path in paths],
        [RasterFeature.model_validate(feature) for feature in features],
        RasterFrameOptions.model_validate(parameters),
    )


@router.post("/prepare-raster-frame", status_code=201)
def prepare(
    body: PrepareFrameRequest, request: Request, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    require_permission(session, user_id, body.project_id, "write")
    store = artifact_store(request)
    lineage: list[JsonValue] = []
    assets: list[DataAssetSpec] = []
    total_size = 0
    with tempfile.TemporaryDirectory(prefix="coastmas-frame-") as temporary:
        paths: list[JsonValue] = []
        for index, binding in enumerate(body.features):
            asset = data_resource(binding.asset_id, session, user_id, binding.version)
            resource = session.get(Resource, binding.asset_id)
            if resource is None or resource.project_id != body.project_id:
                raise CoastMASError(
                    "AUTHORIZATION_ERROR", "source asset belongs to another project"
                )
            if asset.format not in {"GeoTIFF", "COG"}:
                raise ConstraintError("this preparation requires raster assets")
            record = stored_record(request, session, asset)
            total_size += record.size
            if total_size > 8 * 1024**3:
                raise ConstraintError("selected source files exceed the 8 GiB preparation budget")
            path = Path(temporary) / f"source-{index}.tif"
            store.read_file(record, path, max_bytes=MAX_FILE_BYTES)
            paths.append(str(path))
            assets.append(asset)
            lineage.append(
                {
                    **binding.model_dump(mode="json"),
                    "checksum": asset.checksum,
                    "unit_source": "explicit_preparation_declaration",
                    "source_declarations": asset.quality.get("declarations", {}),
                }
            )
        adapter = PythonFunctionAdapter({"prepare": _prepare}, max_output_bytes=16 * 1024**2)
        result = adapter.run(
            RunRequest(
                handler="prepare",
                inputs={
                    "paths": paths,
                    "features": [
                        item.model_dump(mode="json", exclude={"asset_id", "version"})
                        for item in body.features
                    ],
                },
                parameters=body.options.model_dump(mode="json", exclude_unset=True),
                work_root=Path(temporary),
                timeout_seconds=300,
            )
        ).outputs
        content = json.dumps(result, allow_nan=False, separators=(",", ":")).encode()
        checksum = hashlib.sha256(content).hexdigest()
        prepared = DataAssetSpec(
            id="data:" + uuid4().hex,
            name=body.name,
            type="json",
            format="JSON",
            uri="pending",
            checksum=checksum,
            crs="EPSG:4326",
            vertical_datum=None,
            spatial_extent=None,
            time_start=body.period.start if body.period else None,
            time_end=body.period.end if body.period else None,
            time_resolution=body.time_resolution,
            variables=(
                VariableSpec(
                    name="frame",
                    standard_name="projection_pursuit_frame",
                    description=(
                        "Explicit raster observations, units and preprocessing; "
                        "source cell IDs retained"
                    ),
                    data_type="json",
                    unit="1",
                    dimension="dimensionless",
                    semantic_type="continuous",
                    spatial_support="observation",
                    temporal_support="declared_period",
                    aggregation_type="intensive",
                    nodata_policy="reject",
                    required=True,
                ),
            ),
            source="Derived from immutable raster asset versions; see quality.lineage",
            license="; ".join(dict.fromkeys(asset.license for asset in assets)),
            version=1,
            quality={
                **cast(dict[str, JsonValue], result["quality"]),
                "lineage": lineage,
                "preparation": body.options.model_dump(mode="json", exclude_unset=True),
                "geometry": "point",
                "declared_period": body.period.model_dump(mode="json") if body.period else None,
                "business_validated": False,
            },
        )
        inspection = inspect_data(content, prepared)
        artifact = store.put(f"{body.project_id}/data/{uuid4().hex}/{checksum}", content)
        prepared = prepared.model_copy(
            update={
                "uri": artifact.uri,
                "quality": {
                    **prepared.quality,
                    **inspection.metadata,
                    "validation_scope": "prepared_observation_structure",
                    "business_validated": False,
                },
            }
        )
        revision = create_resource(
            session,
            user_id=user_id,
            project_id=body.project_id,
            kind="data",
            identifier=prepared.id,
            name=prepared.name,
            spec=prepared.model_dump(mode="json"),
        )
        add_dependencies(
            session,
            prepared.id,
            1,
            list(dict.fromkeys((asset.id, asset.version) for asset in assets)),
        )
        session.commit()
        return cast(dict[str, JsonValue], asdict(revision))
