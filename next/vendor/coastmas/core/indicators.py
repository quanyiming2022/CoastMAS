"""Versioned indicator definitions with explicit reference ranges and formula inputs."""

from typing import Annotated, Literal, Self

import pint
from pydantic import Field, FiniteFloat, model_validator

from coastmas.core.contracts import UNITS, Contract, Name, Version, VersionReference

FormulaAlias = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")]
WeightMethod = Literal["equal", "manual", "entropy"]
DEMO_CATEGORIES = ("资源利用", "空间潜力", "脆弱性", "稳定性", "发展韧性")


class FixedNormalization(Contract):
    method: Literal["fixed_minmax"] = "fixed_minmax"
    lower: FiniteFloat
    upper: FiniteFloat

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.upper <= self.lower:
            raise ValueError("normalization reference upper must exceed lower")
        return self


class IndicatorDefinition(Contract):
    indicator_id: Name
    name: Name
    category: Name
    unit: Name
    direction: Literal["positive", "negative"]
    source: Annotated[dict[FormulaAlias, Name], Field(min_length=1, max_length=64)]
    formula: Annotated[str, Field(min_length=1, max_length=1000)]
    normalization: FixedNormalization
    weight_method: WeightMethod
    weight: Annotated[FiniteFloat, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def scientific_definition(self) -> Self:
        try:
            UNITS.Unit(self.unit)
        except (pint.UndefinedUnitError, ValueError, TypeError) as exc:
            raise ValueError("unknown indicator unit") from exc
        if any(alias in {"where", "sqrt", "log", "abs"} for alias in self.source):
            raise ValueError("formula input alias conflicts with a function")
        if self.weight_method == "manual" and self.weight is None:
            raise ValueError("manual weighting requires an explicit weight")
        if self.weight_method != "manual" and self.weight is not None:
            raise ValueError("computed weights must remain unknown until calculation")
        return self


class IndicatorFrameworkSpec(Contract):
    id: Name
    name: Name
    version: Version
    description: Annotated[str, Field(min_length=1, max_length=10000)]
    demo: bool = False
    spatial_support: Literal["management_unit", "administrative_unit", "custom_polygon", "grid"]
    indicators: Annotated[tuple[IndicatorDefinition, ...], Field(min_length=1, max_length=100)]
    class_breaks: tuple[FiniteFloat, ...] = (0.25, 0.5, 0.75)

    @model_validator(mode="after")
    def unambiguous(self) -> Self:
        identifiers = [item.indicator_id for item in self.indicators]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("indicator ids must be unique")
        methods = {item.weight_method for item in self.indicators}
        if len(methods) != 1:
            raise ValueError("one shared weight method is required across indicators and periods")
        if methods == {"manual"} and sum(item.weight or 0 for item in self.indicators) <= 0:
            raise ValueError("manual weights must have a positive total")
        if any(not 0 < value < 1 for value in self.class_breaks) or any(
            right <= left
            for left, right in zip(self.class_breaks, self.class_breaks[1:], strict=False)
        ):
            raise ValueError("class breaks must strictly increase inside (0,1)")
        return self


class AssessmentSpec(Contract):
    """A frozen evaluation configuration; run results are read from actual job manifests."""

    id: Name
    name: Name
    version: Version
    framework: VersionReference
    data: VersionReference
    scene: VersionReference
    workflow: VersionReference
