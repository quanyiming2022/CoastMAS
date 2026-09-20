"""Safe array algebra and explicit valid-area statistics.

The calculator interprets a small AST; it never evaluates Python source.
NoData in any referenced input propagates to the output even through a where
condition, preventing an unknown condition from becoming a false low score.
"""

import ast
import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from coastmas.core.errors import ConstraintError
from coastmas.core.numeric import FloatArray
from coastmas.domain.assessment import normalized_weights


def raster_calculator(expression: str, variables: Mapping[str, ArrayLike]) -> FloatArray:
    if len(expression) > 1000 or not variables:
        raise ConstraintError("expression or variable budget exceeded")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ConstraintError("invalid raster expression") from exc
    if len(list(ast.walk(tree))) > 100:
        raise ConstraintError("expression is too complex")
    arrays = {name: np.asarray(value, dtype=np.float64) for name, value in variables.items()}
    first = next(iter(arrays.values()))
    if first.ndim != 2 or first.size == 0:
        raise ConstraintError("raster arrays must be nonempty 2D")
    if any(value.shape != first.shape or np.any(np.isinf(value)) for value in arrays.values()):
        raise ConstraintError("raster shapes differ or values contain infinity")
    referenced: set[str] = set()

    def interpret(node: ast.AST) -> FloatArray:
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        ):
            number = float(node.value)
            if not math.isfinite(number) or abs(number) > 1e12:
                raise ConstraintError("constant outside expression budget")
            return np.asarray(number, dtype=np.float64)
        if isinstance(node, ast.Name) and node.id in arrays:
            referenced.add(node.id)
            return arrays[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = interpret(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left, right = interpret(node.left), interpret(node.right)
            if isinstance(node.op, ast.Add):
                return np.asarray(left + right, dtype=np.float64)
            if isinstance(node.op, ast.Sub):
                return np.asarray(left - right, dtype=np.float64)
            if isinstance(node.op, ast.Mult):
                return np.asarray(left * right, dtype=np.float64)
            if isinstance(node.op, ast.Div):
                return np.asarray(left / right, dtype=np.float64)
            if isinstance(node.op, ast.Pow):
                if right.ndim != 0 or abs(float(right)) > 8:
                    raise ConstraintError("power must be a scalar with magnitude <= 8")
                return np.asarray(left**right, dtype=np.float64)
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left, right = interpret(node.left), interpret(node.comparators[0])
            operation = node.ops[0]
            if isinstance(operation, ast.Gt):
                return np.asarray(left > right, dtype=np.float64)
            if isinstance(operation, ast.GtE):
                return np.asarray(left >= right, dtype=np.float64)
            if isinstance(operation, ast.Lt):
                return np.asarray(left < right, dtype=np.float64)
            if isinstance(operation, ast.LtE):
                return np.asarray(left <= right, dtype=np.float64)
            if isinstance(operation, ast.Eq):
                return np.asarray(left == right, dtype=np.float64)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id
            if name == "where" and len(node.args) == 3:
                condition, yes, no = [interpret(argument) for argument in node.args]
                return np.asarray(np.where(condition, yes, no), dtype=np.float64)
            if name in ("sqrt", "log", "abs") and len(node.args) == 1:
                value = interpret(node.args[0])
                if name == "sqrt":
                    return np.asarray(np.sqrt(value), dtype=np.float64)
                if name == "log":
                    return np.asarray(np.log(value), dtype=np.float64)
                return np.asarray(np.abs(value), dtype=np.float64)
        raise ConstraintError("expression contains an unapproved operation or variable")

    try:
        with np.errstate(divide="raise", invalid="raise", over="raise"):
            result = np.broadcast_to(interpret(tree.body), first.shape).copy()
    except (FloatingPointError, OverflowError) as exc:
        raise ConstraintError("undefined or overflowing raster calculation") from exc
    if not referenced:
        raise ConstraintError("expression must reference a raster")
    nodata = np.zeros(first.shape, dtype=bool)
    for name in referenced:
        nodata |= np.isnan(arrays[name])
    result[nodata] = np.nan
    if np.any(~np.isfinite(result[~nodata])):
        raise ConstraintError("calculation generated invalid values")
    return np.asarray(result, dtype=np.float64)


@dataclass(frozen=True)
class ZonalStatistics:
    count: int
    total: float | None
    mean: float | None
    minimum: float | None
    maximum: float | None
    std: float | None
    valid_area: float
    zone_area: float
    coverage: float


def zonal_statistics(
    values: ArrayLike, zones: ArrayLike, *, cell_area: float
) -> dict[int, ZonalStatistics]:
    matrix = np.asarray(values, dtype=np.float64)
    identifiers = np.asarray(zones, dtype=np.float64)
    if matrix.ndim != 2 or matrix.size == 0 or identifiers.shape != matrix.shape:
        raise ConstraintError("zone and value grids must match")
    if (
        not math.isfinite(cell_area)
        or cell_area <= 0
        or np.any(np.isinf(matrix))
        or not np.all(np.isfinite(identifiers))
        or np.any(identifiers != np.floor(identifiers))
    ):
        raise ConstraintError("invalid areas, zone identifiers or raster values")
    output: dict[int, ZonalStatistics] = {}
    for identifier in np.unique(identifiers):
        zone = identifiers == identifier
        observed = matrix[zone & np.isfinite(matrix)]
        count = int(observed.size)
        zone_count = int(np.count_nonzero(zone))
        output[int(identifier)] = ZonalStatistics(
            count,
            float(observed.sum()) if count else None,
            float(observed.mean()) if count else None,
            float(observed.min()) if count else None,
            float(observed.max()) if count else None,
            float(observed.std(ddof=0)) if count else None,
            count * cell_area,
            zone_count * cell_area,
            count / zone_count,
        )
    return output


def suitability(factors: ArrayLike, weights: ArrayLike, allowed: ArrayLike) -> FloatArray:
    cube = np.asarray(factors, dtype=np.float64)
    mask: NDArray[np.bool_] = np.asarray(allowed, dtype=bool)
    if cube.ndim != 3 or cube.size == 0 or cube.shape[1:] != mask.shape:
        raise ConstraintError("factor grids and constraint mask must match")
    finite = cube[np.isfinite(cube)]
    if np.any(np.isinf(cube)) or np.any(finite < 0) or np.any(finite > 1):
        raise ConstraintError("suitability factors must be normalized in [0,1]")
    weight = normalized_weights(weights, cube.shape[0])
    scores = np.asarray(np.tensordot(weight, cube, axes=(0, 0)), dtype=np.float64)
    scores[~mask] = np.nan
    return scores
