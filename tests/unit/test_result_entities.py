from copy import deepcopy

import pytest

from coastmas.core.errors import ConstraintError
from coastmas.core.geography import GeographicEntity
from coastmas.core.result_entities import ResultObject, bind_result_objects, result_object_id
from coastmas.domain.result_views import management_objects
from tests.factories import model, variable, workflow
from tests.unit.test_geography import entity_payload


def test_result_objects_bind_exact_management_keys_to_pinned_entities_and_preserve_unbound():
    entity = GeographicEntity.model_validate(entity_payload())
    objects = [
        ResultObject(
            id=result_object_id("job", "node", "statistics", unit),
            node_id="node",
            variable="statistics",
            standard_name="coastal_management_statistics",
            model={"id": "model", "version": 1},
            management_unit_id=unit,
            source_pointer="/outputs/node.statistics/units/" + unit,
            values={"area": 12},
            units={"area": "m**2"},
        )
        for unit in ["U1", "U2"]
    ]
    view = bind_result_objects(objects, [entity])
    assert view.entity_binding[0].result_object_id == objects[0].id
    assert view.entity_binding[0].geographic_entity_id == entity.id
    assert view.entity_binding[0].geographic_entity_version == 1
    assert view.entity_binding[0].management_unit_id == "U1"
    assert view.unbound_objects == (objects[1].id,)
    assert view.binding_status == "PARTIAL"
    duplicate = entity.model_copy(update={"id": "other-entity"})
    with pytest.raises(ConstraintError, match="ambiguous"):
        bind_result_objects(objects, [entity, duplicate])


def test_domain_result_mapping_preserves_real_values_units_and_order_independent_identity():
    registered = model(
        outputs=[
            variable("result", data_type="json", standard_name="coastal_management_statistics")
        ]
    )
    outputs = {
        "screen-node.result": {
            "units": {
                "U1": {"inundated_area_m2": 20, "estimated_population": 2, "unknown_area_m2": 5}
            }
        }
    }
    objects = management_objects("job", workflow(), [registered], outputs)
    assert len(objects) == 1
    assert objects[0].values == outputs["screen-node.result"]["units"]["U1"]
    assert objects[0].units == {
        "inundated_area_m2": "m**2",
        "estimated_population": "person",
        "unknown_area_m2": "m**2",
    }
    changed = deepcopy(outputs)
    changed["screen-node.result"]["units"]["U1"]["estimated_population"] = -1
    with pytest.raises(ConstraintError):
        management_objects("job", workflow(), [registered], changed)
    assert objects[0].id != "U1"
    assert objects[0].id == result_object_id("job", "screen-node", "result", "U1")
    assert objects[0].id != result_object_id("another-job", "screen-node", "result", "U1")


def test_assessment_binding_keeps_units_aligned_with_periods_and_trends():
    registered = model(
        outputs=[variable("result", data_type="json", standard_name="assessment_scores")]
    )
    outputs = {
        "screen-node.result": {
            "unit_ids": ["U2", "U1"],
            "years": [2020, 2022],
            "values": [[0.2, 0.4], [0.6, 0.8]],
            "classes": [[0, 1], [2, 3]],
            "method": "composite",
            "weights": [1],
            "unit": "1",
        }
    }
    objects = management_objects("job", workflow(), [registered], outputs)
    assert objects[0].management_unit_id == "U2"
    assert objects[0].values["scores"] == [0.2, 0.6]
    assert objects[0].values["years"] == [2020, 2022]
    assert objects[1].values["scores"] == [0.4, 0.8]
    assert objects[0].units["scores"] == "1"


def test_pointer_escaping_and_non_management_outputs_never_invent_entity_matches():
    registered = model(outputs=[variable("result", data_type="array")])
    objects = management_objects("job", workflow(), [registered], {"screen-node.result": [1, 2]})
    assert len(objects) == 1
    assert objects[0].management_unit_id is None
    assert objects[0].values == {}
    assert bind_result_objects(objects, []).binding_status == "NOT_APPLICABLE"
    assert result_object_id("a.b", "c", "d", "e") != result_object_id("a", "b.c", "d", "e")


def test_full_coastal_metrics_and_pointer_escape_are_preserved():
    registered = model(
        outputs=[
            variable("result", data_type="json", standard_name="coastal_management_statistics")
        ]
    )
    metrics = {
        "inundated_area_m2": 20,
        "estimated_population": 2,
        "unknown_area_m2": 5,
        "study_area_m2": 100,
        "population_in_unknown_dem_area": 0.5,
        "fraction": 0.2,
    }
    objects = management_objects(
        "job", workflow(), [registered], {"screen-node.result": {"units": {"U/~1": metrics}}}
    )
    assert objects[0].values == metrics
    assert objects[0].source_pointer.endswith("/U~1~01")
    assert objects[0].units["fraction"] == "1"
    assert objects[0].units["population_in_unknown_dem_area"] == "person"


def test_temporal_change_mapping_rejects_misalignment_and_retains_explicit_units():
    registered = model(
        outputs=[variable("result", data_type="json", standard_name="temporal_assessment_change")]
    )
    value = {
        "unit_ids": ["U2", "U1"],
        "years": [2020, 2022],
        "change": [0.2, -0.1],
        "trend": [0.1, -0.05],
        "ranks": [[1, 2], [2, 1]],
    }
    objects = management_objects("job", workflow(), [registered], {"screen-node.result": value})
    assert objects[1].values == {
        "years": [2020, 2022],
        "change": -0.1,
        "trend": -0.05,
        "ranks": [2, 1],
    }
    assert objects[1].units["trend"] == "1/year"
    for invalid in [
        {"change": [0.2]},
        {"unit_ids": ["U1", "U1"]},
        {"years": [2022, 2020]},
        {"ranks": [[1], [2]]},
    ]:
        with pytest.raises(ConstraintError):
            management_objects(
                "job", workflow(), [registered], {"screen-node.result": {**value, **invalid}}
            )
