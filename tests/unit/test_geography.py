from copy import deepcopy

import pytest
from pydantic import ValidationError

from coastmas.core.geography import GeographicEntity


def entity_payload():
    return {
        "id": "entity-one",
        "name": "Management unit one",
        "version": 1,
        "type": "management_unit",
        "management_unit_id": "U1",
        "crs": "EPSG:4326",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[117, 31], [117.01, 31], [117.01, 31.01], [117, 31.01], [117, 31]]],
        },
        "valid_from": "2020-01-01T00:00:00Z",
        "valid_to": None,
        "properties": {"source": "synthetic test"},
    }


def test_entity_preserves_geometry_version_and_distinct_management_identity():
    entity = GeographicEntity.model_validate(entity_payload())
    assert entity.id != entity.management_unit_id
    assert entity.geometry.type == "Polygon"
    assert entity.version == 1
    assert entity.valid_from.utcoffset().total_seconds() == 0


@pytest.mark.parametrize(
    "change",
    [
        {"crs": "not-a-crs"},
        {"valid_to": "2019-01-01T00:00:00Z"},
        {"valid_from": "2020-01-01"},
        {"management_unit_id": "entity-one"},
        {"management_unit_id": None},
        {"geometry": {"type": "Point", "coordinates": [117, 31]}},
        {
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 1], [0, 1], [1, 0], [0, 0]]],
            }
        },
        {
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[117, 31], [118, 31], [118, 32], [117, 32]]],
            }
        },
        {
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[500000, 3500000], [500100, 3500000], [500100, 3500100], [500000, 3500000]]
                ],
            }
        },
    ],
)
def test_invalid_geometry_crs_time_or_identity_is_rejected(change):
    with pytest.raises(ValidationError):
        GeographicEntity.model_validate({**deepcopy(entity_payload()), **change})


def test_coast_segments_and_projected_polygons_are_explicitly_supported():
    line = GeographicEntity.model_validate(
        {
            **entity_payload(),
            "type": "coast_segment",
            "management_unit_id": None,
            "geometry": {"type": "LineString", "coordinates": [[117, 31], [117.01, 31.01]]},
        }
    )
    assert line.type == "coast_segment"
    projected = GeographicEntity.model_validate(
        {
            **entity_payload(),
            "crs": "EPSG:32650",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[500000, 3500000], [500100, 3500000], [500100, 3500100], [500000, 3500000]]
                ],
            },
        }
    )
    assert projected.crs == "EPSG:32650"


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [117, 31]},
        {"type": "MultiPoint", "coordinates": [[117, 31], [118, 32]]},
        {"type": "MultiLineString", "coordinates": [[[117, 31], [118, 32]]]},
        {"type": "MultiPolygon", "coordinates": [[[[117, 31], [118, 31], [118, 32], [117, 31]]]]},
    ],
)
def test_custom_entities_support_all_declared_geometry_families(geometry):
    entity = GeographicEntity.model_validate(
        {**entity_payload(), "type": "custom", "geometry": geometry}
    )
    assert entity.geometry.type == geometry["type"]


@pytest.mark.parametrize(
    "change",
    [
        {"crs": "EPSG:4979"},
        {"crs": "EPSG:4807"},
        {"valid_to": "2020-01-01T00:00:00Z"},
        {"type": "coast_segment"},
        {"type": "custom", "geometry": {"type": "Point", "coordinates": [float("nan"), 31]}},
        {
            "type": "custom",
            "geometry": {"type": "LineString", "coordinates": [[117, 31], [117, 31]]},
        },
        {"type": "custom", "geometry": {"type": "MultiPoint", "coordinates": [[117, 31]] * 100001}},
    ],
)
def test_degenerate_unbounded_and_ambiguous_coordinate_contracts_are_rejected(change):
    with pytest.raises(ValidationError):
        GeographicEntity.model_validate({**entity_payload(), **change})


@pytest.mark.parametrize(
    "kind",
    [
        "wetland",
        "land_parcel",
        "administrative_unit",
        "management_unit",
        "water_body",
        "protection_zone",
    ],
)
def test_all_required_area_types_retain_their_distinct_type(kind):
    entity = GeographicEntity.model_validate({**entity_payload(), "type": kind})
    assert entity.type == kind
