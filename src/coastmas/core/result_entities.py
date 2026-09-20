"""Result identities and exact, versioned entity binding without domain inference."""

import hashlib
import json
from collections.abc import Sequence
from typing import Literal

from pydantic import Field, JsonValue

from coastmas.core.contracts import Contract, EntityBinding, Name, VersionReference
from coastmas.core.errors import ConstraintError
from coastmas.core.geography import GeographicEntity


class ResultObject(Contract):
    id: Name
    node_id: Name
    variable: Name
    standard_name: Name
    model: VersionReference
    management_unit_id: Name | None
    source_pointer: str = Field(pattern=r"^/outputs/")
    values: dict[str, JsonValue] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)


class ResultView(Contract):
    objects: tuple[ResultObject, ...]
    entity_binding: tuple[EntityBinding, ...]
    unbound_objects: tuple[str, ...]
    binding_status: Literal["BOUND", "PARTIAL", "UNBOUND", "NOT_APPLICABLE"]


def result_object_id(job_id: str, node_id: str, variable: str, unit_id: str | None) -> str:
    identity = json.dumps([job_id, node_id, variable, unit_id], ensure_ascii=False).encode()
    return "result-object:" + hashlib.sha256(identity).hexdigest()


def bind_result_objects(
    objects: Sequence[ResultObject], entities: Sequence[GeographicEntity]
) -> ResultView:
    by_unit: dict[str, GeographicEntity] = {}
    for entity in entities:
        unit = entity.management_unit_id
        if unit is not None:
            if unit in by_unit:
                raise ConstraintError(f"ambiguous selected entities for management unit {unit}")
            by_unit[unit] = entity
    identifiers = [item.id for item in objects]
    if len(set(identifiers)) != len(identifiers):
        raise ConstraintError("duplicate result object identity")
    reserved = {entity.id for entity in entities} | set(by_unit)
    reserved.update(item.management_unit_id for item in objects if item.management_unit_id)
    if reserved.intersection(identifiers):
        raise ConstraintError("result, entity and management unit identities must be distinct")
    bindings: list[EntityBinding] = []
    unbound: list[str] = []
    for item in objects:
        if item.management_unit_id is None:
            continue
        matched_entity = by_unit.get(item.management_unit_id)
        if matched_entity is None:
            unbound.append(item.id)
        else:
            bindings.append(
                EntityBinding(
                    result_object_id=item.id,
                    geographic_entity_id=matched_entity.id,
                    geographic_entity_version=matched_entity.version,
                    management_unit_id=item.management_unit_id,
                )
            )
    status: Literal["BOUND", "PARTIAL", "UNBOUND", "NOT_APPLICABLE"]
    if bindings:
        status = "PARTIAL" if unbound else "BOUND"
    else:
        status = "UNBOUND" if unbound else "NOT_APPLICABLE"
    return ResultView(
        objects=tuple(objects),
        entity_binding=tuple(bindings),
        unbound_objects=tuple(unbound),
        binding_status=status,
    )
