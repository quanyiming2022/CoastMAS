"""Unit-aware bounded MILP component, suitable for the isolated trusted worker."""

import math

from pydantic import JsonValue

from coastmas.core.binding import convert_units
from coastmas.core.contracts import SceneSpec
from coastmas.core.errors import ConstraintError
from coastmas.core.optimization import (
    Allocation,
    CandidateUnit,
    ConstraintCheck,
    OptimizationFrame,
    OptimizationOutcome,
    OptimizationTotals,
)
from coastmas.domain.optimization import optimize_units


def optimize_component(
    context: dict[str, JsonValue], inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    frame = OptimizationFrame.model_validate(inputs.get("candidates"))
    scene = SceneSpec.model_validate(context.get("scene"))
    timeout = parameters.get("time_limit")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or not 0 < timeout <= 120
    ):
        raise ConstraintError(
            "optimization time_limit must be explicit and within (0, 120] seconds"
        )
    protected = scene.scenario_conditions.get("optimization_protected_units", [])
    if not isinstance(protected, list) or any(not isinstance(value, str) for value in protected):
        raise ConstraintError("scene protected units must be an explicit list of identifiers")
    protected_ids = {str(value) for value in protected} | set(frame.protected_unit_ids)
    if not protected_ids.issubset({unit.id for unit in frame.units}):
        raise ConstraintError("scene protected unit is absent from candidate units")
    areas = convert_units(
        [unit.area for unit in frame.units] + [frame.minimum_area], frame.area_unit, "m^2"
    )
    if not all(math.isfinite(value) for value in areas):
        raise ConstraintError("area conversion is not finite")
    units = [
        CandidateUnit.model_validate(
            {
                **unit.model_dump(),
                "area": float(areas[index]),
                "allowed": unit.allowed and unit.id not in protected_ids,
            }
        )
        for index, unit in enumerate(frame.units)
    ]
    result = optimize_units(
        units,
        budget=frame.budget,
        minimum_area=float(areas[-1]),
        maximum_ecological_cost=frame.maximum_ecological_cost,
        maximum_risk=frame.maximum_risk,
        time_limit=float(timeout),
    )
    feasible = result.constraints_satisfied
    selected = set(result.selected)
    totals = (
        OptimizationTotals.model_validate(
            {
                "benefit": result.benefit,
                "cost": result.cost,
                "area": result.area,
                "ecological_cost": result.ecological_cost,
                "risk": result.risk,
            }
        )
        if feasible
        else None
    )
    checks = {
        "budget": ConstraintCheck(
            bound=frame.budget,
            actual=result.cost,
            satisfied=(result.cost <= frame.budget + 1e-7) if result.cost is not None else None,
            relation="le",
            unit=frame.cost_unit,
        ),
        "minimum_area": ConstraintCheck(
            bound=float(areas[-1]),
            actual=result.area,
            satisfied=(result.area >= float(areas[-1]) - 1e-7) if result.area is not None else None,
            relation="ge",
            unit="m^2",
        ),
        "ecological_cost": ConstraintCheck(
            bound=frame.maximum_ecological_cost,
            actual=result.ecological_cost,
            satisfied=(result.ecological_cost <= frame.maximum_ecological_cost + 1e-7)
            if result.ecological_cost is not None
            else None,
            relation="le",
            unit=frame.ecological_cost_unit,
        ),
        "risk": ConstraintCheck(
            bound=frame.maximum_risk,
            actual=result.risk,
            satisfied=(result.risk <= frame.maximum_risk + 1e-7)
            if result.risk is not None
            else None,
            relation="le",
            unit=frame.risk_unit,
        ),
        "protected_selected": ConstraintCheck(
            bound=0,
            actual=float(sum(unit.id in selected for unit in units if not unit.allowed))
            if feasible
            else None,
            satisfied=not any(unit.id in selected for unit in units if not unit.allowed)
            if feasible
            else None,
            relation="le",
            unit="1",
        ),
    }
    output = OptimizationOutcome(
        status=result.status,
        selected=result.selected,
        allocations=tuple(
            Allocation(**unit.model_dump(), selected=unit.id in selected if feasible else None)
            for unit in units
        ),
        totals=totals,
        checks=checks,
        constraints_satisfied=feasible,
        benefit_unit=frame.benefit_unit,
        cost_unit=frame.cost_unit,
        ecological_cost_unit=frame.ecological_cost_unit,
        risk_unit=frame.risk_unit,
        additivity_basis=frame.additivity_basis,
        data_label=frame.data_label,
        solver_message=result.solver_message,
        relative_gap=result.relative_gap,
    )
    return {"allocation": output.model_dump(mode="json")}
