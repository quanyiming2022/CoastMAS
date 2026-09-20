"""Shared numerical boundary validation; no domain-specific assumptions."""

import numpy as np
from numpy.typing import ArrayLike, NDArray

from coastmas.core.errors import ConstraintError

FloatArray = NDArray[np.float64]


def finite_array(values: ArrayLike, ndim: int, label: str) -> FloatArray:
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != ndim or result.size == 0 or not np.all(np.isfinite(result)):
        raise ConstraintError(f"{label} must be a nonempty finite {ndim}D array")
    return result
