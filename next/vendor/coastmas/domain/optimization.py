"""Binary spatial allocation demonstration with verified solver feasibility."""

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

# SciPy optimize does not ship PEP 561 typing for this API. All outputs are validated below.
from scipy.optimize import Bounds, LinearConstraint, milp  # type: ignore[import-untyped]

from coastmas.core.errors import ConstraintError
from coastmas.core.optimization import CandidateUnit


@dataclass(frozen=True)
class OptimizationResult:
    status: Literal["OPTIMAL", "INCUMBENT", "INFEASIBLE", "TIME_LIMIT", "FAILED"]
    selected: tuple[str, ...]
    benefit: float | None
    cost: float | None
    area: float | None
    ecological_cost: float | None
    risk: float | None
    constraints_satisfied: bool
    solver_message: str
    relative_gap: float | None


def optimize_units(
    units: list[CandidateUnit],
    *,
    budget: float,
    minimum_area: float,
    maximum_ecological_cost: float,
    maximum_risk: float,
    time_limit: float,
) -> OptimizationResult:
    limits = (budget, minimum_area, maximum_ecological_cost, maximum_risk, time_limit)
    if (
        not units
        or not all(math.isfinite(item) and item >= 0 for item in limits)
        or time_limit == 0
    ):
        raise ConstraintError(
            "optimization requires finite nonnegative limits and positive timeout"
        )
    if len({unit.id for unit in units}) != len(units):
        raise ConstraintError("candidate unit identifiers must be unique")
    benefits = np.asarray([unit.benefit for unit in units], dtype=np.float64)
    matrix = np.asarray(
        [
            [unit.cost for unit in units],
            [unit.area for unit in units],
            [unit.ecological_cost for unit in units],
            [unit.risk for unit in units],
        ]
    )
    lower = np.asarray([0, minimum_area, 0, 0], dtype=np.float64)
    upper = np.asarray([budget, np.inf, maximum_ecological_cost, maximum_risk])
    allowed = np.asarray([int(unit.allowed) for unit in units])
    solution = milp(
        -benefits,
        integrality=np.ones(len(units)),
        bounds=Bounds(0, allowed),
        constraints=LinearConstraint(matrix, lower, upper),
        options={"time_limit": time_limit, "mip_rel_gap": 0.0},
    )
    status = int(solution.status)
    message = str(solution.message)
    if status == 2:
        return OptimizationResult(
            "INFEASIBLE", (), None, None, None, None, None, False, message, None
        )
    if solution.x is None:
        return OptimizationResult(
            "TIME_LIMIT" if status == 1 else "FAILED",
            (),
            None,
            None,
            None,
            None,
            None,
            False,
            message,
            None,
        )
    raw = np.asarray(solution.x, dtype=np.float64)
    selected = np.rint(raw)
    tolerance = 1e-7
    if (
        not np.all(np.isfinite(raw))
        or not np.allclose(raw, selected, atol=tolerance, rtol=0)
        or np.any(selected < 0)
        or np.any(selected > allowed)
    ):
        raise ConstraintError("solver returned invalid binary allocation")
    achieved = matrix @ selected
    if np.any(achieved < lower - tolerance) or np.any(achieved > upper + tolerance):
        raise ConstraintError("solver allocation violates hard constraints")
    gap = getattr(solution, "mip_gap", None)
    relative_gap = float(gap) if gap is not None and math.isfinite(float(gap)) else None
    result_status: Literal["OPTIMAL", "INCUMBENT"] = "OPTIMAL" if status == 0 else "INCUMBENT"
    return OptimizationResult(
        result_status,
        tuple(unit.id for unit, chosen in zip(units, selected, strict=True) if chosen),
        float(benefits @ selected),
        float(achieved[0]),
        float(achieved[1]),
        float(achieved[2]),
        float(achieved[3]),
        True,
        message,
        relative_gap,
    )
