import pytest

from coastmas.core.errors import ConstraintError
from coastmas.core.geography import GeographicEntity
from coastmas.core.result_entities import ResultObject, bind_result_objects
from coastmas.core.result_geography import result_entity_features
from tests.unit.test_geography import entity_payload


def test_result_map_uses_only_bound_snapshot_versions_and_explicit_projection():
    entity = GeographicEntity.model_validate(
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
    item = ResultObject(
        id="result-1",
        node_id="node",
        variable="scores",
        standard_name="assessment_scores",
        model={"id": "model", "version": 1},
        management_unit_id="U1",
        source_pointer="/outputs/node.scores",
    )
    view = bind_result_objects([item], [entity])
    unused = entity.model_copy(update={"id": "unused", "management_unit_id": "U2"})
    features = result_entity_features(view, [entity, unused])["features"]
    assert len(features) == 1
    assert features[0]["properties"] == {
        "entity_id": entity.id,
        "entity_version": 1,
        "management_unit_id": "U1",
    }
    longitude, latitude = features[0]["geometry"]["coordinates"][0][0]
    assert longitude == pytest.approx(117, abs=1e-7)
    assert latitude == pytest.approx(31.63518622, abs=1e-6)
    with pytest.raises(ConstraintError, match="snapshot"):
        result_entity_features(view, [entity.model_copy(update={"version": 2})])
    assert result_entity_features(bind_result_objects([item], []), [])["features"] == []
