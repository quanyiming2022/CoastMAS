"""Dimension-aware raster expressions evaluated in base units.

Numeric literals in additive expressions, comparisons and where branches use
the peer operand's base unit; multiplicative literals are dimensionless. This
convention is explicit so a threshold is never silently interpreted as cm in
one raster and metres in another. Output units must match the derived dimension.
"""

import ast

import numpy as np

from coastmas.adapters.geofiles import Grid
from coastmas.core.binding import convert_units
from coastmas.core.contracts import UNITS
from coastmas.core.errors import ConstraintError
from coastmas.domain.raster import raster_calculator


def calculate_grids(expression: str, rasters: dict[str, Grid], output_unit: str) -> Grid:
    if not rasters:
        raise ConstraintError("calculator requires at least one grid")
    template = next(iter(rasters.values()))
    arrays = {}
    units: dict[str, str] = {}
    for name, grid in rasters.items():
        if (
            grid.crs != template.crs
            or grid.transform != template.transform
            or grid.values.shape != template.values.shape
        ):
            raise ConstraintError("calculator grids must be explicitly aligned")
        base = str(UNITS.Quantity(1, grid.unit).to_base_units().units)
        values = grid.values.copy()
        known = np.isfinite(values)
        if np.any(known):
            values[known] = convert_units(values[known], grid.unit, base)
        arrays[name] = values
        units[name] = base
    result = raster_calculator(expression, arrays)

    def compatible(left: str | None, right: str | None) -> str | None:
        if (
            left is not None
            and right is not None
            and not UNITS.Unit(left).is_compatible_with(right)
        ):
            raise ConstraintError("raster expression combines incompatible physical dimensions")
        return left or right

    def infer(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant):
            return None
        if isinstance(node, ast.Name):
            return units[node.id]
        if isinstance(node, ast.UnaryOp):
            return infer(node.operand)
        if isinstance(node, ast.BinOp):
            left, right = infer(node.left), infer(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                return compatible(left, right)
            if isinstance(node.op, ast.Mult):
                return str(
                    UNITS.Unit(left or "dimensionless") * UNITS.Unit(right or "dimensionless")
                )
            if isinstance(node.op, ast.Div):
                return str(
                    UNITS.Unit(left or "dimensionless") / UNITS.Unit(right or "dimensionless")
                )
            if (
                isinstance(node.op, ast.Pow)
                and isinstance(node.right, ast.Constant)
                and isinstance(node.right.value, (int, float))
            ):
                return str(UNITS.Unit(left or "dimensionless") ** float(node.right.value))
        if isinstance(node, ast.Compare):
            compatible(infer(node.left), infer(node.comparators[0]))
            return "dimensionless"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            unit = infer(node.args[0])
            if node.func.id == "where":
                if unit is not None and not UNITS.Unit(unit).dimensionless:
                    raise ConstraintError("where condition must be dimensionless")
                return compatible(infer(node.args[1]), infer(node.args[2]))
            if node.func.id == "sqrt":
                return str(UNITS.Unit(unit or "dimensionless") ** 0.5)
            if node.func.id == "log":
                if unit is not None and not UNITS.Unit(unit).dimensionless:
                    raise ConstraintError("log argument must be dimensionless")
                return "dimensionless"
            if node.func.id == "abs":
                return unit
        raise ConstraintError("unsupported dimensional expression")

    result_unit = infer(ast.parse(expression, mode="eval").body) or "dimensionless"
    known = np.isfinite(result)
    # Check even an entirely NoData result so missing coverage cannot bypass units.
    convert_units([1.0], result_unit, output_unit)
    if np.any(known):
        result[known] = convert_units(result[known], result_unit, output_unit)
    datum = template.vertical_datum if output_unit == template.unit else None
    return Grid(result, template.crs, template.transform, output_unit, datum)
