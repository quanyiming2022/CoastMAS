"""Terrain-connectivity screening, NOT a hydrodynamic solver.

Input heights and baseline/increment are metres in the same declared vertical
reference. Coastal seeds must be supplied by a reviewed scene. NaN and masked
cells are barriers and preserved as -1 in the result. The equality boundary is
wet (height <= absolute water level). Cell area must be computed in square
metres outside this routine from an appropriate projected/equal-area grid.
"""

import math
from collections import deque
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from coastmas.core.errors import ConstraintError


@dataclass(frozen=True)
class ScreeningResult:
    mask: NDArray[np.int8]
    area: float
    absolute_water_level: float
    connectivity: int
    seeds: tuple[tuple[int, int], ...]


def screen_inundation(
    dem: ArrayLike,
    *,
    baseline: float,
    increment: float,
    seeds: list[tuple[int, int]],
    connectivity: int,
    dem_datum: str | None,
    water_datum: str | None,
    cell_area: float,
    barriers: ArrayLike | None = None,
) -> ScreeningResult:
    if not dem_datum or not water_datum or dem_datum != water_datum:
        raise ConstraintError("vertical datum is missing or differs; transformation required")
    if not all(math.isfinite(value) for value in (baseline, increment, cell_area)):
        raise ConstraintError("water level and cell area must be finite")
    if cell_area <= 0 or connectivity not in (4, 8):
        raise ConstraintError("positive cell area and 4/8 connectivity required")
    heights = np.asarray(dem, dtype=np.float64)
    if heights.ndim != 2 or heights.size == 0 or np.any(np.isinf(heights)):
        raise ConstraintError("DEM must be nonempty 2D and cannot contain infinity")
    if not seeds:
        raise ConstraintError("reviewed coastal seeds are required")
    water_level = baseline + increment
    if not math.isfinite(water_level):
        raise ConstraintError("absolute water level overflow")
    blocked = np.zeros(heights.shape, dtype=bool)
    if barriers is not None:
        blocked = np.asarray(barriers, dtype=bool)
        if blocked.shape != heights.shape:
            raise ConstraintError("barrier grid differs from DEM")
    valid = np.isfinite(heights)
    eligible = valid & ~blocked & (heights <= water_level)
    result = np.zeros(heights.shape, dtype=np.int8)
    result[~valid] = -1
    queue: deque[tuple[int, int]] = deque()
    rows, columns = heights.shape
    for row, column in seeds:
        if not (0 <= row < rows and 0 <= column < columns):
            raise ConstraintError("coastal seed outside DEM")
        if not valid[row, column] or blocked[row, column]:
            raise ConstraintError("coastal seed lies on NoData or barrier")
        if eligible[row, column] and result[row, column] != 1:
            result[row, column] = 1
            queue.append((row, column))
    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if connectivity == 8:
        offsets += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    while queue:
        row, column = queue.popleft()
        for row_delta, column_delta in offsets:
            next_row, next_column = row + row_delta, column + column_delta
            if 0 <= next_row < rows and 0 <= next_column < columns:
                if eligible[next_row, next_column] and result[next_row, next_column] != 1:
                    result[next_row, next_column] = 1
                    queue.append((next_row, next_column))
    return ScreeningResult(
        result,
        float(np.count_nonzero(result == 1) * cell_area),
        water_level,
        connectivity,
        tuple(seeds),
    )
