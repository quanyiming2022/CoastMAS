import numpy as np
import pytest
from affine import Affine

from coastmas.adapters.geofiles import Grid, decode_geotiff, encode_geotiff, resample_grid
from coastmas.core.errors import CoastMASError


def test_real_geotiff_roundtrip_preserves_datum_units_and_nodata():
    grid = Grid(
        np.array([[1.0, np.nan], [3.0, 4.0]]),
        "EPSG:32650",
        Affine(30, 0, 500000, 0, -30, 3500000),
        "m",
        "synthetic-local-datum",
    )
    data = encode_geotiff(grid)
    assert data[:4] in (b"II*\x00", b"MM\x00*")
    restored = decode_geotiff(data)
    np.testing.assert_allclose(restored.values, grid.values, equal_nan=True)
    assert restored.vertical_datum == grid.vertical_datum
    assert restored.unit == "m"
    assert restored.cell_area_m2 == 900
    assert restored.transform == grid.transform


def test_decode_rejects_non_tiff_and_oversized_raster_before_allocation():
    with pytest.raises(CoastMASError):
        decode_geotiff(b"not a tiff")
    grid = Grid(np.ones((3, 3)), "EPSG:32650", Affine(10, 0, 1, 0, -10, 100), "m")
    with pytest.raises(CoastMASError, match="budget"):
        decode_geotiff(encode_geotiff(grid), max_cells=4)


def test_categorical_regridding_never_creates_fractional_classes():
    grid = Grid(
        np.array([[1.0, 2.0], [3.0, np.nan]]),
        "EPSG:32650",
        Affine(20, 0, 500000, 0, -20, 3500000),
        "dimensionless",
    )
    transformed = resample_grid(
        grid,
        crs="EPSG:32650",
        transform=Affine(10, 0, 500000, 0, -10, 3500000),
        shape=(4, 4),
        kind="categorical",
        method="nearest",
    )
    assert set(transformed.values[np.isfinite(transformed.values)]) == {1, 2, 3}
    assert np.isnan(transformed.values[-1, -1])
    with pytest.raises(CoastMASError, match="categorical"):
        resample_grid(
            grid,
            crs=grid.crs,
            transform=grid.transform,
            shape=(2, 2),
            kind="categorical",
            method="bilinear",
        )


def test_extensive_variables_cannot_be_interpolated_as_intensive():
    grid = Grid(np.ones((2, 2)), "EPSG:32650", Affine(10, 0, 1, 0, -10, 100), "person")
    with pytest.raises(CoastMASError, match="conservative"):
        resample_grid(
            grid,
            crs=grid.crs,
            transform=grid.transform,
            shape=(2, 2),
            kind="extensive",
            method="bilinear",
        )


def test_geographic_grid_cannot_report_degree_squared_as_square_metres():
    grid = Grid(np.ones((2, 2)), "EPSG:4326", Affine(0.1, 0, 120, 0, -0.1, 30), "m")
    with pytest.raises(CoastMASError, match="projected"):
        _ = grid.cell_area_m2


def test_invalid_grid_and_missing_metadata_fail_explicitly():
    for transform in (Affine(0, 0, 0, 0, 0, 0), Affine(float("nan"), 0, 0, 0, -1, 0)):
        with pytest.raises(CoastMASError):
            Grid(np.ones((2, 2)), "EPSG:32650", transform, "m")
    with pytest.raises(CoastMASError):
        Grid(np.array([[float("inf")]]), "EPSG:32650", Affine(1, 0, 1, 0, -1, 1), "m")
