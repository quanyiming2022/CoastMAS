"""Explicit additive optimization contracts; an infeasible solve is not an allocation."""

from typing import Annotated, Literal, Self

import pint
from pydantic import Field, StrictBool, model_validator

from coastmas.core.contracts import UNITS, Contract, Name, VersionReference

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Nonnegative = Annotated[Number, Field(ge=0)]


class CandidateUnit(Contract):
    id: Name
    benefit: Number
    cost: Nonnegative
    area: Annotated[Number, Field(gt=0)]
    ecological_cost: Nonnegative
    risk: Nonnegative
    allowed: StrictBool = True


class OptimizationFrame(Contract):
    units: Annotated[tuple[CandidateUnit, ...], Field(min_length=1, max_length=5000)]
    area_unit: Name
    benefit_unit: Name
    cost_unit: Name
    ecological_cost_unit: Name
    risk_unit: Name
    budget: Nonnegative
    minimum_area: Nonnegative
    maximum_ecological_cost: Nonnegative
    maximum_risk: Nonnegative
    protected_unit_ids: Annotated[tuple[Name, ...], Field(max_length=5000)] = ()
    risk_aggregation: Literal["additive_index"]
    additivity_basis: Annotated[str, Field(min_length=1, max_length=10000, pattern=r".*\S.*")]
    data_label: Name

    @model_validator(mode="after")
    def scientifically_explicit(self) -> Self:
        identifiers = {unit.id for unit in self.units}
        if len(identifiers) != len(self.units):
            raise ValueError("candidate identifiers must be unique")
        if len(set(self.protected_unit_ids)) != len(self.protected_unit_ids):
            raise ValueError("protected identifiers must be unique")
        if not set(self.protected_unit_ids).issubset(identifiers):
            raise ValueError("protected identifiers must be present in candidate units")
        try:
            for value in (
                self.area_unit,
                self.benefit_unit,
                self.cost_unit,
                self.ecological_cost_unit,
                self.risk_unit,
            ):
                UNITS.Unit(value)
            if UNITS.get_dimensionality(self.area_unit) != UNITS.get_dimensionality("m^2"):
                raise ValueError("area unit must have area dimensionality")
        except (pint.UndefinedUnitError, TypeError) as exc:
            raise ValueError("optimization unit is unknown") from exc
        return self


class OptimizationTotals(Contract):
    benefit: Number
    cost: Nonnegative
    area: Nonnegative
    ecological_cost: Nonnegative
    risk: Nonnegative


class Allocation(CandidateUnit):
    selected: bool | None


class ConstraintCheck(Contract):
    bound: Number
    actual: Number | None
    satisfied: bool | None
    relation: Literal["le", "ge"]
    unit: Name


class OptimizationOutcome(Contract):
    status: Literal["OPTIMAL", "INCUMBENT", "INFEASIBLE", "TIME_LIMIT", "FAILED"]
    selected: tuple[Name, ...]
    allocations: tuple[Allocation, ...]
    totals: OptimizationTotals | None
    checks: dict[str, ConstraintCheck]
    constraints_satisfied: bool
    policy_decision: Literal[False] = False
    area_unit: Literal["m^2"] = "m^2"
    benefit_unit: Name
    cost_unit: Name
    ecological_cost_unit: Name
    risk_unit: Name
    risk_aggregation: Literal["additive_index"] = "additive_index"
    additivity_basis: str
    data_label: Name
    solver_message: str
    relative_gap: Nonnegative | None

    @model_validator(mode="after")
    def truthful_allocation(self) -> Self:
        feasible = self.status in {"OPTIMAL", "INCUMBENT"}
        if self.constraints_satisfied != feasible or (self.totals is not None) != feasible:
            raise ValueError("allocation totals and feasibility must match solver status")
        if not feasible and (
            self.selected or any(row.selected is not None for row in self.allocations)
        ):
            raise ValueError("no allocation may be invented without a feasible solution")
        if feasible:
            chosen = tuple(row.id for row in self.allocations if row.selected)
            if chosen != self.selected or any(
                row.selected and not row.allowed for row in self.allocations
            ):
                raise ValueError(
                    "selection differs from explicit unit allocation or hard protection"
                )
            if any(row.selected is None for row in self.allocations) or not all(
                check.satisfied is True for check in self.checks.values()
            ):
                raise ValueError("feasible solution requires complete verified constraints")
        return self


class OptimizationSpec(Contract):
    id: Name
    name: Name
    version: Annotated[int, Field(ge=1)]
    source_scene: VersionReference
    scene: VersionReference
    data: VersionReference
    workflow: VersionReference
    request_checksum: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
