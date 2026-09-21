import pytest

from coastmas.core.validation import validate_workflow
from tests.factories import asset, model, scene, variable, workflow


def report(**changes):
    args = dict(workflow=workflow(), models=[model()], assets=[asset()], scene=scene())
    args.update(changes)
    return validate_workflow(**args)


def test_valid_workflow_produces_verified_binding():
    result = report()
    assert result.valid
    assert len(result.bindings) == 1
    assert result.bindings[0].status == "VALIDATED"


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"models": []}, "MODEL_MISSING"),
        ({"models": [model(enabled=False)]}, "MODEL_DISABLED"),
        ({"models": [model(execution_status="NOT_EXECUTABLE")]}, "MODEL_NOT_EXECUTABLE"),
        ({"assets": []}, "DATA_MISSING"),
        ({"assets": [asset(crs=None)]}, "CRS_MISSING"),
        ({"assets": [asset(vertical_datum=None)]}, "VERTICAL_DATUM"),
        ({"assets": [asset(vertical_datum="wrong")]}, "VERTICAL_DATUM"),
        ({"assets": [asset(time_start=None, time_end=None)]}, "TIME_MISSING"),
        (
            {"assets": [asset(variables=[variable(unit="s", dimension="[time]")])]},
            "BINDING_INCOMPATIBLE",
        ),
        (
            {"assets": [asset(variables=[variable(standard_name="wave_height")])]},
            "BINDING_INCOMPATIBLE",
        ),
        (
            {
                "assets": [
                    asset(
                        quality={
                            "spatial_resolution_m": 1000,
                            "geometry": "grid",
                            "validated": True,
                        }
                    )
                ]
            },
            "SPATIAL_SCALE",
        ),
        (
            {
                "workflow": workflow(
                    nodes=[
                        {
                            "id": "screen-node",
                            "model_id": "screen",
                            "model_version": 1,
                            "parameters": {"increment": 20},
                        }
                    ]
                )
            },
            "PARAMETER_RANGE",
        ),
        ({"workflow": workflow(input_bindings=[])}, "INPUT_MISSING"),
    ],
)
def test_hard_constraint_failures_are_not_ranked(kwargs, code):
    result = report(**kwargs)
    assert not result.valid
    assert code in {issue.code for issue in result.issues}


def test_convertible_horizontal_crs_is_adapted_instead_of_rejected():
    result = report(assets=[asset(crs="EPSG:4326")])
    assert result.valid
    assert result.bindings[0].crs_transform == "EPSG:4326 -> EPSG:32650"


def test_unit_conversion_is_recorded_and_binding_status_is_not_trusted():
    result = report(assets=[asset(variables=[variable(unit="mm")])])
    assert result.valid
    assert result.bindings[0].unit_conversion == "mm -> m"


def test_output_unknown_variable_blocks():
    result = report(
        workflow=workflow(output_definition=[{"node_id": "screen-node", "variable": "fabricated"}])
    )
    assert not result.valid
    assert "OUTPUT_MISSING" in {issue.code for issue in result.issues}


def test_declared_constraint_is_enforced_before_execution():
    registered = model(
        constraints=[
            {
                "field": "parameters.increment",
                "operator": "le",
                "value": 0.25,
                "description": "reviewed calibration domain",
            }
        ]
    )
    result = report(models=[registered])
    assert not result.valid
    assert "DECLARED_CONSTRAINT" in {issue.code for issue in result.issues}


def test_unknown_constraint_path_cannot_silently_pass():
    registered = model(
        constraints=[
            {"field": "invented.path", "operator": "eq", "value": 1, "description": "unresolvable"}
        ]
    )
    result = report(models=[registered])
    assert not result.valid
    assert "DECLARED_CONSTRAINT" in {issue.code for issue in result.issues}


def test_invalid_temporal_unit_returns_structured_failure():
    result = report(assets=[asset(time_resolution="1 nonsense")])
    assert not result.valid
    assert "TEMPORAL_SCALE" in {issue.code for issue in result.issues}


def test_incompatible_resampling_is_a_report_not_an_unhandled_exception():
    payload = workflow().model_dump(mode="json")
    payload["input_bindings"][0]["resampling"] = "sum"
    result = report(workflow=workflow(**payload))
    assert not result.valid
    assert "RESAMPLING" in {issue.code for issue in result.issues}


def test_vector_scale_uses_explicit_spatial_support_not_raster_pixel_resolution():
    from coastmas.core.validation import validate_asset_binding
    from tests.factories import variable

    boundary = variable(
        data_type="json",
        standard_name="management_units",
        unit="1",
        dimension="dimensionless",
        spatial_support="management_unit",
    )
    candidate = model(inputs=[boundary], supported_geometry=["polygon"])
    data = asset(
        type="vector",
        variables=[boundary],
        quality={"validated": True, "geometry": "polygon", "spatial_support_m": 50},
    )
    report = validate_asset_binding(
        data, boundary, candidate, scene(), workflow().input_bindings[0]
    )
    assert report.valid, report.issues


def test_scene_target_grid_must_be_supported_by_the_model():
    context = scene(
        data_policy={
            "target_grid": {
                "crs": "EPSG:3857",
                "transform": [10, 0, 0, 0, -10, 20],
                "width": 2,
                "height": 2,
            }
        }
    )
    report = validate_workflow(workflow(), [model()], [asset()], context)
    assert not report.valid
    assert "CRS_UNSUPPORTED" in {issue.code for issue in report.issues}


@pytest.mark.parametrize("invalid", [None, "scene_period", "asset_period", "meaning", "cadence"])
def test_instantaneous_observation_requires_exact_time_and_acquisition_semantics(invalid):
    from coastmas.core.validation import validate_asset_binding

    timestamp = "2025-09-25T03:07:23.508Z"
    observation = variable(temporal_support="acquisition")
    candidate = model(inputs=[observation], temporal_scale={"unit": "s"})
    data = asset(
        variables=[observation],
        time_start=timestamp,
        time_end=timestamp,
        time_resolution="instantaneous",
    )
    context = scene(time_range={"start": timestamp, "end": timestamp})
    if invalid == "scene_period":
        context = scene(time_range={"start": timestamp, "end": "2025-09-26T00:00:00Z"})
    elif invalid == "asset_period":
        data = data.model_copy(update={"time_end": context.time_range.end.replace(day=26)})
    elif invalid == "meaning":
        observation = variable(temporal_support="instant")
        candidate = model(inputs=[observation], temporal_scale={"unit": "s"})
        data = data.model_copy(update={"variables": (observation,)})
    elif invalid == "cadence":
        candidate = model(inputs=[observation])
    result = validate_asset_binding(
        data, observation, candidate, context, workflow().input_bindings[0]
    )
    assert result.valid == (invalid is None), result.issues
    if invalid:
        assert {issue.code for issue in result.issues} & {"TIME_COVERAGE", "TEMPORAL_SCALE"}
