"""Publish checksum-verified optical acquisitions as immutable, reproducible demonstrations."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
from affine import Affine
from pydantic import AwareDatetime, BaseModel, ConfigDict, JsonValue
from rasterio.transform import array_bounds  # type: ignore[import-untyped]
from sqlalchemy.orm import Session

from coastmas.adapters.geofiles import decode_geotiff
from coastmas.adapters.storage import S3ArtifactStore
from coastmas.core.contracts import (
    DataAssetSpec,
    ModelSpec,
    SceneSpec,
    TargetGridSpec,
    WorkflowSpec,
)
from coastmas.core.data_inspection import inspect_data
from coastmas.core.errors import ConstraintError
from coastmas.core.scene_workspace import geographic_geometry
from coastmas.core.validation import validate_workflow
from coastmas.domain.optical_observations import OpticalPair
from coastmas.domain.remote_sensing_catalog import remote_sensing_catalog, variable
from coastmas.persistence.resources import require_permission
from coastmas.sample_bootstrap import SampleProject, _save

REGIONS = {
    "yellow-river": "黄河口",
    "jiaozhou": "胶州湾",
    "yangtze-2024": "长江口（2024）",
    "yangtze-2025": "长江口（2025）",
}


class Acquisition(BaseModel):
    # Preserve the full provider manifest in provenance; only consumed fields are typed here.
    model_config = ConfigDict(extra="ignore", frozen=True)
    calibration_policy: Literal["stac_matches_cog_v1"]
    item_id: str
    source: str
    acquired_at: AwareDatetime
    native_crs: str
    transform: tuple[float, float, float, float, float, float]
    width: int
    height: int
    display_bounds_wgs84: tuple[float, float, float, float]
    files: dict[str, str]

    @property
    def grid(self) -> TargetGridSpec:
        return TargetGridSpec(
            crs=self.native_crs, transform=self.transform, width=self.width, height=self.height
        )


def _extent(grid: TargetGridSpec) -> dict[str, float]:
    return dict(
        zip(
            ("west", "south", "east", "north"),
            array_bounds(grid.height, grid.width, Affine(*grid.transform)),
            strict=True,
        )
    )


def _aoi(grid: TargetGridSpec) -> dict[str, JsonValue]:
    bounds = _extent(grid)
    west, south, east, north = (bounds[key] for key in ("west", "south", "east", "north"))
    return geographic_geometry(
        {
            "type": "Polygon",
            "coordinates": [
                [
                    [west, south],
                    [east, south],
                    [east, north],
                    [west, north],
                    [west, south],
                ]
            ],
        },
        grid.crs,
    )


def _asset(
    session: Session,
    owner: str,
    project: str,
    store: S3ArtifactStore,
    source: DataAssetSpec,
    content: bytes,
) -> DataAssetSpec:
    measured = inspect_data(content, source)
    artifact = store.put(f"{project}/imagery/{source.checksum}", content)
    saved = source.model_copy(
        update={
            "uri": artifact.uri,
            "quality": {
                **source.quality,
                **measured.metadata,
                "size_bytes": artifact.size,
            },
        }
    )
    _save(session, owner, project, "data", saved.model_dump(mode="json"))
    return saved


def _scene_workflow(
    project: str,
    key: str,
    label: str,
    model: ModelSpec,
    grid: TargetGridSpec,
    assets: list[DataAssetSpec],
    start: datetime,
    end: datetime,
) -> tuple[SceneSpec, WorkflowSpec]:
    scene = SceneSpec.model_validate(
        {
            "id": f"imagery:{project}:scene:{key}",
            "name": label,
            "version": 1,
            "management_goal": label,
            "study_area": _aoi(grid),
            "entity_types": ["grid"],
            "time_range": {"start": start, "end": end},
            "scenario_conditions": {"data_label": "真实 Sentinel-2 L2A 影像；光谱指数示范"},
            "constraints": [],
            "required_outputs": ["index", "summary", "preview"],
            "data_policy": {
                "study_area_crs": "EPSG:4326",
                "target_grid": grid.model_dump(mode="json"),
            },
            "quality_requirements": {
                "nodata": "mask",
                "temporal_scope": "observed acquisitions only",
            },
            "data_references": [{"id": item.id, "version": item.version} for item in assets],
        }
    )
    workflow = WorkflowSpec.model_validate(
        {
            "id": f"imagery:{project}:workflow:{key}",
            "name": label + "工作流",
            "version": 1,
            "scene_type": "remote_sensing",
            "nodes": [
                {
                    "id": "optical",
                    "model_id": model.id,
                    "model_version": model.version,
                    "parameters": {},
                }
            ],
            "edges": [],
            "input_bindings": [
                {
                    "source": {"id": asset.id, "version": asset.version},
                    "target": {"node_id": "optical", "variable": port.name},
                    "semantic_mapping": "exact_standard_name",
                    "unit_conversion": None,
                    "crs_transform": None,
                    "resampling": "nearest",
                    "temporal_transform": None,
                    "quality_check": [],
                    "status": "MANUAL_REVIEW",
                }
                for asset, port in zip(assets, model.inputs, strict=True)
            ],
            "parameter_bindings": [],
            "constraints": [],
            "validation_rules": [],
            "execution_policy": {"timeout_seconds": 120, "max_retries": 0},
            "output_definition": [
                {"node_id": "optical", "variable": port.name} for port in model.outputs
            ],
        }
    )
    report = validate_workflow(workflow, [model], assets, scene)
    if not report.valid:
        raise ConstraintError(
            "imagery preflight failed", {"issues": [issue.message for issue in report.issues]}
        )
    return scene, workflow.model_copy(update={"input_bindings": report.bindings})


def seed_real_imagery(
    session: Session,
    owner: str,
    project: str,
    store: S3ArtifactStore,
    directory: Path,
) -> SampleProject:
    require_permission(session, owner, project, "write")
    acquisitions = {}
    for name in REGIONS:
        path = directory / name
        acquisition = Acquisition.model_validate_json((path / "manifest.json").read_bytes())
        for filename, digest in acquisition.files.items():
            if (
                Path(filename).name != filename
                or hashlib.sha256((path / filename).read_bytes()).hexdigest() != digest
            ):
                raise ConstraintError(
                    "imagery source file checksum differs from acquisition manifest"
                )
        acquisitions[name] = acquisition
    catalog = remote_sensing_catalog(project)
    models = {str(model.runtime_config["component"]): model for model in catalog.models}
    for model in catalog.models:
        _save(session, owner, project, "model", model.model_dump(mode="json"))
    assets: dict[str, DataAssetSpec] = {}
    previews: dict[str, dict[str, JsonValue]] = {}
    for name, acquisition in acquisitions.items():
        path = directory / name
        image = store.put(
            f"{project}/imagery/{acquisition.files['true-color.png']}",
            (path / "true-color.png").read_bytes(),
        )
        provenance = store.put(
            f"{project}/imagery/{acquisition.files['source-item.json']}",
            (path / "source-item.json").read_bytes(),
        )
        preview: dict[str, JsonValue] = {
            "uri": image.uri,
            "checksum": image.sha256,
            "size_bytes": image.size,
            "bounds": list(acquisition.display_bounds_wgs84),
            "label": REGIONS[name] + "真彩色",
            "attribution": "Copernicus Sentinel-2 / Earth Search",
            "acquired_at": acquisition.acquired_at.isoformat(),
        }
        previews[name] = preview
        for band in ("nir", "red", "green"):
            content = (path / (band + ".tif")).read_bytes()
            band_grid = decode_geotiff(content)
            if (
                band_grid.crs != acquisition.native_crs
                or tuple(band_grid.transform)[:6] != acquisition.transform
                or band_grid.values.shape != (acquisition.height, acquisition.width)
            ):
                raise ConstraintError("imagery band grid differs from acquisition manifest")
            source = DataAssetSpec.model_validate(
                {
                    "id": f"imagery:{project}:{name}:{band}",
                    "name": REGIONS[name]
                    + " · "
                    + {"nir": "近红外", "red": "红光", "green": "绿光"}[band],
                    "type": "raster",
                    "format": "GeoTIFF",
                    "uri": "s3://pending/data",
                    "checksum": hashlib.sha256(content).hexdigest(),
                    "crs": band_grid.crs,
                    "vertical_datum": None,
                    "spatial_extent": _extent(acquisition.grid),
                    "time_start": acquisition.acquired_at,
                    "time_end": acquisition.acquired_at,
                    "time_resolution": "instantaneous",
                    "variables": [variable(band, "surface_reflectance_" + band)],
                    "quality": {
                        "visualization": preview,
                        "source_item": acquisition.item_id,
                        "source_manifest": json.loads((path / "manifest.json").read_bytes()),
                        "source_metadata": {"uri": provenance.uri, "sha256": provenance.sha256},
                        "calibration": (
                            "STAC scale and offset; SCL 4/5/6 only; other pixels remain NoData"
                        ),
                    },
                    "source": acquisition.source,
                    "license": "Copernicus Sentinel data legal notice",
                    "version": 1,
                }
            )
            saved = _asset(session, owner, project, store, source, content)
            assets[saved.id] = saved
    scenes: dict[str, SceneSpec] = {}
    workflows: dict[str, WorkflowSpec] = {}
    for key, component, label in (
        ("yellow-river", "ndvi", "黄河口真实影像植被指数"),
        ("jiaozhou", "ndwi", "胶州湾真实影像水体指数"),
    ):
        acquisition = acquisitions[key]
        selected = [
            assets[f"imagery:{project}:{key}:{port.name}"] for port in models[component].inputs
        ]
        scenes[key], workflows[key] = _scene_workflow(
            project,
            key,
            label,
            models[component],
            acquisition.grid,
            selected,
            acquisition.acquired_at,
            acquisition.acquired_at,
        )
    first, second = acquisitions["yangtze-2024"], acquisitions["yangtze-2025"]
    if first.grid != second.grid:
        raise ConstraintError("two-date demo requires matching original grids")
    # Retain native 10 m cells in a bounded central window.
    # This does not downsample or imply coverage of the whole estuary.
    width, height = min(first.width, 128), min(first.height, 128)
    column, row = (first.width - width) // 2, (first.height - height) // 2
    transform = Affine(*first.transform) * Affine.translation(column, row)
    grid = TargetGridSpec(
        crs=first.native_crs, transform=tuple(transform)[:6], width=width, height=height
    )
    frames: list[dict[str, JsonValue]] = []
    source_refs: list[JsonValue] = []
    for name in ("yangtze-2024", "yangtze-2025"):
        acquisition = acquisitions[name]
        frame: dict[str, JsonValue] = {
            "acquired_at": acquisition.acquired_at.isoformat(),
            "source_item": acquisition.item_id,
            "grid": grid.model_dump(mode="json"),
        }
        for band in ("nir", "red"):
            source = assets[f"imagery:{project}:{name}:{band}"]
            source_refs.append(
                {"id": source.id, "version": source.version, "checksum": source.checksum}
            )
            values = decode_geotiff((directory / name / (band + ".tif")).read_bytes()).values[
                row : row + height, column : column + width
            ]
            frame[band] = [
                [float(value) if np.isfinite(value) else None for value in line] for line in values
            ]
        frames.append(frame)
    pair = OpticalPair.model_validate({"frames": frames})
    content = json.dumps(
        {"observations": pair.model_dump(mode="json")},
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    source = DataAssetSpec.model_validate(
        {
            "id": f"imagery:{project}:yangtze:observations",
            "name": "长江口双期真实反射率观测（原生10米窗口）",
            "type": "json",
            "format": "JSON",
            "uri": "s3://pending/data",
            "checksum": hashlib.sha256(content).hexdigest(),
            "crs": grid.crs,
            "vertical_datum": None,
            "spatial_extent": _extent(grid),
            "time_start": first.acquired_at,
            "time_end": second.acquired_at,
            "time_resolution": str((second.acquired_at - first.acquired_at).total_seconds())
            + " seconds",
            "variables": models["ndvi_change"].inputs,
            "quality": {
                "visualization": previews["yangtze-2025"],
                "sources": source_refs,
                "acquisition_count": 2,
                "continuous_temporal_coverage": False,
                "window": {"row": row, "column": column, "width": width, "height": height},
                "earlier_visualization": previews["yangtze-2024"],
            },
            "source": second.source,
            "license": "Copernicus Sentinel data legal notice",
            "version": 1,
        }
    )
    saved = _asset(session, owner, project, store, source, content)
    assets[saved.id] = saved
    scenes["yangtze"], workflows["yangtze"] = _scene_workflow(
        project,
        "yangtze",
        "长江口真实影像双期植被变化",
        models["ndvi_change"],
        grid,
        [saved],
        first.acquired_at,
        second.acquired_at,
    )
    for key, scene in scenes.items():
        _save(session, owner, project, "scene", scene.model_dump(mode="json"))
        _save(session, owner, project, "workflow", workflows[key].model_dump(mode="json"))
    return SampleProject(catalog, assets, scenes, workflows)
