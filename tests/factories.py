from datetime import UTC, datetime

from coastmas.core.contracts import DataAssetSpec, ModelSpec, SceneSpec, VariableSpec, WorkflowSpec


def variable(name="height", **changes):
    payload = dict(
        name=name,
        standard_name="elevation",
        description="Elevation",
        data_type="raster",
        unit="m",
        dimension="[length]",
        semantic_type="continuous",
        spatial_support="grid",
        temporal_support="instant",
        aggregation_type="intensive",
        nodata_policy="mask",
        required=True,
    )
    payload.update(changes)
    return VariableSpec.model_validate(payload)


def model(**changes):
    payload = dict(
        id="screen",
        name="screen",
        display_name="Screen",
        version=1,
        model_type="RASTER",
        description="test model",
        capabilities=["screen"],
        scientific_domain=["coastal"],
        inputs=[variable()],
        outputs=[variable("result")],
        parameters=[
            dict(name="increment", unit="m", minimum=0, maximum=10, default=None, required=True)
        ],
        spatial_scale=dict(minimum=1, maximum=100, unit="m"),
        temporal_scale=dict(minimum=1, maximum=86400, unit="s"),
        supported_geometry=["grid"],
        supported_crs=["EPSG:32650"],
        runtime_type="python",
        runtime_config={"handler": "screen"},
        constraints=[],
        validation_status="VALIDATED",
        validation_metrics={},
        references=[],
        owner="researcher",
        license="MIT",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        execution_status="EXECUTABLE",
    )
    payload.update(changes)
    return ModelSpec.model_validate(payload)


def asset(**changes):
    payload = dict(
        id="dem",
        name="DEM",
        type="raster",
        uri="s3://coastmas/dem.tif",
        format="GeoTIFF",
        crs="EPSG:32650",
        vertical_datum="demo-datum",
        spatial_extent=dict(west=0, south=0, east=100, north=100),
        time_start="2026-01-01T00:00:00Z",
        time_end="2026-12-31T00:00:00Z",
        time_resolution="1 hour",
        variables=[variable()],
        quality={"spatial_resolution_m": 10, "geometry": "grid", "validated": True},
        source="SYNTHETIC",
        license="CC0",
        version=1,
        checksum="a" * 64,
    )
    payload.update(changes)
    return DataAssetSpec.model_validate(payload)


def scene(**changes):
    payload = dict(
        id="scene",
        name="scene",
        version=1,
        management_goal="screen",
        study_area={
            "type": "Polygon",
            "coordinates": [[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]],
        },
        entity_types=["management_unit"],
        time_range={"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
        scenario_conditions={"vertical_datum": "demo-datum"},
        constraints=[],
        required_outputs=["result"],
        data_policy={},
        quality_requirements={},
    )
    payload.update(changes)
    return SceneSpec.model_validate(payload)


def workflow(**changes):
    payload = dict(
        id="wf",
        name="wf",
        version=1,
        scene_type="custom",
        nodes=[
            dict(
                id="screen-node", model_id="screen", model_version=1, parameters={"increment": 0.5}
            )
        ],
        edges=[],
        input_bindings=[
            dict(
                source={"id": "dem", "version": 1},
                target={"node_id": "screen-node", "variable": "height"},
                semantic_mapping="exact_standard_name",
                unit_conversion=None,
                crs_transform=None,
                resampling=None,
                temporal_transform=None,
                quality_check=[],
                status="VALIDATED",
            )
        ],
        parameter_bindings=[],
        constraints=[],
        validation_rules=[],
        execution_policy={"timeout_seconds": 60, "max_retries": 0},
        output_definition=[{"node_id": "screen-node", "variable": "result"}],
    )
    payload.update(changes)
    return WorkflowSpec.model_validate(payload)
