import numpy as np
import pytest
from test_contracts import variable

from coastmas.core.binding import (
    choose_resampling,
    conservative_redistribute,
    convert_units,
    temporal_transform,
    transform_coordinates,
    validate_semantics,
)
from coastmas.core.errors import ConstraintError


def test_unit_conversion_preserves_physics_and_offset():
    np.testing.assert_allclose(convert_units([500, 1000], "mm", "m"), [0.5, 1])
    np.testing.assert_allclose(convert_units([0, 100], "degC", "kelvin"), [273.15, 373.15])
    with pytest.raises(ConstraintError):
        convert_units([1], "m", "second")


def test_crs_transform_and_missing_reference():
    x, y = transform_coordinates([0, 1], [0, 1], "EPSG:4326", "EPSG:3857")
    np.testing.assert_allclose(x, [0, 111319.49079327357], atol=1e-6)
    np.testing.assert_allclose(y, [0, 111325.1428663851], atol=1e-6)
    with pytest.raises(ConstraintError):
        transform_coordinates([1], [2], None, "EPSG:4326")


def test_semantics_cannot_be_overridden_by_unit_compatibility():
    source = variable()
    with pytest.raises(ConstraintError):
        validate_semantics(source, variable(standard_name="wave_height"), {})
    assert (
        validate_semantics(
            source, variable(standard_name="terrain_height"), {"elevation": "terrain_height"}
        )
        == "approved_mapping"
    )
    with pytest.raises(ConstraintError):
        validate_semantics(source, variable(temporal_support="annual_average"), {})


def test_categorical_resampling_rejects_continuous_interpolation():
    assert choose_resampling("categorical", None) == "nearest"
    assert choose_resampling("extensive", None) == "area_weighted"
    with pytest.raises(ConstraintError):
        choose_resampling("categorical", "bilinear")


def test_extensive_redistribution_conserves_total_and_rejects_partial_coverage():
    np.testing.assert_allclose(conservative_redistribute([10, 20], [[0.5, 0], [0.5, 1]]), [5, 25])
    with pytest.raises(ConstraintError):
        conservative_redistribute([10, 20], [[0.5, 0], [0, 1]])


def test_temporal_mean_and_interpolation_do_not_guess_extrapolation():
    assert temporal_transform([1, 3], [0, 2], "mean", "intensive") == 2
    assert temporal_transform([1, 3], [0, 2], "interpolation", "intensive", target=1) == 2
    with pytest.raises(ConstraintError):
        temporal_transform([1, 3], [0, 2], "interpolation", "intensive", target=3)
    with pytest.raises(ConstraintError):
        temporal_transform([1, 3], [0, 2], "mean", "extensive")
    assert temporal_transform([1, 3], [0, 2], "sum", "extensive") == 4
