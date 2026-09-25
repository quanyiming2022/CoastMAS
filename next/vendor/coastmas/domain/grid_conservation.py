"""Exact planar cell-intersection allocation for extensive raster quantities.

Both grids must already share a reviewed projected CRS. Every source cell must
be fully partitioned and every covered target cell fully observed. NoData or
partial cells require a separately reviewed missing-coverage policy and are
rejected here. Uncovered target cells remain NaN, never zero population.
"""

import math

import numpy as np
from affine import Affine
from numpy.typing import ArrayLike
from shapely.geometry import Polygon  # type: ignore[import-untyped]
from shapely.strtree import STRtree  # type: ignore[import-untyped]

from coastmas.core.errors import ConstraintError
from coastmas.core.numeric import FloatArray, finite_array


def allocate_grid(
    values: ArrayLike,
    source: Affine,
    target: Affine,
    shape: tuple[int, int],
    *,
    max_cells: int = 100000,
) -> FloatArray:
    totals = finite_array(values, 2, "conservative source totals")
    if np.any(totals < 0) or min(shape) <= 0 or max(totals.size, shape[0] * shape[1]) > max_cells:
        raise ConstraintError("conservative grid values or cell budget invalid")
    for transform in (source, target):
        if transform.determinant == 0 or not all(math.isfinite(value) for value in transform):
            raise ConstraintError("conservative affine transforms must be finite and invertible")

    def cell(transform: Affine, row: int, column: int) -> Polygon:
        return Polygon(
            [
                transform @ (column, row),
                transform @ (column + 1, row),
                transform @ (column + 1, row + 1),
                transform @ (column, row + 1),
            ]
        )

    polygons = [
        cell(source, row, column)
        for row in range(totals.shape[0])
        for column in range(totals.shape[1])
    ]
    tree = STRtree(polygons)
    fractions = np.zeros(totals.size, dtype=np.float64)
    flattened = totals.ravel()
    output = np.full(shape, np.nan, dtype=np.float64)
    for row in range(shape[0]):
        for column in range(shape[1]):
            destination = cell(target, row, column)
            observed_area = 0.0
            quantity = 0.0
            for raw_index in tree.query(destination):
                index = int(raw_index)
                area = float(destination.intersection(polygons[index]).area)
                if area <= 0:
                    continue
                fraction = area / float(polygons[index].area)
                fractions[index] += fraction
                quantity += flattened[index] * fraction
                observed_area += area
            if observed_area:
                if not math.isclose(
                    observed_area, float(destination.area), rel_tol=1e-10, abs_tol=1e-10
                ):
                    raise ConstraintError(
                        "target cell has partial coverage; cannot infer unknown total"
                    )
                output[row, column] = quantity
    if not np.allclose(fractions, 1.0, rtol=0, atol=1e-10):
        raise ConstraintError("target coverage must partition every source cell exactly once")
    if not np.isclose(np.nansum(output), totals.sum(), rtol=1e-10, atol=1e-10):
        raise ConstraintError("conservative grid total verification failed")
    return output
