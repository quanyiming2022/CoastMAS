"""Explicit point/interval observations; elapsed UTC support, never guessed cadence."""

import bisect
import math
from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from coastmas.core.binding import convert_units
from coastmas.core.contracts import UNITS, Contract, Name
from coastmas.core.errors import CoastMASError

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Method = Literal["nearest", "mean", "sum", "min", "max", "interpolation"]


class TemporalObservation(Contract):
    start: AwareDatetime
    end: AwareDatetime
    value: Number | None

    @field_validator("start", "end")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError("observation end precedes start")
        return self


class TemporalRequest(Contract):
    variable: Name
    unit: Name
    output_unit: Name
    aggregation_type: Literal["intensive", "extensive", "categorical", "instantaneous"]
    support: Literal["point", "interval"]
    observations: Annotated[tuple[TemporalObservation, ...], Field(min_length=1, max_length=10000)]
    method: Method
    target_time: AwareDatetime | None = None
    window_start: AwareDatetime | None = None
    window_end: AwareDatetime | None = None
    nodata_policy: Literal["propagate", "reject"] = "propagate"

    @field_validator("target_time", "window_start", "window_end")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode="after")
    def scientific_contract(self) -> Self:
        allowed = {
            "intensive": {"nearest", "interpolation", "mean", "min", "max"},
            "instantaneous": {"nearest", "interpolation", "min", "max"},
            "extensive": {"sum"},
            "categorical": {"nearest"},
        }
        if self.method not in allowed[self.aggregation_type]:
            raise ValueError("method conflicts with declared aggregation type")
        if self.aggregation_type in {"categorical", "instantaneous"} and self.support != "point":
            raise ValueError("categorical or instantaneous observations require point support")
        if self.method in {"nearest", "interpolation"}:
            if self.support != "point" or self.target_time is None:
                raise ValueError(
                    "nearest/interpolation require explicit point support and target time"
                )
            if self.window_start is not None or self.window_end is not None:
                raise ValueError("point adaptation cannot silently ignore a supplied window")
        else:
            if self.target_time is not None or self.window_start is None or self.window_end is None:
                raise ValueError("aggregation requires an explicit window and no point target")
            if self.window_end <= self.window_start:
                raise ValueError("aggregation window must have positive duration")
            if self.method in {"mean", "sum"} and self.support != "interval":
                raise ValueError("mean/sum need interval support, not guessed point weights")
        previous: TemporalObservation | None = None
        for observation in self.observations:
            if (observation.start == observation.end) != (self.support == "point"):
                raise ValueError("observation support differs from declared series support")
            if previous is not None and (
                observation.start <= previous.start
                or (self.support == "interval" and observation.start < previous.end)
            ):
                raise ValueError("observations overlap or are not strictly ordered")
            previous = observation
        try:
            mapped = convert_units([0, 1], self.unit, self.output_unit)
        except CoastMASError as exc:
            raise ValueError("time-series units are incompatible") from exc
        if self.method == "sum" and mapped[0] != 0:
            raise ValueError("extensive sums cannot use offset unit conversion")
        if self.aggregation_type == "categorical" and (
            UNITS.get_dimensionality(self.unit) != UNITS.get_dimensionality("1")
            or mapped[0] != 0
            or mapped[1] != 1
        ):
            raise ValueError("categorical labels require unchanged dimensionless codes")
        return self


class TemporalResult(Contract):
    variable: Name
    value: Number | None
    unit: Name
    method: Method
    start: AwareDatetime
    end: AwareDatetime
    source_start: AwareDatetime
    source_end: AwareDatetime
    observations_used: Annotated[int, Field(strict=True, ge=1)]
    valid_observations: Annotated[int, Field(strict=True, ge=0)]
    nodata_policy: Literal["propagate", "reject"]
    interpretation: str


def adapt_time_series(request: TemporalRequest) -> TemporalResult:
    observations = request.observations
    selected: tuple[TemporalObservation, ...]
    weights: list[float]
    if request.method in {"nearest", "interpolation"}:
        target = request.target_time
        if target is None:
            raise ValueError("target time missing")
        times = [sample.start for sample in observations]
        if not times[0] <= target <= times[-1]:
            raise ValueError("temporal extrapolation is not permitted")
        position = bisect.bisect_left(times, target)
        if times[position] == target:
            selected, weights = (observations[position],), [1.0]
        elif request.method == "nearest":
            # Ties select the earlier sample; no skip-over of missing observations.
            left = position - 1
            nearest = left if target - times[left] <= times[position] - target else position
            selected, weights = (observations[nearest],), [1.0]
        else:
            left = position - 1
            fraction = (target - times[left]).total_seconds() / (
                times[position] - times[left]
            ).total_seconds()
            selected = (observations[left], observations[position])
            weights = [1 - fraction, fraction]
        start = end = target
        interpretation = (
            "Assigned from explicit source support; not an observation at the target time."
        )
    else:
        window_start, window_end = request.window_start, request.window_end
        if window_start is None or window_end is None:
            raise ValueError("aggregation window missing")
        start, end = window_start, window_end
        if start < observations[0].start or end > observations[-1].end:
            raise ValueError("temporal extrapolation is not permitted")
        if request.support == "interval":
            selected = tuple(
                sample for sample in observations if sample.start < end and sample.end > start
            )
            if (
                not selected
                or selected[0].start != start
                or selected[-1].end != end
                or any(a.end != b.start for a, b in zip(selected, selected[1:], strict=False))
            ):
                raise ValueError("source intervals must partition the requested window exactly")
            duration = (end - start).total_seconds()
            weights = [
                (sample.end - sample.start).total_seconds() / duration for sample in selected
            ]
        else:
            selected = tuple(sample for sample in observations if start <= sample.start <= end)
            if not selected:
                raise ValueError("window has no observed samples")
            weights = [1.0] * len(selected)
        interpretation = (
            "Duration-weighted source support means."
            if request.method == "mean"
            else "Sum of complete source support totals."
            if request.method == "sum"
            else (
                "Extremum of observed source support values, not an unobserved continuous extremum."
            )
        )
    valid = sum(sample.value is not None for sample in selected)
    value = None
    if valid != len(selected):
        if request.nodata_policy == "reject":
            raise ValueError("selected source support contains NoData")
    else:
        values = [sample.value for sample in selected if sample.value is not None]
        if request.method == "sum":
            try:
                raw = math.fsum(values)
            except OverflowError as exc:
                raise ValueError("temporal accumulation overflow") from exc
        elif request.method == "min":
            raw = min(values)
        elif request.method == "max":
            raw = max(values)
        else:
            raw = math.fsum(v * w for v, w in zip(values, weights, strict=True))
        try:
            value = float(convert_units([raw], request.unit, request.output_unit)[0])
        except CoastMASError as exc:
            raise ValueError("temporal result cannot be converted to declared output unit") from exc
    return TemporalResult(
        variable=request.variable,
        value=value,
        unit=request.output_unit,
        method=request.method,
        start=start,
        end=end,
        source_start=selected[0].start,
        source_end=selected[-1].end,
        observations_used=len(selected),
        valid_observations=valid,
        nodata_policy=request.nodata_policy,
        interpretation=interpretation,
    )
