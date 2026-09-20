"""Deterministic scientific transformations. Unknown metadata never implies consent."""

import math
from typing import Literal

import numpy as np
import pint
from numpy.typing import ArrayLike
from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError

from coastmas.core.contracts import UNITS, VariableSpec
from coastmas.core.errors import ConstraintError
from coastmas.core.numeric import FloatArray, finite_array

ResamplingMethod = Literal["nearest", "bilinear", "cubic", "sum", "area_weighted"]


def convert_units(values: ArrayLike, source: str, target: str) -> FloatArray:
    array = np.asarray(values, dtype=np.float64)
    if array.size == 0 or not np.all(np.isfinite(array)):
        raise ConstraintError("unit conversion requires finite values; apply NoData mask first")
    try:
        converted = UNITS.Quantity(array, source).to(target).magnitude
    except (pint.UndefinedUnitError, pint.DimensionalityError, ValueError) as exc:
        raise ConstraintError("units are unknown or incompatible") from exc
    result = np.asarray(converted, dtype=np.float64)
    if not np.all(np.isfinite(result)):
        raise ConstraintError("unit conversion overflow")
    return result


def transform_coordinates(
    x: ArrayLike, y: ArrayLike, source: str | None, target: str | None
) -> tuple[FloatArray, FloatArray]:
    if not source or not target:
        raise ConstraintError("CRS missing; transformation is blocked")
    horizontal = finite_array(x, 1, "x coordinates")
    vertical = finite_array(y, 1, "y coordinates")
    if horizontal.shape != vertical.shape:
        raise ConstraintError("coordinate arrays differ")
    try:
        transformer = Transformer.from_crs(
            CRS(source), CRS(target), always_xy=True, allow_ballpark=False, only_best=True
        )
        transformed_x, transformed_y = transformer.transform(horizontal, vertical, errcheck=True)
    except ProjError as exc:
        raise ConstraintError("CRS transformation unavailable or invalid") from exc
    return (
        finite_array(transformed_x, 1, "transformed x"),
        finite_array(transformed_y, 1, "transformed y"),
    )


def validate_semantics(source: VariableSpec, target: VariableSpec, approved: dict[str, str]) -> str:
    if (
        source.aggregation_type != target.aggregation_type
        or source.temporal_support != target.temporal_support
        or source.semantic_type != target.semantic_type
    ):
        raise ConstraintError("statistical or semantic meaning differs")
    if source.data_type != target.data_type or source.spatial_support != target.spatial_support:
        raise ConstraintError("data type or spatial support requires explicit transformation")
    convert_units([1], source.unit, target.unit)
    if source.standard_name == target.standard_name:
        return "exact_standard_name"
    if approved.get(source.standard_name) == target.standard_name:
        return "approved_mapping"
    raise ConstraintError("semantic mapping requires approval; similarity is insufficient")


def choose_resampling(semantic_type: str, requested: ResamplingMethod | None) -> ResamplingMethod:
    allowed: dict[str, tuple[ResamplingMethod, ...]] = {
        "continuous": ("bilinear", "nearest", "cubic"),
        "categorical": ("nearest",),
        "extensive": ("area_weighted", "sum"),
    }
    methods = allowed.get(semantic_type)
    if methods is None:
        raise ConstraintError("unknown variable semantics")
    if requested is not None and requested not in methods:
        raise ConstraintError("resampling method conflicts with variable semantics")
    return requested or methods[0]


def conservative_redistribute(values: ArrayLike, fractions: ArrayLike) -> FloatArray:
    totals = finite_array(values, 1, "source totals")
    allocation = finite_array(fractions, 2, "target by source area fractions")
    if allocation.shape[1] != totals.size or np.any(allocation < 0) or np.any(totals < 0):
        raise ConstraintError("invalid extensive quantity allocation")
    # Fractions are intersection area / source area; partial/overlapping coverage is rejected.
    if not np.allclose(allocation.sum(axis=0), 1, atol=1e-10, rtol=0):
        raise ConstraintError("target coverage must partition every source area exactly once")
    output = np.asarray(allocation @ totals, dtype=np.float64)
    if not np.isclose(output.sum(), totals.sum(), rtol=1e-10, atol=1e-10):
        raise ConstraintError("total conservation failed")
    return output


def temporal_transform(
    values: ArrayLike,
    times: ArrayLike,
    method: str,
    aggregation_type: str,
    *,
    target: float | None = None,
) -> float:
    samples = finite_array(values, 1, "time samples")
    coordinates = finite_array(times, 1, "time coordinates")
    if samples.size != coordinates.size or np.any(np.diff(coordinates) <= 0):
        raise ConstraintError("time coordinates must match and strictly increase")
    allowed = {
        "intensive": {"nearest", "mean", "min", "max", "interpolation"},
        "instantaneous": {"nearest", "interpolation", "min", "max"},
        "extensive": {"sum"},
        "categorical": {"nearest"},
    }
    if method not in allowed.get(aggregation_type, set()):
        raise ConstraintError("temporal operation conflicts with aggregation meaning")
    if method in ("nearest", "interpolation"):
        if target is None or not math.isfinite(target):
            raise ConstraintError("target time required")
        if not coordinates[0] <= target <= coordinates[-1]:
            raise ConstraintError("temporal extrapolation is not permitted")
        if method == "nearest":
            return float(samples[np.argmin(abs(coordinates - target))])
        return float(np.interp(target, coordinates, samples))
    if method == "mean":
        # Unweighted mean applies to equally supported observations only.
        if coordinates.size > 2 and not np.allclose(np.diff(coordinates), np.diff(coordinates)[0]):
            raise ConstraintError("unequal temporal support requires explicit weighted aggregation")
        return float(samples.mean())
    if method == "sum":
        return float(samples.sum())
    if method == "min":
        return float(samples.min())
    return float(samples.max())
