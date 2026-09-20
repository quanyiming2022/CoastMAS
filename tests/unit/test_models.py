import numpy as np
import pytest

from coastmas.core.errors import ConstraintError
from coastmas.domain.optimization import CandidateUnit, optimize_units
from coastmas.domain.raster import raster_calculator, suitability, zonal_statistics


def test_optimization_respects_hard_protection_over_score():
    units = [
        CandidateUnit(
            id="protected", benefit=1000, cost=1, area=1, ecological_cost=0, risk=0, allowed=False
        ),
        CandidateUnit(id="a", benefit=5, cost=2, area=1, ecological_cost=1, risk=1),
        CandidateUnit(id="b", benefit=8, cost=3, area=2, ecological_cost=1, risk=1),
    ]
    result = optimize_units(
        units, budget=3, minimum_area=1, maximum_ecological_cost=2, maximum_risk=2, time_limit=5
    )
    assert result.status == "OPTIMAL"
    assert result.selected == ("b",)
    assert result.benefit == 8
    assert result.constraints_satisfied


def test_optimization_reports_infeasible_without_fake_solution():
    units = [CandidateUnit(id="a", benefit=1, cost=2, area=1, ecological_cost=1, risk=1)]
    result = optimize_units(
        units, budget=1, minimum_area=1, maximum_ecological_cost=2, maximum_risk=2, time_limit=5
    )
    assert result.status == "INFEASIBLE"
    assert result.selected == ()
    assert not result.constraints_satisfied


def test_safe_raster_expression_and_nodata_propagation():
    result = raster_calculator(
        "where(a > 1, a * 2, b + 1)", {"a": np.array([[1, 2, np.nan]]), "b": np.array([[3, 4, 5]])}
    )
    np.testing.assert_allclose(result, [[4, 4, np.nan]], equal_nan=True)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os')",
        "a.__class__",
        "[x for x in a]",
        "a ** 100000000",
        "open('file')",
        "a / 0",
    ],
)
def test_raster_rejects_code_execution_or_invalid_math(expression):
    with pytest.raises(ConstraintError):
        raster_calculator(expression, {"a": np.array([[1, 2]])})


def test_zonal_statistics_excludes_nodata_and_reports_coverage():
    result = zonal_statistics([[1, 3], [np.nan, 4]], [[1, 1], [1, 2]], cell_area=2)
    first = result[1]
    assert first.count == 2
    assert first.total == 4
    assert first.mean == 2
    assert first.minimum == 1 and first.maximum == 3
    assert first.std == 1
    assert first.valid_area == 4 and first.zone_area == 6
    assert first.coverage == pytest.approx(2 / 3)


def test_empty_zone_has_no_fake_zero_statistics():
    result = zonal_statistics([[np.nan]], [[1]], cell_area=1)
    assert result[1].count == 0
    assert result[1].mean is None
    assert result[1].total is None


def test_suitability_masks_protected_cells_and_preserves_missing():
    result = suitability(
        [[[0, 1], [0.5, np.nan]], [[1, 0], [0.5, 0.5]]], [1, 1], [[True, False], [True, True]]
    )
    np.testing.assert_allclose(result, [[0.5, np.nan], [0.5, np.nan]], equal_nan=True)
