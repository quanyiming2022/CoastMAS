"""Extract management views from validated domain outputs, preserving source pointers."""

from collections.abc import Sequence
from math import isfinite

from pydantic import JsonValue, ValidationError

from coastmas.core.contracts import ModelSpec, VersionReference, WorkflowSpec
from coastmas.core.errors import ConstraintError
from coastmas.core.result_entities import ResultObject, result_object_id
from coastmas.domain.indicator_frames import ScoreFrame, TemporalChange


def pointer_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def management_objects(
    job_id: str, workflow: WorkflowSpec, models: Sequence[ModelSpec], outputs: dict[str, JsonValue]
) -> tuple[ResultObject, ...]:
    registered = {(model.id, model.version): model for model in models}
    nodes = {node.id: node for node in workflow.nodes}
    result: list[ResultObject] = []
    seen: set[str] = set()
    for selected in workflow.output_definition:
        key = f"{selected.node_id}.{selected.variable}"
        if key in seen:
            raise ConstraintError("ambiguous flattened output key")
        seen.add(key)
        node = nodes[selected.node_id]
        spec = registered.get((node.model_id, node.model_version))
        variable = (
            next((v for v in spec.outputs if v.name == selected.variable), None) if spec else None
        )
        if spec is None or variable is None or key not in outputs:
            raise ConstraintError("result output lacks its pinned model declaration or value")
        source = "/outputs/" + pointer_segment(key)
        value = outputs[key]
        rows: list[tuple[str | None, str, dict[str, JsonValue], dict[str, str]]] = []
        if variable.standard_name == "coastal_management_statistics":
            units = value.get("units") if isinstance(value, dict) else None
            if not isinstance(units, dict):
                raise ConstraintError("management statistics require explicit units")
            metric_units = {
                "inundated_area_m2": "m**2",
                "estimated_population": "person",
                "unknown_area_m2": "m**2",
                "study_area_m2": "m**2",
                "population_in_unknown_dem_area": "person",
                "fraction": "1",
            }
            for unit, metrics in units.items():
                if (
                    not isinstance(metrics, dict)
                    or not {
                        "inundated_area_m2",
                        "estimated_population",
                        "unknown_area_m2",
                    }.issubset(metrics)
                    or not set(metrics).issubset(metric_units)
                ):
                    raise ConstraintError("management statistics metrics are incomplete or unknown")
                if any(
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not isfinite(v)
                    or v < 0
                    for v in metrics.values()
                ):
                    raise ConstraintError("management statistics must be finite and nonnegative")
                rows.append(
                    (
                        unit,
                        source + "/units/" + pointer_segment(unit),
                        metrics,
                        {name: metric_units[name] for name in metrics},
                    )
                )
        elif variable.standard_name == "assessment_scores":
            try:
                frame = ScoreFrame.model_validate(value)
            except ValidationError as exc:
                raise ConstraintError("invalid assessment score output") from exc
            for index, unit in enumerate(frame.unit_ids):
                rows.append(
                    (
                        unit,
                        source,
                        {
                            "scores": [row[index] for row in frame.values],
                            "classes": [row[index] for row in frame.classes],
                            "years": list(frame.years) if frame.years is not None else None,
                        },
                        {"scores": "1", "classes": "1", "years": "year"},
                    )
                )
        elif variable.standard_name == "temporal_assessment_change":
            try:
                changes = TemporalChange.model_validate(value)
            except ValidationError as exc:
                raise ConstraintError("invalid temporal change output") from exc
            for index, unit in enumerate(changes.unit_ids):
                rows.append(
                    (
                        unit,
                        source,
                        {
                            "years": list(changes.years),
                            "change": changes.change[index],
                            "trend": changes.trend[index],
                            "ranks": [row[index] for row in changes.ranks],
                        },
                        {
                            "years": "year",
                            "change": changes.change_unit,
                            "trend": changes.trend_unit,
                            "ranks": "1",
                        },
                    )
                )
        else:
            rows.append((None, source, {}, {}))
        for result_unit, pointer, metrics, metric_units in rows:
            result.append(
                ResultObject(
                    id=result_object_id(job_id, node.id, variable.name, result_unit),
                    node_id=node.id,
                    variable=variable.name,
                    standard_name=variable.standard_name,
                    model=VersionReference(id=spec.id, version=spec.version),
                    management_unit_id=result_unit,
                    source_pointer=pointer,
                    values=metrics,
                    units=metric_units,
                )
            )
    return tuple(result)
