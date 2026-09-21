"""Versioned demonstration catalog derived from checked-in real sample files.

All inputs are explicitly synthetic. Initialization only inserts absent v1
resources; it never resets current versions, permissions, flags, or user edits.
"""

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import JsonValue
from sqlalchemy.orm import Session

from coastmas.adapters.geofiles import decode_geotiff
from coastmas.adapters.storage import S3ArtifactStore
from coastmas.core.contracts import (
    DataAssetSpec,
    SceneSpec,
    VariableSpec,
    VersionReference,
    WorkflowSpec,
)
from coastmas.core.data_inspection import inspect_data
from coastmas.core.errors import CoastMASError
from coastmas.core.planning import build_template_plan, parse_template_goal
from coastmas.domain.builtin_catalog import BuiltinCatalog
from coastmas.domain.coastal_catalog import coastal_catalog, coastal_sample_scene
from coastmas.domain.indicator_frames import IndicatorFrame
from coastmas.domain.scenarios import verify_samples
from coastmas.persistence.resources import (
    create_resource,
    fingerprint,
    read_resource,
    require_permission,
)
from coastmas.persistence.schema import Resource


@dataclass(frozen=True)
class SampleProject:
    catalog: BuiltinCatalog
    assets: dict[str, DataAssetSpec]
    scenes: dict[str, SceneSpec]
    workflows: dict[str, WorkflowSpec]


def _save(
    session: Session, owner: str, project: str, kind: str, spec: dict[str, JsonValue]
) -> None:
    identifier, name = str(spec["id"]), str(spec["name"])
    existing = session.get(Resource, identifier)
    if existing is not None:
        if existing.project_id != project or existing.kind != kind:
            raise CoastMASError("SEED_CONFLICT", "sample identity is owned by another resource")
        old = read_resource(session, user_id=owner, identifier=identifier, version=1)
        original = old.spec
        if kind == "scene":
            # The original checksum was verified by read_resource; optional reference
            # defaults are normalized without rewriting the immutable source version.
            original = SceneSpec.model_validate(original).model_dump(mode="json")
        if fingerprint(original) != fingerprint(spec):
            raise CoastMASError("SEED_CONFLICT", "sample v1 differs; a new release is required")
        return
    create_resource(
        session,
        user_id=owner,
        project_id=project,
        kind=kind,
        identifier=identifier,
        name=name,
        spec=spec,
    )


def _frames(directory: Path) -> tuple[IndicatorFrame, IndicatorFrame]:
    records: dict[tuple[int, str], tuple[float, float]] = {}
    with (directory / "economic.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            key = int(row["year"]), row["unit_id"]
            if key in records:
                raise CoastMASError("SAMPLE_INVALID", "duplicate unit-period indicator observation")
            records[key] = float(row["economic"]), float(row["pressure"])
    years = sorted({year for year, _ in records})
    units = sorted({unit for _, unit in records})
    if (
        len(years) < 2
        or not units
        or any((year, unit) not in records for year in years for unit in units)
    ):
        raise CoastMASError("SAMPLE_INVALID", "sample indicators have incomplete period coverage")
    columns = [
        {
            "name": name,
            "unit": "1",
            "reference_unit": "1",
            "lower": 0,
            "upper": 100,
            "positive": positive,
            "weight": 1,
        }
        for name, positive in [("economic", True), ("pressure", False)]
    ]
    cube = [[records[(year, unit)] for unit in units] for year in years]
    temporal = IndicatorFrame.model_validate(
        {
            "unit_ids": units,
            "columns": columns,
            "values": cube,
            "years": years,
            "class_breaks": [0.25, 0.5, 0.75],
        }
    )
    single = IndicatorFrame.model_validate(
        {
            "unit_ids": units,
            "columns": columns,
            "values": cube[0],
            "years": None,
            "class_breaks": [0.25, 0.5, 0.75],
        }
    )
    return single, temporal


def _container(name: str, standard: str, *, spatial: str = "management_unit") -> VariableSpec:
    return VariableSpec(
        name=name,
        standard_name=standard,
        description="Synthetic sample container",
        data_type="json",
        unit="1",
        dimension="dimensionless",
        semantic_type="continuous",
        spatial_support=spatial,
        temporal_support="declared_period",
        aggregation_type="intensive",
        nodata_policy="reject",
        required=True,
    )


def seed_project(
    session: Session, owner: str, project: str, store: S3ArtifactStore, directory: Path
) -> SampleProject:
    require_permission(session, owner, project, "write")
    manifest = verify_samples(directory)
    catalog = coastal_catalog(project, directory)
    components = {
        str(model.runtime_config["component"]): model
        for model in catalog.models
        if model.id == f"builtin:{project}:{model.runtime_config['component']}"
    }
    for model in catalog.models:
        _save(session, owner, project, "model", model.model_dump(mode="json"))
    coastal = coastal_sample_scene(directory, identifier=f"sample:{project}:scene-A")
    assets: dict[str, DataAssetSpec] = {}
    signatures = {
        "dem.tif": next(item for item in components["screening"].inputs if item.name == "dem"),
        "land_cover_t1.tif": next(
            item for item in components["overlay"].inputs if item.name == "land_cover"
        ),
        "management_units.geojson": next(
            item for item in components["overlay"].inputs if item.name == "units"
        ),
        "population.csv": next(
            item for item in components["overlay"].inputs if item.name == "population"
        ),
        "economic.csv": _container("table", "economic_indicator_observations"),
        "tide.csv": _container("table", "tidal_level_observations", spatial="point"),
        "coastal_aoi.geojson": _container("features", "study_area_boundary", spatial="polygon"),
        "protection_zone.geojson": _container(
            "features", "protected_area_boundary", spatial="polygon"
        ),
    }
    signatures["land_cover_t2.tif"] = signatures["land_cover_t1.tif"]
    for filename, variable in signatures.items():
        content = (directory / filename).read_bytes()
        artifact = store.put(f"samples/{project}/v1/{filename}", content)
        crs, datum = None, None
        start, end = coastal.time_range.start, coastal.time_range.end
        quality: dict[str, JsonValue] = {
            "data_label": manifest.label,
            "time_source": "synthetic scenario validity, not observed survey coverage",
            "source_sample_sha256": manifest.sha256[filename],
        }
        if filename.endswith(".tif"):
            grid = decode_geotiff(content)
            kind, format_name = "raster", "GeoTIFF"
            crs, datum = grid.crs, grid.vertical_datum
            variable = variable.model_copy(update={"unit": grid.unit})
        elif filename.endswith(".geojson"):
            kind, format_name, crs = "vector", "GeoJSON", "EPSG:4326"
        else:
            kind, format_name = "table", "CSV"
            quality["column_units"] = {
                "population": "person",
                "economic": "1",
                "pressure": "1",
                "level_m": "m",
            }
        if filename == "tide.csv":
            start = end = datetime(2020, 1, 1, tzinfo=UTC)
            datum = manifest.vertical_datum
            quality["time_source"] = "timestamp in synthetic tide.csv"
        source = DataAssetSpec.model_validate(
            {
                "id": f"sample:{project}:data:{filename}",
                "name": filename,
                "type": kind,
                "format": format_name,
                "uri": artifact.uri,
                "checksum": artifact.sha256,
                "crs": crs,
                "vertical_datum": datum,
                "spatial_extent": None,
                "time_start": start,
                "time_end": end,
                "time_resolution": "1 day",
                "variables": [variable],
                "quality": quality,
                "source": manifest.label,
                "license": "CC0",
                "version": 1,
            }
        )
        inspected = inspect_data(content, source)
        source = source.model_copy(update={"quality": {**quality, **inspected.metadata}})
        _save(session, owner, project, "data", source.model_dump(mode="json"))
        assets[filename] = source
    single, temporal = _frames(directory)
    for label, frame in [("B", single), ("C", temporal)]:
        content = json.dumps(
            {"frame": frame.model_dump(mode="json")},
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        artifact = store.put(f"samples/{project}/v1/indicator-frame-{label}.json", content)
        source = DataAssetSpec(
            id=f"sample:{project}:data:frame-{label}",
            name=f"Synthetic indicator frame {label}",
            type="json",
            format="JSON",
            uri=artifact.uri,
            checksum=artifact.sha256,
            crs=None,
            vertical_datum=None,
            spatial_extent=None,
            time_start=coastal.time_range.start,
            time_end=datetime(2021 if label == "B" else 2023, 1, 1, tzinfo=UTC),
            time_resolution="1 year",
            variables=components["normalize"].inputs,
            quality={
                "data_label": manifest.label,
                "source_sample_sha256": manifest.sha256["economic.csv"],
                "derivation": "entity/period aligned columns from economic.csv; fixed [0,100]",
                "period_count": 1 if label == "B" else len(temporal.years or ()),
            },
            source=manifest.label,
            license="CC0",
            version=1,
        )
        inspected = inspect_data(content, source)
        source = source.model_copy(update={"quality": {**source.quality, **inspected.metadata}})
        _save(session, owner, project, "data", source.model_dump(mode="json"))
        assets[f"frame-{label}"] = source
    scenes = {"A": coastal}
    goals = {
        "A": "海岸影响筛查：海平面上升0.5米",
        "B": "可持续性评价：等权综合评价",
        "C": "多期变化评价：人工权重综合评价",
    }
    for label in ("B", "C"):
        scenes[label] = SceneSpec(
            id=f"sample:{project}:scene-{label}",
            name=f"Synthetic assessment scenario {label}",
            version=1,
            management_goal=goals[label],
            study_area=coastal.study_area,
            entity_types=("management_unit",),
            time_range=coastal.time_range.model_copy(
                update={"end": assets[f"frame-{label}"].time_end}
            ),
            scenario_conditions={
                "data_label": manifest.label,
                "period_policy": "fixed reference and shared weights",
            },
            constraints=(),
            required_outputs=("scores",) if label == "B" else ("scores", "change"),
            data_policy={"study_area_crs": "EPSG:4326"},
            quality_requirements={},
        )
    workflows = {}
    for label, scene in scenes.items():
        _save(session, owner, project, "scene", scene.model_dump(mode="json"))
        if label == "A":
            selected_files = {
                "screening.dem": "dem.tif",
                "overlay.land_cover": "land_cover_t1.tif",
                "overlay.units": "management_units.geojson",
                "overlay.population": "population.csv",
            }
        else:
            selected_files = {"normalize.frame": f"frame-{label}"}
        selected = {
            key: VersionReference(id=assets[name].id, version=1)
            for key, name in selected_files.items()
        }
        plan = build_template_plan(
            parse_template_goal(goals[label]),
            scene,
            catalog.models,
            tuple(assets.values()),
            catalog.registry,
            selected_data=selected,
        )
        if plan.candidate_workflow is None:
            raise CoastMASError(
                "SAMPLE_INVALID",
                "sample workflow failed scientific preflight",
                {"issues": [item.model_dump(mode="json") for item in plan.missing_conditions]},
            )
        workflow = plan.candidate_workflow
        _save(session, owner, project, "workflow", workflow.model_dump(mode="json"))
        workflows[label] = workflow
    return SampleProject(catalog=catalog, assets=assets, scenes=scenes, workflows=workflows)
