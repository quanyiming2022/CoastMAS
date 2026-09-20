import numpy as np
import pytest

from coastmas.core.errors import ConstraintError
from coastmas.domain.assessment import (
    composite,
    entropy_weights,
    normalize,
    temporal_assessment,
    topsis,
)
from coastmas.domain.screening import screen_inundation


def test_normalization_uses_fixed_reference_and_direction():
    result = normalize([[0, 10], [5, 5], [10, 0]], [0, 0], [10, 10], [True, False])
    np.testing.assert_allclose(result, [[0, 0], [0.5, 0.5], [1, 1]])
    np.testing.assert_allclose(composite(result, [1, 3]), [0, 0.5, 1])


@pytest.mark.parametrize(
    "values,lower,upper",
    [([[1]], [2], [1]), ([[float("nan")]], [0], [1]), ([[2]], [0], [1]), ([[1]], [1], [1])],
)
def test_invalid_normalization_blocks(values, lower, upper):
    with pytest.raises(ConstraintError):
        normalize(values, lower, upper, [True])


@pytest.mark.parametrize("weights", [[0, 0], [-1, 2], [float("nan"), 1], [1]])
def test_invalid_weights_block(weights):
    with pytest.raises(ConstraintError):
        composite([[0, 1], [1, 0]], weights)


def test_entropy_ignores_constant_columns_and_handles_zero():
    np.testing.assert_allclose(entropy_weights([[0, 1], [1, 1], [2, 1]]), [1, 0], atol=1e-12)
    with pytest.raises(ConstraintError, match="information"):
        entropy_weights([[0, 0], [0, 0]])


def test_topsis_known_order_and_degenerate_rejection():
    scores = topsis([[1, 1], [2, 2], [3, 3]], [0.5, 0.5], [True, True])
    np.testing.assert_allclose(scores, [0, 0.5, 1], atol=1e-12)
    with pytest.raises(ConstraintError, match="degenerate"):
        topsis([[1, 1], [1, 1]], [1, 1], [True, True])


def test_temporal_fixed_reference_exposes_absolute_change():
    result = temporal_assessment(
        [[[0], [5]], [[5], [10]], [[10], [10]]], [0], [10], [True], [1], [2020, 2021, 2022]
    )
    np.testing.assert_allclose(result.scores, [[0, 0.5], [0.5, 1], [1, 1]])
    np.testing.assert_allclose(result.change, [1, 0.5])
    np.testing.assert_allclose(result.trend, [0.5, 0.25])


def test_screening_blocks_inland_basin_and_nodata():
    dem = np.array([[0, 2, 0], [0, 2, 0], [0, 2, np.nan]])
    result = screen_inundation(
        dem,
        baseline=0,
        increment=0.5,
        seeds=[(0, 0)],
        connectivity=4,
        dem_datum="datum",
        water_datum="datum",
        cell_area=4,
    )
    np.testing.assert_equal(result.mask, [[1, 0, 0], [1, 0, 0], [1, 0, -1]])
    assert result.area == 12
    assert result.absolute_water_level == 0.5


def test_screening_baseline_is_not_increment():
    dem = np.array([[1.2, 1.4]])
    result = screen_inundation(
        dem,
        baseline=1,
        increment=0.5,
        seeds=[(0, 0)],
        connectivity=4,
        dem_datum="d",
        water_datum="d",
        cell_area=1,
    )
    assert result.area == 2


@pytest.mark.parametrize("datum", [None, "wrong"])
def test_screening_blocks_missing_or_mismatched_vertical_datum(datum):
    with pytest.raises(ConstraintError, match="datum"):
        screen_inundation(
            np.zeros((2, 2)),
            baseline=0,
            increment=0.5,
            seeds=[(0, 0)],
            connectivity=4,
            dem_datum=datum,
            water_datum="d",
            cell_area=1,
        )


def test_diagonal_connectivity_is_explicit():
    dem = np.array([[0, 2], [2, 0]])
    args = dict(
        baseline=0, increment=0.5, seeds=[(0, 0)], dem_datum="d", water_datum="d", cell_area=1
    )
    assert screen_inundation(dem, connectivity=4, **args).area == 1
    assert screen_inundation(dem, connectivity=8, **args).area == 2
