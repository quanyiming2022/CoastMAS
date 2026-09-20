from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from coastmas.core.contracts import EntityBinding, SceneSpec
from coastmas.core.errors import ConstraintError
from coastmas.core.geography import GeographicEntity
from coastmas.core.scene_workspace import inspect_scene
from tests.factories import asset, scene


def workspace_scene(**changes):
    return scene(
        study_area={"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]},
        data_policy={"study_area_crs": "EPSG:4326"},
        **changes,
    )


def test_scene_coverage_measures_explicit_footprints_and_time_without_inventing_unknowns():
    selected = asset(crs="EPSG:4326", spatial_extent={"west": 0, "south": 0, "east": 1, "north": 2})
    report = inspect_scene(
        workspace_scene(),
        [selected, selected.model_copy(update={"id": "unknown", "spatial_extent": None})],
        [],
    )
    first, unknown = report.data_coverage
    assert first.spatial_fraction == pytest.approx(0.5, abs=1e-6)
    assert first.temporal_coverage is True
    assert first.status == "PARTIAL"
    assert unknown.spatial_fraction is None
    assert unknown.status == "UNKNOWN"
    assert report.valid is False
    assert report.study_area_wgs84["type"] == "Polygon"


def test_scene_requires_explicit_valid_area_crs_and_rejects_invalid_geometry():
    with pytest.raises(ConstraintError, match="CRS"):
        inspect_scene(scene(data_policy={}), [], [])
    bad = workspace_scene().model_copy(
        update={"study_area": {"type": "Point", "coordinates": [0, 0]}}
    )
    with pytest.raises(ConstraintError):
        inspect_scene(bad, [], [])


def test_scene_entity_validity_and_area_intersection_are_checked_at_exact_versions():
    entity = GeographicEntity(
        id="entity",
        name="Unit",
        version=2,
        type="management_unit",
        crs="EPSG:4326",
        geometry=workspace_scene().study_area,
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_to=datetime(2026, 1, 2, tzinfo=UTC),
        management_unit_id="U1",
    )
    report = inspect_scene(workspace_scene(), [], [entity])
    assert report.entity_coverage[0].reference.version == 2
    assert report.entity_coverage[0].status == "COVERED"
    expired = entity.model_copy(update={"valid_to": datetime(2026, 1, 1, 12, tzinfo=UTC)})
    assert inspect_scene(workspace_scene(), [], [expired]).entity_coverage[0].status == "PARTIAL"


def test_scene_selected_references_are_typed_and_duplicate_versions_rejected():
    payload = workspace_scene().model_dump(mode="json")
    payload["entity_references"] = [{"id": "entity", "version": 2}]
    payload["data_references"] = [{"id": "data", "version": 3}]
    result = SceneSpec.model_validate(payload)
    assert result.entity_references[0].version == 2
    payload["entity_references"].append({"id": "entity", "version": 1})
    with pytest.raises(ValidationError):
        SceneSpec.model_validate(payload)


@pytest.mark.parametrize(
    "result_id,entity_id,unit_id",
    [("same", "same", "unit"), ("result", "same", "same"), ("same", "entity", "same")],
)
def test_result_entity_and_management_identifiers_are_distinct(result_id, entity_id, unit_id):
    with pytest.raises(ValidationError):
        EntityBinding(
            result_object_id=result_id,
            geographic_entity_id=entity_id,
            geographic_entity_version=1,
            management_unit_id=unit_id,
        )


def test_workflow_execution_preflight_rejects_missing_aoi_crs():
    from coastmas.core.validation import validate_workflow
    from tests.factories import model, workflow

    report = validate_workflow(workflow(), [model()], [asset()], scene(data_policy={}))
    assert not report.valid
    assert any(issue.code == "SCENE_GEOMETRY" for issue in report.issues)


def test_unknown_data_time_stays_unknown_instead_of_crashing_or_claiming_coverage():
    data = asset(time_start=None, time_end=None)
    row = inspect_scene(workspace_scene(), [data], []).data_coverage[0]
    assert row.temporal_coverage is None
    assert row.status == "UNKNOWN"


def test_coverage_uses_verified_file_extent_but_never_unverified_quality_claims():
    data = asset(
        crs="EPSG:4326",
        spatial_extent=None,
        quality={"validated": True, "spatial_extent": [0, 0, 2, 2]},
    )
    coverage = inspect_scene(workspace_scene(), [data], []).data_coverage[0]
    assert coverage.spatial_fraction == pytest.approx(1)
    assert coverage.method == "inspected_extent_equal_area_EPSG6933"
    unverified = data.model_copy(update={"quality": {**data.quality, "validated": False}})
    assert (
        inspect_scene(workspace_scene(), [unverified], []).data_coverage[0].spatial_fraction is None
    )
    table = data.model_copy(update={"type": "table"})
    assert inspect_scene(workspace_scene(), [table], []).data_coverage[0].spatial_fraction is None


def test_selected_scene_data_constrains_actual_workflow_input_versions():
    from coastmas.core.validation import validate_workflow
    from tests.factories import model, workflow

    mismatch = scene(data_references=[{"id": "other-data", "version": 1}])
    report = validate_workflow(workflow(), [model()], [asset()], mismatch)
    assert not report.valid
    assert any(issue.code == "SCENE_DATA_SELECTION" for issue in report.issues)
    selected = scene(data_references=[{"id": "dem", "version": 1}])
    assert validate_workflow(workflow(), [model()], [asset()], selected).valid


def test_instant_scene_at_entity_expiry_is_not_covered():
    instant = workspace_scene(
        time_range={"start": "2026-01-02T00:00:00Z", "end": "2026-01-02T00:00:00Z"}
    )
    entity = GeographicEntity(
        id="expired",
        name="Unit",
        version=1,
        type="management_unit",
        crs="EPSG:4326",
        geometry=instant.study_area,
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_to=datetime(2026, 1, 2, tzinfo=UTC),
        management_unit_id="U1",
    )
    assert inspect_scene(instant, [], [entity]).entity_coverage[0].temporal_coverage is False
