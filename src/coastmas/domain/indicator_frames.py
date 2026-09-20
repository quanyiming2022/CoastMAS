"""Entity-aligned assessment frames with per-column units and fixed references.

A frame is a structured container; its numeric columns are not falsely assigned
one shared physical unit. Normalization removes units only after compatible
reference bounds have been converted. Temporal weights are shared across periods.
"""

from typing import Annotated, Literal, Self

import numpy as np
from pydantic import Field, FiniteFloat, model_validator

from coastmas.core.binding import convert_units
from coastmas.core.contracts import Contract, Name
from coastmas.core.errors import ConstraintError
from coastmas.domain.assessment import (
    composite,
    entropy_weights,
    normalize,
    normalized_weights,
    topsis,
)

Row = tuple[FiniteFloat, ...]
Matrix = tuple[Row, ...]
Cube = tuple[Matrix, ...]


class IndicatorColumn(Contract):
    name: Name
    unit: Name
    reference_unit: Name
    lower: FiniteFloat
    upper: FiniteFloat
    positive: bool
    weight: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 1


class IndicatorFrame(Contract):
    unit_ids: Annotated[tuple[Name, ...], Field(min_length=1)]
    columns: Annotated[tuple[IndicatorColumn, ...], Field(min_length=1)]
    values: Matrix | Cube
    years: tuple[FiniteFloat, ...] | None = None
    class_breaks: tuple[FiniteFloat, ...] = (0.25, 0.5, 0.75)

    @model_validator(mode="after")
    def aligned(self) -> Self:
        if len(set(self.unit_ids)) != len(self.unit_ids):
            raise ValueError("geographic unit identifiers must be unique")
        names = [column.name for column in self.columns]
        if len(set(names)) != len(names):
            raise ValueError("indicator names must be unique")
        values = np.asarray(self.values, dtype=float)
        expected_rank = 2 if self.years is None else 3
        if values.ndim != expected_rank or values.shape[-2:] != (
            len(self.unit_ids),
            len(self.columns),
        ):
            raise ValueError("indicator dimensions must align with entity ids, columns and periods")
        if self.years is not None and (
            len(self.years) != values.shape[0] or not self.years or np.any(np.diff(self.years) <= 0)
        ):
            raise ValueError("time coordinates must match strictly increasing periods")
        if any(not 0 < value < 1 for value in self.class_breaks) or any(
            after <= before
            for before, after in zip(self.class_breaks, self.class_breaks[1:], strict=False)
        ):
            raise ValueError("class breaks must strictly increase inside (0,1)")
        return self


class NormalizedFrame(Contract):
    unit_ids: tuple[Name, ...]
    columns: tuple[Name, ...]
    values: Cube
    years: tuple[FiniteFloat, ...] | None
    manual_weights: Row
    class_breaks: Row

    @model_validator(mode="after")
    def aligned(self) -> Self:
        array = np.asarray(self.values, dtype=float)
        if (
            array.ndim != 3
            or array.size == 0
            or array.shape[1:] != (len(self.unit_ids), len(self.columns))
            or len(set(self.unit_ids)) != len(self.unit_ids)
            or len(set(self.columns)) != len(self.columns)
            or len(self.manual_weights) != len(self.columns)
            or np.any(array < 0)
            or np.any(array > 1)
        ):
            raise ValueError("normalized frame has invalid alignment or values")
        if self.years is None and array.shape[0] != 1:
            raise ValueError("multiple periods require time coordinates")
        if self.years is not None and (
            len(self.years) != array.shape[0] or np.any(np.diff(self.years) <= 0)
        ):
            raise ValueError("normalized periods and times differ")
        if any(not 0 < value < 1 for value in self.class_breaks) or any(
            after <= before
            for before, after in zip(self.class_breaks, self.class_breaks[1:], strict=False)
        ):
            raise ValueError("invalid classification thresholds")
        return self


class ScoreFrame(Contract):
    unit_ids: tuple[Name, ...]
    years: tuple[FiniteFloat, ...] | None
    values: Matrix
    classes: tuple[tuple[int, ...], ...]
    method: Literal["composite", "topsis"]
    weights: Row
    unit: Literal["1"] = "1"

    @model_validator(mode="after")
    def aligned(self) -> Self:
        values = np.asarray(self.values, dtype=float)
        if (
            values.ndim != 2
            or values.size == 0
            or values.shape[1] != len(self.unit_ids)
            or len(set(self.unit_ids)) != len(self.unit_ids)
            or np.asarray(self.classes).shape != values.shape
            or np.any(values < 0)
            or np.any(values > 1)
        ):
            raise ValueError("score frame alignment or range is invalid")
        if self.years is None and values.shape[0] != 1:
            raise ValueError("multiple score periods require time coordinates")
        if self.years is not None and (
            len(self.years) != values.shape[0] or np.any(np.diff(self.years) <= 0)
        ):
            raise ValueError("score time coordinates must match and increase")
        return self


class TemporalChange(Contract):
    unit_ids: tuple[Name, ...]
    years: tuple[FiniteFloat, ...]
    change: Row
    trend: Row
    ranks: tuple[tuple[int, ...], ...]
    change_unit: Literal["1"] = "1"
    trend_unit: Literal["1/year"] = "1/year"

    @model_validator(mode="after")
    def aligned(self) -> Self:
        count = len(self.unit_ids)
        if (
            count == 0
            or len(set(self.unit_ids)) != count
            or len(self.change) != count
            or len(self.trend) != count
            or len(self.years) < 2
            or any(right <= left for left, right in zip(self.years, self.years[1:], strict=False))
            or len(self.ranks) != len(self.years)
            or any(
                len(row) != count or any(rank < 1 or rank > count for rank in row)
                for row in self.ranks
            )
        ):
            raise ValueError("temporal change units, periods and ranks must align")
        return self


def normalize_frame(frame: IndicatorFrame) -> NormalizedFrame:
    values = np.asarray(frame.values, dtype=float)
    periods = values[None, ...] if values.ndim == 2 else values
    bounds = [
        convert_units([column.lower, column.upper], column.reference_unit, column.unit)
        for column in frame.columns
    ]
    lower, upper = [pair[0] for pair in bounds], [pair[1] for pair in bounds]
    positive = [column.positive for column in frame.columns]
    normalized = [normalize(period, lower, upper, positive).tolist() for period in periods]
    return NormalizedFrame.model_validate(
        {
            "unit_ids": frame.unit_ids,
            "columns": [column.name for column in frame.columns],
            "values": normalized,
            "years": frame.years,
            "manual_weights": [column.weight for column in frame.columns],
            "class_breaks": frame.class_breaks,
        }
    )


def weight_frame(frame: NormalizedFrame, *, method: Literal["equal", "manual", "entropy"]) -> Row:
    if method == "equal":
        weight = normalized_weights(np.ones(len(frame.columns)), len(frame.columns))
    elif method == "manual":
        weight = normalized_weights(frame.manual_weights, len(frame.columns))
    elif method == "entropy":
        values = np.asarray(frame.values, dtype=float)
        weight = entropy_weights(values.reshape(-1, values.shape[-1]))
    else:
        raise ConstraintError("unknown weight method")
    return tuple(float(value) for value in weight)


def aggregate_frame(
    frame: NormalizedFrame, weights: Row, *, method: Literal["composite", "topsis"] = "composite"
) -> ScoreFrame:
    weight = normalized_weights(weights, len(frame.columns))
    periods = np.asarray(frame.values, dtype=float)
    if method == "composite":
        scores = np.stack([composite(period, weight) for period in periods])
    elif method == "topsis":
        if len(periods) != 1:
            raise ConstraintError(
                "period-specific TOPSIS ideals would break temporal comparability"
            )
        scores = np.stack(
            [topsis(period, weight, [True] * len(frame.columns)) for period in periods]
        )
    else:
        raise ConstraintError("unknown aggregation method")
    # Intervals are [lower, upper); values on a break enter the next class.
    classes = np.searchsorted(frame.class_breaks, scores, side="right") + 1
    return ScoreFrame.model_validate(
        {
            "unit_ids": frame.unit_ids,
            "years": frame.years,
            "values": scores.tolist(),
            "classes": classes.tolist(),
            "method": method,
            "weights": weight.tolist(),
        }
    )


def temporal_change(scores: ScoreFrame) -> TemporalChange:
    if scores.years is None or len(scores.years) < 2:
        raise ConstraintError("change and trend require at least two declared periods")
    times = np.asarray(scores.years, dtype=float)
    values = np.asarray(scores.values, dtype=float)
    centered = times - times.mean()
    denominator = float(centered @ centered)
    if denominator <= 0:
        raise ConstraintError("time coordinates cannot define a trend")
    trend = centered @ values / denominator
    ranks = [[1 + int(np.count_nonzero(row > value)) for value in row] for row in values]
    return TemporalChange.model_validate(
        {
            "unit_ids": scores.unit_ids,
            "years": scores.years,
            "change": (values[-1] - values[0]).tolist(),
            "trend": trend.tolist(),
            "ranks": ranks,
        }
    )
