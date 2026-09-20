"""Display geometry from pinned result snapshots, never from current catalogue versions."""

from collections.abc import Sequence

from pydantic import JsonValue

from coastmas.core.errors import ConstraintError
from coastmas.core.geography import GeographicEntity
from coastmas.core.result_entities import ResultView
from coastmas.core.scene_workspace import geographic_geometry


def result_entity_features(
    view: ResultView, entities: Sequence[GeographicEntity]
) -> dict[str, JsonValue]:
    snapshots = {(entity.id, entity.version): entity for entity in entities}
    if len(snapshots) != len(entities):
        raise ConstraintError("duplicate entity snapshot")
    seen: set[tuple[str, int]] = set()
    features: list[JsonValue] = []
    for binding in view.entity_binding:
        key = (binding.geographic_entity_id, binding.geographic_entity_version)
        entity = snapshots.get(key)
        if entity is None or entity.management_unit_id != binding.management_unit_id:
            raise ConstraintError("result binding does not match its entity snapshot")
        if key in seen:
            continue
        seen.add(key)
        features.append(
            {
                "type": "Feature",
                "id": entity.id,
                "geometry": geographic_geometry(
                    entity.geometry.model_dump(mode="json"), entity.crs
                ),
                "properties": {
                    "entity_id": entity.id,
                    "entity_version": entity.version,
                    "management_unit_id": entity.management_unit_id,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}
