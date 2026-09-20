"""Deterministic assessment with explicit rejection of undefined scores.

A constant reference interval is not informative and is rejected. Constant
sample columns remain usable with an externally declared nonzero interval.
No missing value is imputed; frameworks must supply a reviewed imputation
transformation before this engine. Entropy uses nonnegative benefit-oriented
values and gives constant columns zero information weight.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from coastmas.core.errors import ConstraintError
from coastmas.core.numeric import FloatArray, finite_array


def normalized_weights(weights: ArrayLike, columns: int) -> FloatArray:
    result = finite_array(weights, 1, "weights")
    if result.size != columns or np.any(result < 0) or result.sum() <= 0:
        raise ConstraintError("weights must match columns, be nonnegative and have positive sum")
    return np.asarray(result / result.sum(), dtype=np.float64)


def normalize(
    values: ArrayLike, lower: ArrayLike, upper: ArrayLike, positive: list[bool]
) -> FloatArray:
    matrix = finite_array(values, 2, "indicators")
    minimum = finite_array(lower, 1, "reference minimum")
    maximum = finite_array(upper, 1, "reference maximum")
    if minimum.size != matrix.shape[1] or maximum.size != minimum.size:
        raise ConstraintError("reference dimensions differ from indicators")
    if len(positive) != minimum.size or not all(isinstance(value, bool) for value in positive):
        raise ConstraintError("each indicator requires a boolean direction")
    if np.any(maximum <= minimum):
        raise ConstraintError("reference intervals must be nonconstant and increasing")
    if np.any(matrix < minimum) or np.any(matrix > maximum):
        raise ConstraintError("value outside fixed reference interval; review framework version")
    scaled = (matrix - minimum) / (maximum - minimum)
    return np.asarray(np.where(positive, scaled, 1 - scaled), dtype=np.float64)


def composite(values: ArrayLike, weights: ArrayLike) -> FloatArray:
    matrix = finite_array(values, 2, "normalized indicators")
    if np.any(matrix < 0) or np.any(matrix > 1):
        raise ConstraintError("composite requires normalized values in [0,1]")
    return np.asarray(matrix @ normalized_weights(weights, matrix.shape[1]), dtype=np.float64)


def entropy_weights(values: ArrayLike) -> FloatArray:
    matrix = finite_array(values, 2, "entropy indicators")
    if matrix.shape[0] < 2 or np.any(matrix < 0):
        raise ConstraintError("entropy requires at least two rows of nonnegative values")
    totals = matrix.sum(axis=0)
    proportions = np.divide(matrix, totals, out=np.zeros_like(matrix), where=totals > 0)
    logarithms = np.zeros_like(proportions)
    np.log(proportions, out=logarithms, where=proportions > 0)
    entropy = -(proportions * logarithms).sum(axis=0) / np.log(matrix.shape[0])
    information = np.clip(1 - entropy, 0, 1)
    information[np.ptp(matrix, axis=0) == 0] = 0
    if information.sum() <= np.finfo(float).eps:
        raise ConstraintError("no information in constant indicators; choose reviewed weights")
    return np.asarray(information / information.sum(), dtype=np.float64)


def topsis(values: ArrayLike, weights: ArrayLike, positive: list[bool]) -> FloatArray:
    matrix = finite_array(values, 2, "TOPSIS indicators")
    if len(positive) != matrix.shape[1]:
        raise ConstraintError("TOPSIS directions differ from columns")
    weight = normalized_weights(weights, matrix.shape[1])
    norms = np.linalg.norm(matrix, axis=0)
    normalized = np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms > 0)
    weighted = normalized * weight
    best = np.where(positive, weighted.max(axis=0), weighted.min(axis=0))
    worst = np.where(positive, weighted.min(axis=0), weighted.max(axis=0))
    distance_best = np.linalg.norm(weighted - best, axis=1)
    distance_worst = np.linalg.norm(weighted - worst, axis=1)
    denominator = distance_best + distance_worst
    if np.any(denominator <= np.finfo(float).eps):
        raise ConstraintError("degenerate TOPSIS ideal solutions; no defensible ranking")
    return np.asarray(distance_worst / denominator, dtype=np.float64)


@dataclass(frozen=True)
class TemporalAssessment:
    scores: FloatArray
    ranks: NDArray[np.int64]
    change: FloatArray
    trend: FloatArray


def temporal_assessment(
    periods: ArrayLike,
    lower: ArrayLike,
    upper: ArrayLike,
    positive: list[bool],
    weights: ArrayLike,
    years: ArrayLike,
) -> TemporalAssessment:
    cube = finite_array(periods, 3, "period indicators")
    times = finite_array(years, 1, "time coordinates")
    if times.size != cube.shape[0] or times.size < 2 or np.any(np.diff(times) <= 0):
        raise ConstraintError("periods require strictly increasing time coordinates")
    scores = np.stack(
        [composite(normalize(period, lower, upper, positive), weights) for period in cube]
    )
    # Competition ranks preserve ties rather than assigning arbitrary winners.
    ranks = np.asarray(
        [[1 + np.count_nonzero(row > score) for score in row] for row in scores], dtype=np.int64
    )
    centered = times - times.mean()
    trend = np.asarray(centered @ scores / (centered @ centered), dtype=np.float64)
    return TemporalAssessment(scores, ranks, scores[-1] - scores[0], trend)
